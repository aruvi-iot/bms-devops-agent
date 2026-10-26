# ARD requirement traceability

This codebase is a POC implementation scaffold. Requirement IDs below refer to BMS-AI-ARD-04 v1.0. “Implemented” means code paths and fail-closed behavior are present; this is not a claim that the ARD acceptance tests have been run.

| ARD requirements | Code / behavior |
| --- | --- |
| DA-001, DA-004, DA-005 | `git.py`, `evidence.py`: repository-derived revision and file checksums |
| DA-002, DA-003, DA-006 | No protected-branch merge/baseline/history rewrite interface; evidence is unique and append-only |
| DA-007, DA-008 | `workflow.py`: S6 requires code-generation and configuration approvals before build |
| DA-009, DA-022, DA-024, DA-027 | `evidence.py`: configuration record, toolchain config snapshot, manifest and hashes |
| DA-010, DA-014, DA-015 | CI quality checks plus separate integration smoke check; output only says build passed; validation is not performed |
| DA-011 | Checksum comparison helper is provided for operator-declared reproducibility inputs; exclusions must be explicit |
| DA-012, DA-013 | `workflow.py`: S5 skips generation; independent configured checks run concurrently and gate subsequent stages |
| DA-016, DA-017, DA-020, DA-021 | Stage exit/result verification, categorized failure and preserved run logs/records |
| DA-018, DA-019 | Retries and corrective edits are not implemented; failed stages stop and report |
| DA-023, DA-025, DA-026 | Configuration artifact identity and tool-derived checksums are recorded; tasks require approved expected hashes and drift check compares expected and observed checksums |
| DA-028, DA-029 | Retrieval is not enabled; status is grounded in tool outcomes. Knowledge retrieval can be added after the controlled KB is supplied |
| DA-030, DA-031 | Schema-validated task/result objects and explicit incoming validation/compliance gate fields |
| DA-032, DA-033, DA-034, DA-035 | LangGraph in-memory checkpoints, audit logging, explicit execute gate; no approval-writing or merge API. Durable checkpoints and deployment identity permissions remain deployment work |
| DA-036–DA-039 | Later phase; no release packaging, deployment, HIL, or release workflow |

## Open decisions

DA-OI-01 to DA-OI-08 are intentionally not invented. The sample config disables execution until the CI provider, licensed runner, branch policy, retry policy, reproducible-build exclusions, code-generation interface, checks, and ID patterns are approved. The document supplied does not include the other three agent schemas or the frozen solution/knowledge-base files, so inter-agent payloads are represented by a small local contract and require project-owner alignment.

The approval records are structurally validated but their source is not authenticated in this POC. Before enabling an execution runner, connect task approvals to the authorized Orchestrator or approval store and run the agent under a dedicated least-privilege identity.

## Task approval contract

`approvals.configuration` must contain an approval whose `scope` exactly matches `configuration_id`. For S6, `approvals.code_generation.scope` must be `SIL code generation`. Each record carries the source-system approval ID, actor, role, and ISO 8601 approval time. These are references to existing human decisions; the agent does not create or edit them. The current POC checks their structure and scope only, not their authenticity or revocation status.
