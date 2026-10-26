from __future__ import annotations

import argparse
import json
import sys

from .config import load_config
from .workflow import execute_task, load_task


def main() -> int:
    parser = argparse.ArgumentParser(prog="bms-devops-agent")
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run", help="Plan or execute an approved POC task")
    run_parser.add_argument("task", help="Path to task JSON")
    run_parser.add_argument("--config", required=True, help="Operator TOML configuration")
    run_parser.add_argument("--execute", action="store_true", help="Execute configured commands")
    args = parser.parse_args()
    try:
        task = load_task(args.task)
        config = load_config(args.config)
        result = execute_task(task, config, args.execute)
    except Exception as exc:
        print(json.dumps({"build_status": "blocked", "validation_status": "not_performed",
                          "error": str(exc)}, indent=2), file=sys.stderr)
        return 2
    output = {key: result.get(key) for key in (
        "run_id", "build_status", "validation_status", "configuration_hash", "failure", "evidence_path"
    )}
    output["stage_results"] = {
        name: {"status": item.get("status"), "returncode": item.get("returncode")}
        for name, item in result.get("stage_results", {}).items()
    }
    print(json.dumps(output, indent=2))
    return 0 if result.get("build_status") in ("passed", "planned", "recorded", "checks_passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
