#!/usr/bin/env python3
"""Execute a project's bounded integration assertions and retain their evidence.

This runner checks execution, not scientific validity or reviewer approval.
See references/aris/integration-checks.md for the project-side contract.

Optional plan field "profile": "triage" additionally requires the TRIAGE check ids; of those only augmentation_sync
and positive_control may be "not_applicable" (with a reason). Without "profile" the five REQUIRED checks apply.

  python3 integration_gate.py PLAN.json --project DIR --output NEW_DIR
Exit 0 = all checks passed (next step: independent review), 1 = a check failed/timed out, 2 = invalid plan or paths,
130 = interrupted.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

REQUIRED = {"interface", "training_path", "data_semantics", "baseline_control", "checkpoint"}
NON_SKIPPABLE = {"interface", "training_path", "data_semantics"}
TRIAGE = {"evaluator_selftest", "input_alignment", "augmentation_sync", "overfit_train_transforms",
          "positive_control", "selection_exposure"}
TRIAGE_SKIPPABLE = {"augmentation_sync", "positive_control"}


def positive_number(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def validate(plan):
    if not isinstance(plan, dict) or plan.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")
    checks = plan.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("checks must be a nonempty list")
    if not positive_number(plan.get("budget_seconds", 300)):
        raise ValueError("budget_seconds must be finite and positive")
    required, non_skippable = REQUIRED, NON_SKIPPABLE
    if "profile" in plan:
        if plan["profile"] != "triage":
            raise ValueError('profile must be "triage" when present')
        required, non_skippable = REQUIRED | TRIAGE, NON_SKIPPABLE | (TRIAGE - TRIAGE_SKIPPABLE)
    seen = set()
    for check in checks:
        if not isinstance(check, dict) or check.get("id") not in required:
            raise ValueError("each check id must name a required check")
        name = check["id"]
        if name in seen:
            raise ValueError(f"duplicate check: {name}")
        seen.add(name)
        if "not_applicable" in check:
            reason = check["not_applicable"]
            if name in non_skippable or "command" in check or not isinstance(reason, str) or not reason.strip():
                raise ValueError(f"invalid not_applicable: {name}")
        else:
            command = check.get("command")
            if not isinstance(command, list) or not command or not all(isinstance(x, str) and x for x in command):
                raise ValueError(f"command must be a nonempty argv array: {name}")
            if not positive_number(check.get("timeout_seconds", 60)):
                raise ValueError(f"invalid timeout_seconds: {name}")
    if seen != required:
        raise ValueError(f"missing checks: {', '.join(sorted(required - seen))}")


def now():
    return datetime.now(timezone.utc).isoformat()


def stop_process(proc):
    # Only the process group created by this runner; never a name-based kill.
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
    except ProcessLookupError:
        pass
    proc.wait()


def run(plan, project, output):
    validate(plan)
    project = Path(project).resolve(strict=True)
    if not project.is_dir():
        raise ValueError("project must be a directory")
    output = Path(output).absolute()
    # A fresh output directory prevents accidentally reusing a previous pass.
    output.mkdir(parents=True, exist_ok=False)
    (output / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
    report = {"status": "blocked", "project": str(project), "started_at": now(),
              "checks": [], "next_step": "fix_checks",
              "meaning": "Execution evidence only; not semantic correctness, independent review, or permission to deploy."}
    deadline = time.monotonic() + plan.get("budget_seconds", 300)
    failed = False
    interrupted = False
    for check in plan["checks"]:
        result = {"id": check["id"]}
        if failed:
            result["status"] = "not_run"
        elif "not_applicable" in check:
            result.update(status="not_applicable", reason=check["not_applicable"])
        else:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                result["status"] = "budget_exhausted"
                failed = True
            else:
                logfile = output / f"{check['id']}.log"
                timeout = min(remaining, check.get("timeout_seconds", 60))
                result.update(command=check["command"], cwd=str(project), started_at=now(),
                              log=str(logfile), timeout_seconds=timeout)
                proc = None
                with logfile.open("wb") as log:
                    try:
                        proc = subprocess.Popen(check["command"], cwd=project,
                                                stdin=subprocess.DEVNULL, stdout=log,
                                                stderr=subprocess.STDOUT,
                                                start_new_session=(os.name == "posix"))
                        code = proc.wait(timeout=timeout)
                        result.update(exit_code=code, status="passed" if code == 0 else "failed")
                    except subprocess.TimeoutExpired:
                        stop_process(proc)
                        result.update(status="timeout", exit_code=proc.returncode)
                    except KeyboardInterrupt:
                        if proc is not None:
                            stop_process(proc)
                        result.update(status="interrupted", exit_code=proc.returncode if proc else None)
                        interrupted = True
                    except OSError as exc:
                        result.update(status="execution_error", error=str(exc))
                    result["finished_at"] = now()
                failed = result["status"] != "passed"
        report["checks"].append(result)
        report["finished_at"] = now()
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    if not failed:
        report.update(status="checks_passed", next_step="independent_review")
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report, 130 if interrupted else (1 if failed else 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New directory; will not overwrite evidence")
    args = parser.parse_args()
    try:
        plan = json.loads(args.plan.read_text())
        report, code = run(plan, args.project, args.output)
    except (ValueError, OSError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": report["status"], "next_step": report["next_step"],
                      "report": str(args.output.absolute() / "report.json")}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
