from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any


class ConfigurationError(ValueError):
    pass


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).resolve()
    with config_path.open("rb") as stream:
        data = tomllib.load(stream)
    for section in ("agent", "runner", "checks", "build", "policy"):
        if not isinstance(data.get(section), dict):
            raise ConfigurationError(f"Missing [{section}] section in {config_path}")
    timeout = data["agent"].get("command_timeout_seconds", 1800)
    if not isinstance(timeout, int) or timeout < 1 or timeout > 86400:
        raise ConfigurationError("command_timeout_seconds must be between 1 and 86400")
    max_log_bytes = data["agent"].get("max_log_bytes", 200000)
    if not isinstance(max_log_bytes, int) or max_log_bytes < 1024 or max_log_bytes > 10_000_000:
        raise ConfigurationError("max_log_bytes must be between 1024 and 10000000")
    if not isinstance(data["runner"].get("enabled"), bool):
        raise ConfigurationError("runner.enabled must be a boolean")
    for section in ("checks", "build"):
        for name, argv in data[section].items():
            if not isinstance(argv, list) or any(not isinstance(part, str) or not part for part in argv):
                raise ConfigurationError(f"[{section}].{name} must be an argv array of non-empty strings")
    return data
