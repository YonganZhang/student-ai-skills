import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts/integration_gate.py"
EVIDENCE = ROOT / "scripts/aris_evidence.py"
IDS = ("interface", "training_path", "data_semantics", "baseline_control", "checkpoint")


class ToolsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def plan(self):
        return {"schema_version": 1, "checks": [
            {"id": name, "command": [sys.executable, "-c", "print('executed')"]} for name in IDS]}

    def gate(self, plan):
        p = self.root / "plan.json"
        p.write_text(json.dumps(plan))
        return subprocess.run([sys.executable, str(GATE), str(p), "--project", str(self.root),
                               "--output", str(self.root / "run")], capture_output=True, text=True, timeout=20)

    def report(self):
        return json.loads((self.root / "run/report.json").read_text())

    def test_real_commands_are_logged_and_pass_only_to_review(self):
        result = self.gate(self.plan())
        self.assertEqual(result.returncode, 0, result.stderr)
        report = self.report()
        self.assertEqual(report["status"], "checks_passed")
        self.assertEqual(report["next_step"], "independent_review")
        for check in report["checks"]:
            self.assertEqual(Path(check["log"]).read_text().strip(), "executed")
            self.assertEqual(check["cwd"], str(self.root))
            self.assertEqual(check["exit_code"], 0)

    def test_failure_stops_following_checks_and_preserves_stderr(self):
        plan = self.plan()
        plan["checks"][1]["command"] = [sys.executable, "-c", "raise AssertionError('optimizer omitted parameter')"]
        self.assertEqual(self.gate(plan).returncode, 1)
        report = self.report()
        self.assertEqual([c["status"] for c in report["checks"]], ["passed", "failed", "not_run", "not_run", "not_run"])
        self.assertIn("optimizer omitted parameter", Path(report["checks"][1]["log"]).read_text())

    def test_timeout_is_blocked(self):
        plan = self.plan()
        plan["checks"][0].update(command=[sys.executable, "-c", "import time; time.sleep(10)"], timeout_seconds=0.05)
        self.assertEqual(self.gate(plan).returncode, 1)
        self.assertEqual(self.report()["checks"][0]["status"], "timeout")

    def test_missing_executable_is_blocked(self):
        plan = self.plan()
        plan["checks"][0]["command"] = [str(self.root / "absent-python")]
        self.assertEqual(self.gate(plan).returncode, 1)
        self.assertEqual(self.report()["checks"][0]["status"], "execution_error")

    def test_missing_check_rejected_before_any_execution(self):
        plan = self.plan()
        plan["checks"].pop()
        self.assertEqual(self.gate(plan).returncode, 2)
        self.assertFalse((self.root / "run").exists())

    def test_duplicate_check_rejected(self):
        plan = self.plan()
        plan["checks"].append(plan["checks"][0])
        self.assertEqual(self.gate(plan).returncode, 2)

    def test_optional_inapplicable_is_visible_not_passed(self):
        plan = self.plan()
        plan["checks"][-1] = {"id": "checkpoint", "not_applicable": "Transient diagnostic object; no persistence claim."}
        self.assertEqual(self.gate(plan).returncode, 0)
        self.assertEqual(self.report()["checks"][-1]["status"], "not_applicable")

    def test_required_semantics_cannot_be_skipped(self):
        plan = self.plan()
        plan["checks"][2] = {"id": "data_semantics", "not_applicable": "No time to check."}
        self.assertEqual(self.gate(plan).returncode, 2)

    def test_bad_timeout_and_empty_skip_rejected(self):
        for value in (0, -1, float("nan"), float("inf"), True, "60"):
            with self.subTest(value=value):
                plan = self.plan()
                plan["checks"][0]["timeout_seconds"] = value
                self.assertEqual(self.gate(plan).returncode, 2)
        plan = self.plan()
        plan["checks"][-1] = {"id": "checkpoint", "not_applicable": " "}
        self.assertEqual(self.gate(plan).returncode, 2)

    def test_old_success_cannot_be_overwritten(self):
        self.assertEqual(self.gate(self.plan()).returncode, 0)
        old = (self.root / "run/report.json").read_bytes()
        self.assertEqual(self.gate(self.plan()).returncode, 2)
        self.assertEqual((self.root / "run/report.json").read_bytes(), old)

    def evidence(self, claims):
        p = self.root / "claims.json"
        p.write_text(json.dumps(claims))
        return subprocess.run([sys.executable, str(EVIDENCE), str(p), "--root", str(self.root)],
                              capture_output=True, text=True, timeout=10)

    def test_evidence_found_is_only_presence(self):
        (self.root / "metrics.json").write_text('{"accuracy": 73.20}')
        result = self.evidence([{"id": "c1", "value": 73.2, "source": "metrics.json"}])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "evidence_found")
        self.assertIn("Value presence only", result.stdout)

    def test_bad_evidence_never_passes(self):
        for claims in ([], {}, [{"id": "c"}], [{"id": "c", "value": None, "source": "x"}],
                       [{"id": "c", "value": 1, "source": "missing.json"}]):
            with self.subTest(claims=claims):
                self.assertNotEqual(self.evidence(claims).returncode, 0)

    def test_duplicate_claims_rejected(self):
        item = {"id": "same", "value": 1, "source": "metrics.json"}
        self.assertEqual(self.evidence([item, item]).returncode, 2)

    def test_wrong_number_rejected(self):
        (self.root / "metrics.json").write_text('{"accuracy": 73.5}')
        result = self.evidence([{"id": "c", "value": 73, "source": "metrics.json"}])
        self.assertEqual(result.returncode, 1)
        self.assertIn("value_not_found", result.stdout)


if __name__ == "__main__":
    unittest.main()
