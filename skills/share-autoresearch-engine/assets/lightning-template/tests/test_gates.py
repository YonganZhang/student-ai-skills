"""Tests for the two skill-level gates."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
CHECK = ROOT / "scripts" / "check_run.py"
AUDIT = ROOT / "scripts" / "audit_curve.py"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_run(run_dir: Path, *, test_read: bool = False, best_at_cap: bool = False, best_step: int = 5) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    config = run_dir / "config.yaml"
    resolved = run_dir / "resolved_config.yaml"
    data = run_dir / "data.npz"
    config.write_text("seed: 17\n", encoding="utf-8")
    resolved.write_text("seed: 17\noutput_dir: runs/x\n", encoding="utf-8")
    data.write_bytes(b"fake-npz")
    verdict = "BEST_AT_CAP" if best_at_cap else "TURNED_UP"
    manifest = {
        "git_commit": "abc",
        "git_dirty": False,
        "config_path": str(config),
        "config_sha256": sha(config),
        "resolved_config_path": str(resolved),
        "resolved_config_sha256": sha(resolved),
        "data_path": str(data),
        "data_sha256": sha(data),
        "split_seed": 17,
        "train_seed": 17,
        "budget_max_steps": 10,
        "best_step": best_step,
        "best_val_loss": 0.5,
        "best_at_cap": best_at_cap,
        "curve_verdict": verdict,
        "test_read": test_read,
    }
    (run_dir / "manifest.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")
    guard = {
        "best_step": best_step,
        "best_val_loss": 0.5,
        "max_steps": 10,
        "best_at_cap": best_at_cap,
        "history": [
            {"step": 2, "val_loss": 0.8},
            {"step": 5, "val_loss": 0.5 if best_step == 5 else 0.9},
            {"step": 10, "val_loss": 0.5 if best_step == 10 else 0.9},
        ],
    }
    (run_dir / "budget_guard.json").write_text(json.dumps(guard), encoding="utf-8")
    audit = {
        "verdict": verdict,
        "n_validations": 3,
        "best_step": best_step,
        "best_val_loss": 0.5,
        "last_val_loss": 0.9,
    }
    (run_dir / "curve_audit.json").write_text(json.dumps(audit), encoding="utf-8")


def run(script: Path, arg: Path, *flags: str) -> int:
    return subprocess.run([sys.executable, str(script), str(arg), *flags], capture_output=True).returncode


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="dl-gates-") as tmp:
        root = Path(tmp)
        ok = root / "ok"
        write_run(ok)
        assert run(CHECK, ok) == 0
        assert run(AUDIT, ok / "budget_guard.json") == 0

        capped = root / "capped"
        write_run(capped, best_at_cap=True, best_step=10)
        assert run(CHECK, capped) == 2
        assert run(CHECK, capped, "--allow-censored") == 0
        assert run(AUDIT, capped / "budget_guard.json") == 2

        forged_cap = root / "forged_cap"
        write_run(forged_cap, best_at_cap=False, best_step=10)
        assert run(CHECK, forged_cap) == 2

        mismatch = root / "mismatch"
        write_run(mismatch, best_step=5)
        guard_path = mismatch / "budget_guard.json"
        guard = json.loads(guard_path.read_text(encoding="utf-8"))
        guard["history"] = [
            {"step": 2, "val_loss": 0.8},
            {"step": 5, "val_loss": 0.9},
            {"step": 10, "val_loss": 0.5},
        ]
        guard_path.write_text(json.dumps(guard), encoding="utf-8")
        assert run(CHECK, mismatch) == 2

        contaminated = root / "contaminated"
        write_run(contaminated, test_read=True)
        assert run(CHECK, contaminated) == 2

        decreasing = root / "decreasing.json"
        decreasing.write_text(
            json.dumps(
                {
                    "best_step": 10,
                    "best_val_loss": 0.8,
                    "max_steps": 20,
                    "best_at_cap": False,
                    "history": [
                        {"step": 5, "val_loss": 1.0},
                        {"step": 10, "val_loss": 0.8},
                        {"step": 15, "val_loss": 0.8},
                    ],
                }
            ),
            encoding="utf-8",
        )
        assert run(AUDIT, decreasing) == 2

        corrupted = root / "corrupted_data"
        write_run(corrupted)
        (corrupted / "data.npz").write_bytes(b"different")
        assert run(CHECK, corrupted) == 2

        resolved_tamper = root / "resolved_tamper"
        write_run(resolved_tamper)
        (resolved_tamper / "resolved_config.yaml").write_text("seed: 18\n", encoding="utf-8")
        assert run(CHECK, resolved_tamper) == 2

        portable = root / "portable"
        write_run(portable)
        manifest_path = portable / "manifest.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        manifest["resolved_config_path"] = "resolved_config.yaml"
        manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
        assert run(CHECK, portable) == 0

        false_resolved = root / "false_resolved"
        write_run(false_resolved)
        manifest_path = false_resolved / "manifest.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        manifest["resolved_config_path"] = False
        manifest["resolved_config_sha256"] = False
        manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
        assert run(CHECK, false_resolved) == 2

        bad_sha = root / "bad_resolved_sha"
        write_run(bad_sha)
        manifest_path = bad_sha / "manifest.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        manifest["resolved_config_sha256"] = "0" * 63
        manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
        assert run(CHECK, bad_sha) == 2

        missing_resolved = root / "missing_resolved"
        write_run(missing_resolved)
        manifest_path = missing_resolved / "manifest.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        del manifest["resolved_config_path"]
        manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
        assert run(CHECK, missing_resolved) == 2

        no_guard = root / "no_guard"
        write_run(no_guard)
        (no_guard / "budget_guard.json").unlink()
        assert run(CHECK, no_guard) == 2

        short = root / "short"
        write_run(short, best_step=5)
        (short / "budget_guard.json").write_text(
            json.dumps({"best_step": 5, "best_at_cap": False, "history": [{"step": 5, "val_loss": 0.5}]}),
            encoding="utf-8",
        )
        assert run(AUDIT, short / "budget_guard.json") == 2
    print("ok gates: eligible, cap, forged_cap, test_read, decreasing, data_hash, resolved_hash, missing_or_false_resolved_config, missing_guard, insufficient")


if __name__ == "__main__":
    main()
