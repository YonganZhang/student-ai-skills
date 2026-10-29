#!/usr/bin/env python3
"""Unit contract for scripts/issue_ledger_check.py (no training, no data)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import issue_ledger_check as c  # noqa: E402


def issue(**over):
    data = {
        "id": "DL-2026-001",
        "title": "split leak",
        "status": "open",
        "severity": "P1",
        "blocks_action": "freeze",
        "layer": "data",
        "symptom": "val F1 high, test low",
        "evidence": [{"path": "runs/x/manifest.json", "fact": "patient repeats"}],
        "root_cause": "split by image",
        "invariant": "one patient in one split",
        "check": "group overlap assert",
        "automation": "script",
        "owner": "builder",
        "opened": "2026-10-25",
    }
    data.update(over)
    return data


def ledger(*items):
    return {"schema_version": 1, "issues": list(items)}


class IssueLedgerTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(c.check(ledger(issue())), [])

    def test_closed_needs_evidence(self):
        errors = c.check(ledger(issue(status="closed")))
        self.assertTrue(any("close_evidence" in e for e in errors))
        ok = issue(status="closed", close_evidence="cmd output", closed_by="reviewer", reviewed="2026-10-26")
        self.assertEqual(c.check(ledger(ok)), [])

    def test_duplicate_and_enum(self):
        errors = c.check(ledger(issue(), issue(severity="P9", blocks_action="all")))
        self.assertTrue(any("duplicate" in e for e in errors))
        self.assertTrue(any("severity" in e for e in errors))
        self.assertTrue(any("blocks_action" in e for e in errors))

    def test_empty_evidence(self):
        self.assertTrue(any("evidence" in e for e in c.check(ledger(issue(evidence=[])))))

    def test_evidence_must_be_list(self):
        for bad in ("no path or fact", {"path": "runs/x", "fact": "x"}):
            errors = c.check(ledger(issue(evidence=bad)))
            self.assertTrue(any("evidence" in e for e in errors), bad)


if __name__ == "__main__":
    unittest.main()
