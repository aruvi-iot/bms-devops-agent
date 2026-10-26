from __future__ import annotations

import json
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from .evidence import append_audit, artifact_hashes, canonical_hash, classify_failure, configuration_record, write_evidence
from .git import current_head, resolve_revision, working_tree_status
from .models import AgentState
from .runner import CommandResult, run_command


class GateError(ValueError):
    pass


def _approval_valid(approval: Any, expected_scope: str) -> bool:
    if not isinstance(approval, dict):
        return False
    required = ("approval_id", "actor", "role", "approved_at", "scope")
    if any(not isinstance(approval.get(key), str) or not approval[key].strip() for key in required):
        return False
    try:
        datetime.fromisoformat(approval["approved_at"].replace("Z", "+00:00"))
    except ValueError:
        return False
    return approval["scope"] == expected_scope


def preflight(state: AgentState) -> dict[str, Any]:
    task, config = state["task"], state["config"]
    messages: list[str] = []
    if task.get("engineering_state") not in ("S5", "S6", "S7", "S8"):
        raise GateError("Unsupported engineering state")
    if task.get("validation_status") not in (None, "not_performed"):
        raise GateError("Task cannot instruct this agent to execute or report validation")
    if task.get("validation_passed") is False or task.get("compliance_blocked") is True:
        raise GateError("Required validation failed or compliance has blocked this transition")
    if not _approval_valid(task.get("approvals", {}).get("configuration"), task["configuration_id"]):
        raise GateError("Missing recorded human approval for this configuration")
    if task["engineering_state"] == "S6" and config["policy"].get("require_codegen_approval_for_s6", True):
        if not _approval_valid(task.get("approvals", {}).get("code_generation"), "SIL code generation"):
            raise GateError("Missing recorded human approval for SIL code generation")
    repo_root = str(Path(task["repo_root"]).resolve(strict=True))
    commit = resolve_revision(repo_root, task["source_revision"])
    if current_head(repo_root) != commit:
        raise GateError("Checked-out HEAD differs from the approved task revision; checkout changes are outside this agent")
    dirty = working_tree_status(repo_root)
    if dirty:
        raise GateError("Repository working tree is not clean; agent will not build ambiguous inputs")
    hashes = artifact_hashes(repo_root, task.get("artifacts", []))
    if not hashes:
        raise GateError("At least one approved artifact path is required")
    expected = task.get("expected_artifact_hashes", {})
    if not expected:
        raise GateError("Approved expected_artifact_hashes are required to check configuration drift")
    if expected != hashes:
        raise GateError("Configuration drift detected: current artifact checksums differ from the approved record")
    if task["engineering_state"] == "S6" and not task.get("output_artifacts"):
        raise GateError("S6 build task must declare output_artifacts for its manifest")
    if task["engineering_state"] == "S8" and not task.get("expected_output_hashes"):
        raise GateError("S8 reproducibility rebuild requires expected_output_hashes from the recorded build")
    messages.append("Inputs and approvals passed preflight")
    return {"source_commit": commit, "artifact_hashes": hashes, "messages": messages}


def source_check(state: AgentState) -> dict[str, Any]:
    config = state["config"]
    result = run_command(config["checks"].get("source", []), config, state["execute"],
                         state["task"]["repo_root"], _command_context(state))
    return {"stage_results": {"source": _result_dict(result)}}


def _command_context(state: AgentState) -> dict[str, str]:
    task = state["task"]
    return {"BMS_TASK_ID": task["task_id"],
            "BMS_ENGINEERING_STATE": task["engineering_state"],
            "BMS_SOURCE_COMMIT": state.get("source_commit", task["source_revision"]),
            "BMS_CONFIGURATION_ID": task["configuration_id"]}


def _result_dict(result: CommandResult) -> dict[str, Any]:
    return {"status": result.status, "returncode": result.returncode,
            "stdout": result.stdout, "stderr": result.stderr, "command": result.command}


def _checks(state: AgentState) -> dict[str, Any]:
    check_names = ["static", "model", "dependency_toolchain"]
    if state["config"]["checks"].get("unit_quality_gate"):
        check_names.append("unit_quality_gate")
    checks = {name: state["config"]["checks"].get(name, []) for name in check_names}
    results: dict[str, dict[str, Any]] = {}
    if not state["execute"]:
        return {"stage_results": {name: _result_dict(run_command(argv, state["config"], False,
                                                                    state["task"]["repo_root"], _command_context(state)))
                                   for name, argv in checks.items()}}
    with ThreadPoolExecutor(max_workers=max(1, len(checks)), thread_name_prefix="bms-check") as pool:
        future_map = {pool.submit(run_command, argv, state["config"], True,
                                  state["task"]["repo_root"], _command_context(state)): name
                      for name, argv in checks.items()}
        for future in as_completed(future_map):
            results[future_map[future]] = _result_dict(future.result())
    return {"stage_results": results}


def _build(state: AgentState) -> dict[str, Any]:
    engineering_state = state["task"]["engineering_state"]
    if engineering_state in ("S5", "S7"):
        message = "S5 change workflow does not generate code" if engineering_state == "S5" else "S7 supplies the existing build and configuration record"
        return {"build_status": "not_requested", "stage_results": {"sil_build": {
            "status": "not_applicable", "returncode": None,
            "stdout": message, "stderr": "", "command": []}}}
    command_key = "rebuild" if engineering_state == "S8" else "sil"
    result = run_command(state["config"]["build"].get(command_key, state["config"]["build"].get("sil", [])),
                         state["config"], state["execute"], state["task"]["repo_root"], _command_context(state))
    result_data = _result_dict(result)
    if engineering_state == "S6" and result.status == "passed":
        try:
            output_paths = state["task"].get("output_artifacts", [])
            if not output_paths:
                raise ValueError("S6 build task must declare output_artifacts")
            generated_hashes = artifact_hashes(state["task"]["repo_root"], output_paths)
            result_data["output_hashes"] = generated_hashes
        except (OSError, ValueError) as exc:
            result_data["status"] = "failed"
            result_data["stderr"] = f"Could not record generated artifacts: {exc}"
    if engineering_state == "S8" and result.status == "passed":
        try:
            observed = artifact_hashes(state["task"]["repo_root"], list(state["task"]["expected_output_hashes"]))
            expected = state["task"]["expected_output_hashes"]
            if observed != expected:
                result_data["status"] = "failed"
                result_data["stderr"] = "Reproducibility mismatch: rebuilt output checksums differ from recorded output"
            result_data["output_hashes"] = observed
        except (OSError, ValueError) as exc:
            result_data["status"] = "failed"
            result_data["stderr"] = f"Could not verify rebuilt output checksums: {exc}"
    new_hashes = result_data.get("output_hashes", {}) if result_data["status"] == "passed" else {}
    return {"stage_results": {"sil_build": result_data},
            "artifact_hashes": {**state.get("artifact_hashes", {}), **new_hashes}}


def _integration(state: AgentState) -> dict[str, Any]:
    if state["task"]["engineering_state"] in ("S5", "S7"):
        message = "S5 change workflow does not run the SIL harness" if state["task"]["engineering_state"] == "S5" else "S7 records the existing build; no harness run requested"
        return {"stage_results": {"integration_smoke": {"status": "not_applicable", "returncode": None,
                "stdout": message, "stderr": "", "command": []}}}
    result = run_command(state["config"]["checks"].get("integration_smoke", []), state["config"], state["execute"],
                         state["task"]["repo_root"], _command_context(state))
    return {"stage_results": {"integration_smoke": _result_dict(result)}}


def _merge_stage(state: AgentState, name: str, update: dict[str, Any]) -> AgentState:
    results = {**state.get("stage_results", {}), **update.get("stage_results", {})}
    merged = {**state, **update, "stage_results": results}
    append_audit(merged["config"], {"run_id": merged["run_id"], "stage": name,
                                    "results": update.get("stage_results", {})})
    failures = [(stage, item) for stage, item in results.items()
                if item["status"] in ("failed", "blocked", "unconfigured")]
    if failures:
        failing_name, failing_result = failures[0]
        output = failing_result.get("stderr", "") or failing_result.get("stdout", "")
        merged["failure"] = {"stage": failing_name,
                             "category": classify_failure(failing_name, output),
                             "detail": output or failing_result["status"]}
        merged["build_status"] = "failed" if failing_result["status"] == "failed" else "blocked"
        merged["blocked"] = True
    return merged


def _record(state: AgentState) -> dict[str, Any]:
    cfg_hash = canonical_hash(configuration_record(state))
    path = write_evidence(state)
    append_audit(state["config"], {"run_id": state["run_id"], "event": "evidence_recorded",
                                    "build_status": state["build_status"], "path": path})
    return {"evidence_path": path, "configuration_hash": cfg_hash}


def _preflight_node(state: AgentState) -> AgentState:
    try:
        return {**state, **preflight(state)}
    except Exception as exc:
        state = dict(state)
        state["build_status"] = "blocked"
        state["validation_status"] = "not_performed"
        state["failure"] = {"stage": "preflight", "category": "configuration", "detail": str(exc)}
        state["blocked"] = True
        return state


def _source_node(state: AgentState) -> AgentState:
    try:
        return _merge_stage(state, "source_check", source_check(state))
    except Exception as exc:
        return {**state, "build_status": "failed", "blocked": True,
                "failure": {"stage": "source_check", "category": "infrastructure", "detail": str(exc)}}


def _build_node(state: AgentState) -> AgentState:
    try:
        return _merge_stage(state, "sil_build", _build(state))
    except Exception as exc:
        return {**state, "build_status": "failed", "blocked": True,
                "failure": {"stage": "sil_build", "category": "infrastructure", "detail": str(exc)}}


def _checks_node(state: AgentState) -> AgentState:
    try:
        return _merge_stage(state, "parallel_checks", _checks(state))
    except Exception as exc:
        return {**state, "build_status": "failed", "blocked": True,
                "failure": {"stage": "parallel_checks", "category": "infrastructure", "detail": str(exc)}}


def _integration_node(state: AgentState) -> AgentState:
    try:
        return _merge_stage(state, "integration_smoke", _integration(state))
    except Exception as exc:
        return {**state, "build_status": "failed", "blocked": True,
                "failure": {"stage": "integration_smoke", "category": "infrastructure", "detail": str(exc)}}


def _finish_stages(state: AgentState) -> AgentState:
    if not state.get("blocked"):
        successful_status = {"S5": "checks_passed", "S6": "passed", "S7": "recorded", "S8": "passed"}
        status = successful_status[state["task"]["engineering_state"]] if state["execute"] else "planned"
        state = {**state, "build_status": status,
                 "validation_status": "not_performed"}
    return state


def _record_node(state: AgentState) -> AgentState:
    try:
        return {**state, **_record(state)}
    except FileExistsError as exc:
        return {**state, "build_status": "failed", "blocked": True,
                "failure": {"stage": "record", "category": "infrastructure", "detail": str(exc)}}


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("preflight", _preflight_node)
    graph.add_node("source_check", _source_node)
    graph.add_node("sil_build", _build_node)
    graph.add_node("parallel_checks", _checks_node)
    graph.add_node("integration_smoke", _integration_node)
    graph.add_node("finish", _finish_stages)
    graph.add_node("record", _record_node)
    graph.add_edge(START, "preflight")
    graph.add_conditional_edges("source_check", lambda s: "blocked" if s.get("blocked") else s["task"]["engineering_state"],
                                {"blocked": "record", "S5": "parallel_checks", "S6": "sil_build",
                                 "S7": "finish", "S8": "sil_build"})
    graph.add_conditional_edges("sil_build", lambda s: "blocked" if s.get("blocked") else "continue",
                                {"blocked": "record", "continue": "parallel_checks"})
    graph.add_conditional_edges("parallel_checks", lambda s: "blocked" if s.get("blocked") else "continue",
                                {"blocked": "record", "continue": "integration_smoke"})
    graph.add_edge("integration_smoke", "finish")
    graph.add_edge("finish", "record")
    graph.add_conditional_edges("preflight", lambda s: "blocked" if s.get("blocked") else "ready",
                                {"blocked": "record", "ready": "source_check"})
    graph.add_edge("record", END)
    return graph.compile(checkpointer=MemorySaver())


def execute_task(task: dict[str, Any], config: dict[str, Any], execute: bool) -> AgentState:
    state: AgentState = {"task": task, "config": config, "run_id": uuid.uuid4().hex,
                         "execute": execute, "stage_results": {}, "validation_status": "not_performed"}
    graph = build_graph()
    result = graph.invoke(state, {"configurable": {"thread_id": task["task_id"]}})
    from importlib.resources import files
    from jsonschema import Draft202012Validator, FormatChecker

    schema_resource = files("bms_devops_agent").joinpath("schemas/result.schema.json")
    schema = json.loads(schema_resource.read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(result))
    if errors:
        raise ValueError("Agent result failed result.schema.json validation: " + "; ".join(error.message for error in errors))
    return result


def load_task(path: str | Path) -> dict[str, Any]:
    task = json.loads(Path(path).read_text(encoding="utf-8"))
    from importlib.resources import files
    from jsonschema import Draft202012Validator, FormatChecker

    schema_resource = files("bms_devops_agent").joinpath("schemas/task.schema.json")
    schema = json.loads(schema_resource.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(task),
                    key=lambda error: list(error.absolute_path))
    if errors:
        detail = "; ".join(f"{'.'.join(map(str, error.absolute_path)) or 'task'}: {error.message}"
                           for error in errors)
        raise ValueError(f"Task does not match schemas/task.schema.json: {detail}")
    return task
