from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import AgentState


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def artifact_hashes(repo_root: str, artifacts: list[str]) -> dict[str, str]:
    root = Path(repo_root).resolve(strict=True)
    result: dict[str, str] = {}
    for relative in artifacts:
        target = (root / relative).resolve(strict=True)
        if not target.is_relative_to(root) or not target.is_file():
            raise ValueError(f"Artifact must be a file inside the repository: {relative}")
        result[relative] = sha256_file(target)
    return result


def classify_failure(stage: str, output: str) -> str:
    text = output.lower()
    if any(word in text for word in ("license", "matlab", "compiler", "toolchain")):
        return "toolchain"
    if any(word in text for word in ("dependency", "package not found", "module not found")):
        return "dependency"
    if any(word in text for word in ("configuration", "config id", "cfg-")):
        return "configuration"
    if "model" in text:
        return "model"
    if "code generation" in text or "codegen" in text:
        return "code_generation"
    if any(word in text for word in ("timeout", "connection", "runner unavailable")):
        return "infrastructure"
    return "unknown"


def configuration_record(state: AgentState) -> dict[str, Any]:
    task = state["task"]
    config = state["config"]
    return {
        "configuration_id": task["configuration_id"],
        "requirement_set_version": task.get("requirement_set_version", "unspecified"),
        "source_commit": state.get("source_commit"),
        "artifacts": state.get("artifact_hashes", {}),
        "task_configuration": task.get("configuration", {}),
        "approvals": task.get("approvals", {}),
        "toolchain": config.get("toolchain", {}),
        "runner": config.get("runner", {}),
    }


def write_evidence(state: AgentState) -> str:
    task = state["task"]
    config = state["config"]
    evidence_root = Path(config["agent"].get("evidence_dir", "./evidence")).resolve()
    run_id = state["run_id"]
    if not re.fullmatch(r"[A-Za-z0-9._-]+", run_id):
        raise ValueError("Invalid run ID")
    run_dir = evidence_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    configuration = configuration_record(state)
    cfg_hash = canonical_hash(configuration)
    record = {
        "task_id": task["task_id"],
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "engineering_state": task["engineering_state"],
        "source_commit": state.get("source_commit"),
        "configuration_id": task["configuration_id"],
        "configuration_hash": cfg_hash,
        "configuration_record": configuration,
        "manifest": [
            {"name": path, "version": state.get("source_commit"), "sha256": checksum}
            for path, checksum in sorted(state.get("artifact_hashes", {}).items())
        ],
        "stage_results": state.get("stage_results", {}),
        "build_status": state.get("build_status", "blocked"),
        "validation_status": "not_performed",
        "failure": state.get("failure"),
    }
    (run_dir / "configuration.json").write_text(json.dumps(configuration, indent=2), encoding="utf-8")
    (run_dir / "manifest.json").write_text(json.dumps(record["manifest"], indent=2), encoding="utf-8")
    (run_dir / "build-record.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return str(run_dir)


def append_audit(config: dict[str, Any], event: dict[str, Any]) -> None:
    path = Path(config["agent"].get("audit_file", "./evidence/audit.jsonl")).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    item = {"timestamp": datetime.now(timezone.utc).isoformat(), **event}
    # O_APPEND prevents replacing earlier audit records; deployment storage should
    # enforce append-only permissions for the agent identity.
    descriptor = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(item, sort_keys=True) + "\n")
