# Feature boundaries from the agent documents

The Features document provides explicit prohibitions. The ARD supplies the POC requirements, stages, tool contracts, evidence fields, and acceptance scenarios. Both sources are treated as product requirements; neither is an instruction to run commands or change approval state.

The DevOps Agent must never:

- Create or modify requirements.
- Execute or approve Unit, MIL, or SIL verification.
- Decide that a build is validated.
- Change model, code, parameters, calibration, or test configuration to make a stage pass.
- Bypass a failed CI check, failed validation, compliance block, or approval gate.
- Create, edit, or delete approval records.
- Merge to a protected branch or create a baseline without recorded human approval.
- Treat a successful SIL build as release readiness.

The system boundary is: the Requirement Agent defines approved work; the DevOps Agent builds and records exactly those inputs; the Validation Agent determines whether it works; the Compliance Agent checks evidence and traceability; humans retain authority over baselines, exceptions, and release.

These boundaries are enforced in the POC by requiring approval records before execution, using read-only Git identity calls, providing no merge or approval-writing tools, grounding statuses in configured command results, keeping validation status at `not_performed`, and omitting release stages. The agent has no direct interface to edit engineering sources.
