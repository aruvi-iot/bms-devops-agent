from __future__ import annotations

from typing import Any, Literal, TypedDict


class Approval(TypedDict):
    approval_id: str
    actor: str
    role: str
    approved_at: str
    scope: str


class Task(TypedDict, total=False):
    task_id: str
    engineering_state: Literal["S5", "S6", "S7", "S8"]
    repo_root: str
    source_revision: str
    requirement_set_version: str
    configuration_id: str
    artifacts: list[str]
    output_artifacts: list[str]
    expected_artifact_hashes: dict[str, str]
    expected_output_hashes: dict[str, str]
    configuration: dict[str, Any]
    approvals: dict[str, Approval]
    validation_status: str
    validation_passed: bool
    compliance_blocked: bool


class AgentState(TypedDict, total=False):
    task: Task
    config: dict[str, Any]
    run_id: str
    execute: bool
    stage_results: dict[str, dict[str, Any]]
    source_commit: str
    artifact_hashes: dict[str, str]
    configuration_hash: str
    build_status: str
    validation_status: str
    blocked: bool
    failure: dict[str, Any]
    evidence_path: str
    messages: list[str]
