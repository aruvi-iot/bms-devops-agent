# BMS DevOps Agent POC

This codebase automates the approved DevOps portion of the UC-BMS-SOC-001 proof of concept. It identifies the exact Git revision and input files, runs configured source and CI checks, runs an approved SIL build, performs a build integration smoke check, and writes reproducible configuration evidence.

The agent does not execute or approve Unit, MIL, or SIL verification. It does not declare a build validated or ready for release, change engineering inputs to make a stage pass, bypass failed checks, edit approval records, merge protected branches, or create baselines.

## 1. Project layout

| Path | Purpose |
|---|---|
| `task.json` | The task-specific input you edit for each run |
| `schemas/task.schema.json` | Required task fields and data types |
| `config/devops-agent.example.toml` | Configuration template for commands and toolchain |
| `bms_devops_agent/` | Python workflow implementation |
| `schemas/result.schema.json` | Output contract checked by the agent |
| `evidence/` | Generated configuration, manifest, build record, and audit files |
| `docs/requirements-traceability.md` | Mapping to the ARD requirements |

## 2. Install the codebase

Run these commands from this project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
Copy-Item config\devops-agent.example.toml config\devops-agent.toml
```

The example configuration is intentionally disabled until the approved CI provider, toolchain, runner, and commands are entered.

## 3. Create a new task

For every new build or check, edit `task.json`. Keep one task file per run, or save copies such as `tasks\TASK-SIL-001.json`.

### Task input fields

| Field | Data to enter | Example |
|---|---|---|
| `task_id` | Unique task identifier | `TASK-SIL-001` |
| `engineering_state` | `S5`, `S6`, `S7`, or `S8` | `S6` for an approved SIL build |
| `repo_root` | Absolute path to the actual BMS Git repository | `C:\BMS\soc-project` |
| `source_revision` | Exact checked-out commit | `a1b2c3d4e5f6...` |
| `requirement_set_version` | Approved requirement version | `REQ-0.3.0` |
| `configuration_id` | Approved configuration identity | `CFG-0.3.0` |
| `artifacts` | Relative paths to approved inputs | `src/model.slx`, `config/CALCE.mat` |
| `expected_artifact_hashes` | SHA-256 for every item in `artifacts` | `64-character SHA-256 value` |
| `output_artifacts` | Generated code/build files; required for S6 | `build/generated_code.c` |
| `expected_output_hashes` | Previously recorded output hashes; required for S8 | `{ "build/generated_code.c": "..." }` |
| `configuration` | Target, tool versions, harness, parameters | `{ "target": "SIL" }` |
| `approvals.configuration` | Existing human approval for the configuration | Scope must equal `configuration_id` |
| `approvals.code_generation` | Existing human approval for SIL code generation | Required for S6; scope is `SIL code generation` |
| `validation_status` | Always `not_performed` | `not_performed` |

Approval records refer to decisions already made by a human or approved system. The agent records them; it does not create or edit them.

### How to obtain Git revision and hashes

From the BMS repository, run:

```powershell
git rev-parse HEAD
Get-FileHash .\src\model.slx -Algorithm SHA256
Get-FileHash .\config\CALCE.mat -Algorithm SHA256
```

Copy the exact commit into `source_revision`. Copy each file’s `Hash` value into `expected_artifact_hashes` using the same relative path as `artifacts`.

### Minimal S5 example

S5 runs checks on a change and does not generate code:

```json
{
  "task_id": "TASK-CHANGE-001",
  "engineering_state": "S5",
  "repo_root": "C:\\BMS\\soc-project",
  "source_revision": "a1b2c3d4e5f6",
  "requirement_set_version": "REQ-0.3.0",
  "configuration_id": "CFG-0.3.0",
  "artifacts": ["src/model.slx"],
  "expected_artifact_hashes": {
    "src/model.slx": "PUT_THE_REAL_64_CHARACTER_SHA256_HASH_HERE"
  },
  "approvals": {
    "configuration": {
      "approval_id": "REV-001",
      "actor": "reviewer@example.com",
      "role": "Technical Reviewer",
      "approved_at": "2026-10-26T10:00:00Z",
      "scope": "CFG-0.3.0"
    }
  },
  "validation_status": "not_performed"
}
```

### S6 additions

For S6, add `output_artifacts` and a `code_generation` approval. The SIL build command in the TOML configuration must create those output files. The agent hashes them after the build and places them in the evidence manifest.

### S8 additions

For an S8 reproducibility rebuild, add `expected_output_hashes` from the original recorded build. The agent compares the rebuilt output hashes and reports drift if they differ.

## 4. Configure the commands

Edit `config/devops-agent.toml`:

| Configuration | What you enter | Example |
|---|---|---|
| `runner.enabled` | `true` only after approvals and runner setup | `true` |
| `runner.provider` | Approved provider | `github-actions` |
| `[toolchain]` | Installed product/version/license record | MATLAB R2023b |
| `checks.source` | Source check command as an argument array | `["python", "tools/check_source.py"]` |
| `checks.static` | Static check command | `["python", "tools/static_check.py"]` |
| `checks.model` | Model check command | `["matlab", "-batch", "runModelChecks"]` |
| `checks.unit_quality_gate` | Optional CI quality gate only | `["python", "tools/unit_gate.py"]` |
| `checks.dependency_toolchain` | Dependency/toolchain check | `["python", "tools/check_toolchain.py"]` |
| `checks.integration_smoke` | SIL harness load/run smoke check only | `["python", "tools/sil_smoke.py"]` |
| `build.sil` | Approved SIL build command | `["matlab", "-batch", "runApprovedSilBuild"]` |
| `agent.evidence_dir` | Evidence output directory | `"./evidence"` |

Commands are arrays, not shell strings. Empty commands are treated as unconfigured during execution and block the run. The integration command must not run Unit, MIL, or SIL verification.

## 5. Run a task

Always run a plan first:

```powershell
bms-devops-agent run task.json --config config\devops-agent.toml
```

After reviewing the planned commands, approvals, and inputs, execute:

```powershell
bms-devops-agent run task.json --config config\devops-agent.toml --execute
```

The process runs from the task’s `repo_root`. The repository must be clean and its current `HEAD` must equal `source_revision`. The agent never checks out another revision or modifies source files.

## 6. What the agent produces

Each run creates a unique folder under `evidence/`:

| Output | Meaning |
|---|---|
| `configuration.json` | Configuration ID, source commit, input hashes, approvals, toolchain, and task configuration |
| `manifest.json` | Artifact names, versions, and SHA-256 values |
| `build-record.json` | Task/run IDs, stage statuses, logs, build status, configuration hash, and failure details |
| `audit.jsonl` | Append-only record of stage actions and evidence creation |

Typical statuses are `planned`, `checks_passed`, `passed`, `recorded`, `failed`, or `blocked`. `validation_status` remains `not_performed` because validation belongs to the Validation Agent.

## 7. Common blocked-run causes

- The repository has uncommitted changes.
- `source_revision` is not the current `HEAD`.
- An artifact hash does not match the approved hash.
- A required human approval is missing or has the wrong scope.
- A command is empty, the runner is disabled, or a command returns a nonzero exit code.
- S6 does not declare generated output files.
- S8 does not provide expected output hashes.

The POC is intentionally fail-closed: a failed check is preserved in evidence and blocks downstream stages.

## 8. Scope and limitations

The POC does not include CI-provider integration, persistent LangGraph checkpoints, release packaging, deployment, HIL, approval authentication, or a MATLAB project. Those require the open decisions DA-OI-01 through DA-OI-08 from the ARD and project-specific infrastructure.
