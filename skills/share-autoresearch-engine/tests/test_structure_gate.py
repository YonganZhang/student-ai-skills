"""Unit contract for scripts/structure_gate.py (stdlib unittest, no training)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import structure_gate as g  # noqa: E402


def valid_card(budget=2000, seeds=(20261017,)):
    return {
        "schema": g.SCHEMA,
        "target_model": "test model",
        "failure_mode": "FN at low contrast",
        "failure_evidence": "val FN concentrated in low-contrast windows",
        "structure_map": "stem -> enc -> bottleneck -> dec -> head",
        "candidate_positions": [
            {"id": "P0", "name": "native bottleneck", "why": "paper inserts here"},
            {"id": "P1", "name": "decoder skip", "why": "targets fine detail"},
        ],
        "single_position_reason": "",
        "mechanism_hypothesis": "more global context reduces misses",
        "single_axis": {"axis": "position", "baseline": "K", "budget_steps": budget,
                        "seeds": list(seeds), "primary_metric": "val F1",
                        "success_threshold": "+0.5 pp"},
        "falsification": "no gain in 3 seeds or F1 drop",
        "config_sha256": "",
    }


class StructureGateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.card = self.dir / "card.json"
        self.card.write_text(json.dumps(valid_card()))
        self.cfg = {"arm": "K", "train": {"steps": 2000}}

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid_card_and_binding_resume(self):
        result = g.require_card(self.card, self.cfg, expected_budget=2000, expected_seed=20261017)
        self.assertEqual(result["status"], "ok")
        path = g.record_binding(self.dir / "run", self.card, result, ["host.py"])
        self.assertTrue(path.exists())
        self.assertEqual((self.dir / "run" / "structure_card.json").read_bytes(), self.card.read_bytes())
        g.record_binding(self.dir / "run", self.card, result, ["host.py"])  # resume is idempotent

    def test_template_is_incomplete(self):
        with self.assertRaises(g.GateError):
            g.require_card(ROOT / "assets" / "structure-card.template.json", self.cfg)

    def test_missing_card_required(self):
        with self.assertRaises(g.GateError):
            g.require_card(None, self.cfg, required=True)
        self.assertIsNone(g.require_card(None, self.cfg, required=False))

    def test_single_position_needs_reason(self):
        data = valid_card()
        data["candidate_positions"] = data["candidate_positions"][:1]
        self.card.write_text(json.dumps(data))
        with self.assertRaises(g.GateError):
            g.require_card(self.card, self.cfg)

    def test_budget_and_seed_must_match(self):
        with self.assertRaises(g.GateError):
            g.require_card(self.card, self.cfg, expected_budget=1999)
        with self.assertRaises(g.GateError):
            g.require_card(self.card, self.cfg, expected_seed=1)

    def test_config_hash_mismatch(self):
        data = valid_card()
        data["config_sha256"] = "0" * 64
        self.card.write_text(json.dumps(data))
        with self.assertRaises(g.GateError):
            g.require_card(self.card, self.cfg)

    def test_binding_conflict(self):
        result = g.require_card(self.card, self.cfg)
        g.record_binding(self.dir / "run", self.card, result, ["host.py"])
        other = dict(result, config_sha256="1" * 64)
        with self.assertRaises(g.GateError):
            g.record_binding(self.dir / "run", self.card, other, ["host.py"])


if __name__ == "__main__":
    unittest.main()
