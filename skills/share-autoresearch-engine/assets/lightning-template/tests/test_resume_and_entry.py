"""Regression checks for resume state, output preflight, and the structure entry gate."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import torch
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.callbacks import BudgetGuard
from pipeline.train import (
    check_resume_budget,
    check_selection_recipe,
    check_structure_config,
    next_resolved_path,
    preflight_output,
    resolve_resume_path,
    selection_recipe,
    validate_resume_lineage,
)


class FakeTrainer:
    is_global_zero = True
    max_steps = 20

    def __init__(self, step: int, loss: float):
        self.global_step = step
        self.callback_metrics = {"val/loss": loss}


class ResumeAndPreflightTest(unittest.TestCase):
    def test_guard_state_survives_resume_and_legacy_artifact(self):
        with tempfile.TemporaryDirectory(prefix="dl-resume-") as tmp:
            out = Path(tmp)
            guard = BudgetGuard(out)
            guard.on_validation_end(FakeTrainer(5, 0.1), None)
            state = guard.state_dict()

            resumed = BudgetGuard(out)
            resumed.load_state_dict(state)
            resumed.on_validation_end(FakeTrainer(15, 0.8), None)
            self.assertEqual(resumed.best_step, 5)
            self.assertAlmostEqual(resumed.best_loss, 0.1)
            self.assertEqual([row["step"] for row in resumed.history], [5, 15])

            legacy = BudgetGuard(out)
            legacy.on_train_start(FakeTrainer(15, 0.8), None)
            self.assertEqual(legacy.best_step, 5)
            self.assertAlmostEqual(legacy.best_loss, 0.1)

    def test_existing_run_is_not_touched(self):
        with tempfile.TemporaryDirectory(prefix="dl-preflight-") as tmp:
            out = Path(tmp)
            manifest = out / "manifest.yaml"
            resolved = out / "resolved_config.yaml"
            manifest.write_text("old: manifest\n", encoding="utf-8")
            resolved.write_text("old: resolved\n", encoding="utf-8")
            before = (manifest.read_bytes(), resolved.read_bytes())
            with self.assertRaises(SystemExit):
                preflight_output(out, resume=False, test_read_flag=out / "test_read.flag")
            self.assertEqual((manifest.read_bytes(), resolved.read_bytes()), before)
            self.assertEqual(
                next_resolved_path(out, resume=True).name,
                "resolved_config.resume-1.yaml",
            )

    def test_lr_and_seed_changes_do_not_require_a_structure_card(self):
        with tempfile.TemporaryDirectory(prefix="dl-baseline-") as tmp:
            cfg = yaml.safe_load((ROOT / "configs" / "points.yaml").read_text(encoding="utf-8"))
            cfg["module"]["lr"] = 0.002
            cfg["seed"] = 18
            cfg["split_seed"] = 18
            config = Path(tmp) / "tuned.yaml"
            config.write_text(yaml.safe_dump(cfg), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, "-m", "pipeline.train", "--config", str(config), "--validate-only"],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("structure_gate_ok", proc.stdout)

    def test_resume_budget_change_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="dl-budget-") as tmp:
            out = Path(tmp)
            (out / "manifest.yaml").write_text(
                yaml.safe_dump({"budget_max_steps": 6}), encoding="utf-8"
            )
            with self.assertRaises(SystemExit):
                check_resume_budget(out, 8)

    def test_selection_recipe_is_immutable_for_a_run(self):
        with tempfile.TemporaryDirectory(prefix="dl-recipe-") as tmp:
            out = Path(tmp)
            cfg = yaml.safe_load((ROOT / "configs" / "points.yaml").read_text(encoding="utf-8"))
            recipe = selection_recipe(cfg)
            (out / "selection_recipe.json").write_text(json.dumps(recipe), encoding="utf-8")
            check_selection_recipe(out, recipe, resume=True)
            changed = {"module": dict(recipe["module"]), "data_target_dtypes": None}
            changed["module"]["loss"] = "mae"
            with self.assertRaises(SystemExit):
                check_selection_recipe(out, changed, resume=True)
            dtype_changed = {"module": dict(recipe["module"]), "data_target_dtypes": {"recon": "int64"}}
            with self.assertRaises(SystemExit):
                check_selection_recipe(out, dtype_changed, resume=True)

    def test_resume_lineage_rejects_moved_and_stale_checkpoints(self):
        with tempfile.TemporaryDirectory(prefix="dl-lineage-") as tmp:
            out = Path(tmp) / "run"
            ckpt_dir = out / "checkpoints"
            ckpt_dir.mkdir(parents=True)
            moved = Path(tmp) / "old" / "checkpoints"
            moved.mkdir(parents=True)
            payload = {
                "global_step": 3,
                "callbacks": {
                    "ModelCheckpoint{}": {"dirpath": str(moved)},
                    "BudgetGuard": {"best_step": 2, "best_loss": 0.1, "history": []},
                },
            }
            torch.save(payload, ckpt_dir / "last.ckpt")
            with self.assertRaises(SystemExit):
                validate_resume_lineage(out, ckpt_dir / "last.ckpt")

            payload["callbacks"]["ModelCheckpoint{}"]["dirpath"] = str(ckpt_dir)
            torch.save(payload, ckpt_dir / "last.ckpt")
            (out / "budget_guard.json").write_text(
                json.dumps({"best_step": 4, "best_val_loss": 0.05, "history": []}),
                encoding="utf-8",
            )
            with self.assertRaises(SystemExit):
                validate_resume_lineage(out, ckpt_dir / "last.ckpt")

            (out / "budget_guard.json").unlink()
            with self.assertRaises(SystemExit):
                validate_resume_lineage(out, ckpt_dir / "last.ckpt")

    def test_custom_selector_is_rejected_before_output_dir_exists(self):
        with tempfile.TemporaryDirectory(prefix="dl-selector-") as tmp:
            out = Path(tmp) / "run"
            cfg = yaml.safe_load((ROOT / "configs" / "points.yaml").read_text(encoding="utf-8"))
            cfg["checkpoint_monitor"] = "val/mae"
            config = Path(tmp) / "selector.yaml"
            config.write_text(yaml.safe_dump(cfg), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, "-m", "pipeline.train", "--config", str(config), "--max-steps", "10",
                 "--output-dir", str(out)],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertFalse(out.exists(), proc.stdout + proc.stderr)

    def test_baseline_cannot_hide_a_model_change(self):
        with tempfile.TemporaryDirectory(prefix="dl-baseline-") as tmp:
            cfg = yaml.safe_load((ROOT / "configs" / "points.yaml").read_text(encoding="utf-8"))
            cfg["model"]["kwargs"]["base"] = 16
            config = Path(tmp) / "changed.yaml"
            config.write_text(yaml.safe_dump(cfg), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, "-m", "pipeline.train", "--config", str(config), "--validate-only"],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("baseline fingerprint mismatch", proc.stderr)

    def test_structure_config_conflict_is_read_only(self):
        with tempfile.TemporaryDirectory(prefix="dl-structure-") as tmp:
            out = Path(tmp)
            path = out / "structure_config.yaml"
            path.write_text("seed: 1\n", encoding="utf-8")
            before = path.read_bytes()
            with self.assertRaises(SystemExit):
                check_structure_config(out, {"seed": 2})
            self.assertEqual(path.read_bytes(), before)

    def test_external_resume_checkpoint_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="dl-resume-") as tmp:
            root = Path(tmp)
            out = root / "run"
            out.mkdir()
            external = root / "other.ckpt"
            external.write_bytes(b"checkpoint")
            with self.assertRaises(SystemExit):
                resolve_resume_path(out, str(external))
            inside = out / "checkpoints" / "last.ckpt"
            inside.parent.mkdir()
            inside.write_bytes(b"checkpoint")
            self.assertEqual(resolve_resume_path(out, "last"), inside.resolve())
            archive = out / "archive" / "last.ckpt"
            archive.parent.mkdir()
            archive.write_bytes(b"checkpoint")
            with self.assertRaises(SystemExit):
                resolve_resume_path(out, str(archive))

    def test_test_flag_blocks_training(self):
        with tempfile.TemporaryDirectory(prefix="dl-testflag-") as tmp:
            out = Path(tmp)
            (out / "test_read.flag").write_text("read\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                preflight_output(out, resume=True, test_read_flag=out / "test_read.flag")

    def test_training_entry_rejects_missing_structure_card(self):
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pipeline.train",
                "--config",
                str(ROOT / "configs" / "points.yaml"),
                "--structure-card",
                "/tmp/does-not-exist-card.json",
                "--validate-only",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("cannot read card", proc.stderr)


if __name__ == "__main__":
    unittest.main()
