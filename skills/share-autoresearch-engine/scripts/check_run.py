#!/usr/bin/env python3
"""Check development-stage admission for a run.

This is not a final test-evaluation receipt: it requires `test_read: false`
and a sealed `test_read.flag`. After the test is opened, use a separate
final-test receipt instead of this checker.

Usage: python scripts/check_run.py <run_dir> [--strict] [--allow-censored]
Exit 0 = development-stage eligible, 2 = blocked, 1 = usage/parse error.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from pathlib import Path

import yaml

from audit_curve import classify

REQUIRED = (
    "git_commit",
    "git_dirty",
    "config_path",
    "config_sha256",
    "resolved_config_path",
    "resolved_config_sha256",
    "data_path",
    "data_sha256",
    "split_seed",
    "train_seed",
    "budget_max_steps",
    "best_step",
    "best_val_loss",
    "best_at_cap",
    "curve_verdict",
    "test_read",
)
ALLOWED_VERDICTS = {"TURNED_UP", "PLATEAU"}
MAX_HASH_BYTES = 2 * 1024**3


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _block(message: str) -> int:
    print(f"BLOCKED: {message}", file=sys.stderr)
    return 2


def main() -> int:
    flags = {a for a in sys.argv[1:] if a in {"--strict", "--allow-censored"}}
    args = [a for a in sys.argv[1:] if a not in flags]
    strict = "--strict" in flags
    allow_censored = "--allow-censored" in flags
    if len(args) != 1:
        print("usage: check_run.py <run_dir> [--strict] [--allow-censored]", file=sys.stderr)
        return 1
    run_dir = Path(args[0])
    manifest_path = run_dir / "manifest.yaml"
    if not manifest_path.exists():
        return _block(f"missing {manifest_path}")
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    missing = [key for key in REQUIRED if key not in manifest or manifest[key] in (None, "")]
    if missing:
        return _block(f"manifest missing {missing}")
    resolved_path = manifest["resolved_config_path"]
    resolved_sha = manifest["resolved_config_sha256"]
    if not isinstance(resolved_path, str) or not resolved_path.strip():
        return _block("resolved_config_path must be a nonempty string")
    if not isinstance(resolved_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", resolved_sha):
        return _block("resolved_config_sha256 must be 64 lowercase hex characters")
    if manifest["test_read"] is not False:
        return _block("test_read is not false; this checker is development-stage only")
    if (run_dir / "test_read.flag").exists():
        return _block("test_read.flag exists; use a final-test receipt, not this checker")
    if str(manifest["git_commit"]).lower() in {"unknown", "none", ""}:
        return _block("git_commit is unknown")

    try:
        budget = int(manifest["budget_max_steps"])
        best_step = int(manifest["best_step"])
    except (TypeError, ValueError):
        return _block("budget_max_steps/best_step are not integers")
    if budget <= 0:
        return _block("budget_max_steps <= 0; max_epochs-only runs are not eligible")
    if best_step <= 0:
        return _block("best_step <= 0")

    config_path = Path(str(manifest["config_path"]))
    if not config_path.is_file():
        return _block(f"config_path missing: {config_path}")
    if _sha256(config_path) != manifest["config_sha256"]:
        return _block("config_sha256 does not match config_path")
    resolved_file = Path(resolved_path)
    if not resolved_file.is_absolute():
        resolved_file = run_dir / resolved_file
    if not resolved_file.is_file():
        return _block(f"resolved_config_path missing: {resolved_file}")
    if _sha256(resolved_file) != resolved_sha:
        return _block("resolved_config_sha256 does not match resolved_config_path")

    data_path = Path(str(manifest["data_path"]))
    if not data_path.is_file():
        return _block(f"data_path missing: {data_path}")
    if data_path.stat().st_size <= MAX_HASH_BYTES:
        if _sha256(data_path) != manifest["data_sha256"]:
            return _block("data_sha256 does not match data_path")
    else:
        print("WARN: data file > 2 GiB; data_sha256 not recomputed", file=sys.stderr)

    guard_path = run_dir / "budget_guard.json"
    if not guard_path.exists():
        return _block(f"missing {guard_path}")
    guard = json.loads(guard_path.read_text(encoding="utf-8"))
    if "best_at_cap" not in guard or "history" not in guard:
        return _block("budget_guard.json missing best_at_cap/history")
    if int(guard.get("max_steps", -1)) != budget:
        return _block("budget_guard max_steps does not match manifest")
    if int(guard.get("best_step", -1)) != best_step:
        return _block("best_step mismatch between manifest and budget_guard")
    if not math.isclose(float(guard.get("best_val_loss")), float(manifest["best_val_loss"]), rel_tol=1e-9, abs_tol=1e-12):
        return _block("best_val_loss mismatch between manifest and budget_guard")

    history = guard["history"]
    if len(history) < 3:
        return _block("fewer than 3 validation points")
    try:
        pairs = [(float(row["step"]), float(row["val_loss"])) for row in history]
    except (KeyError, TypeError, ValueError):
        return _block("history has non-numeric step/val_loss")
    if not all(math.isfinite(step) and math.isfinite(loss) for step, loss in pairs):
        return _block("history has non-finite step/val_loss")
    if any(later < earlier for (earlier, _), (later, _) in zip(pairs, pairs[1:])):
        return _block("history steps are not non-decreasing")
    min_loss = min(loss for _, loss in pairs)
    history_best_step = min(step for step, loss in pairs if math.isclose(loss, min_loss, rel_tol=1e-12, abs_tol=1e-15))
    if history_best_step != best_step:
        return _block("best_step does not match history minimum")
    if not math.isclose(min_loss, float(manifest["best_val_loss"]), rel_tol=1e-9, abs_tol=1e-12):
        return _block("best_val_loss does not match history minimum")
    verdict = classify(history, bool(guard.get("best_at_cap")))
    allowed_verdicts = ALLOWED_VERDICTS | ({"BEST_AT_CAP"} if allow_censored else set())
    if verdict not in allowed_verdicts:
        return _block(f"curve verdict is {verdict}")
    if manifest.get("curve_verdict") != verdict:
        return _block("manifest curve_verdict does not match recomputed verdict")

    audit_path = run_dir / "curve_audit.json"
    if not audit_path.exists():
        return _block(f"missing {audit_path}")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("verdict") != verdict:
        return _block("curve_audit verdict does not match recomputed verdict")
    if int(audit.get("best_step", -1)) != best_step:
        return _block("curve_audit best_step mismatch")
    if not math.isclose(float(audit.get("best_val_loss")), float(manifest["best_val_loss"]), rel_tol=1e-9, abs_tol=1e-12):
        return _block("curve_audit best_val_loss mismatch")

    # Recompute the cap from history; never trust the self-reported boolean alone.
    recomputed_cap = best_step >= budget
    if recomputed_cap and not allow_censored:
        return _block("BEST_AT_CAP recomputed; use --allow-censored only for a clearly labeled fixed-budget comparison")
    if recomputed_cap:
        print("WARN: BEST_AT_CAP; result is right-censored, not evidence of convergence", file=sys.stderr)
    if bool(manifest.get("best_at_cap")) != recomputed_cap or bool(guard.get("best_at_cap")) != recomputed_cap:
        return _block("best_at_cap flags inconsistent with recomputed cap")

    git_dirty = manifest.get("git_dirty") is True
    if git_dirty:
        print("WARN: git_dirty=true; provenance is recorded but the tree is not reproducible", file=sys.stderr)
        if strict:
            return _block("git_dirty=true under --strict")

    print(
        json.dumps(
            {
                "eligible": True,
                "stage": "development",
                "censored": recomputed_cap,
                "best_step": best_step,
                "best_val_loss": manifest["best_val_loss"],
                "budget_max_steps": budget,
                "curve_verdict": verdict,
                "test_read": manifest["test_read"],
                "git_dirty": git_dirty,
                "claim_eligible": not git_dirty,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
