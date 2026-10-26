from __future__ import annotations

import subprocess
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CommandResult:
    status: str
    returncode: int | None
    stdout: str
    stderr: str
    command: list[str]


def run_command(argv: list[str], config: dict[str, Any], execute: bool,
                cwd: str | None = None, context: dict[str, str] | None = None) -> CommandResult:
    if not argv:
        status = "unconfigured" if execute else "planned"
        return CommandResult(status, None, "", "No approved command is configured", [])
    if not execute:
        return CommandResult("planned", None, "", "Plan only; command not executed", argv)
    if not config["runner"].get("enabled", False):
        return CommandResult("blocked", None, "", "Runner is disabled", argv)
    timeout = config["agent"].get("command_timeout_seconds", 1800)
    max_bytes = config["agent"].get("max_log_bytes", 200000)
    try:
        environment = os.environ.copy()
        environment.update(context or {})
        result = subprocess.run(argv, capture_output=True, text=True, shell=False,
                                timeout=timeout, check=False,
                                cwd=str(Path(cwd).resolve()) if cwd else None,
                                env=environment)
        status = "passed" if result.returncode == 0 else "failed"
        return CommandResult(status, result.returncode, result.stdout[-max_bytes:],
                             result.stderr[-max_bytes:], argv)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return CommandResult("failed", None, stdout[-max_bytes:],
                             (stderr + "\nCommand timed out").strip()[-max_bytes:], argv)
    except OSError as exc:
        return CommandResult("failed", None, "", str(exc), argv)
