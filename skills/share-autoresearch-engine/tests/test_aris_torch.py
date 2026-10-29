import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PYTHON = os.environ.get("ARIS_TEST_PYTHON")
IDS = ("interface", "training_path", "data_semantics", "baseline_control", "checkpoint")


@unittest.skipUnless(PYTHON, "Set ARIS_TEST_PYTHON to an existing PyTorch environment")
class TorchGateTest(unittest.TestCase):
    def run_case(self, bug):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = {"schema_version": 1, "budget_seconds": 150, "checks": [
                {"id": name, "command": [PYTHON, str(ROOT / "tests/fixtures/aris_torch_probe.py"), name, "--bug", bug],
                 "timeout_seconds": 30} for name in IDS]}
            (root / "plan.json").write_text(json.dumps(plan))
            result = subprocess.run([sys.executable, str(ROOT / "scripts/integration_gate.py"),
                                     str(root / "plan.json"), "--project", str(root), "--output", str(root / "run")],
                                    capture_output=True, text=True, timeout=170)
            report = json.loads((root / "run/report.json").read_text())
            logs = "\n".join(p.read_text() for p in (root / "run").glob("*.log"))
            return result, report, logs

    def test_healthy_real_training_mask_and_checkpoint(self):
        result, report, logs = self.run_case("none")
        self.assertEqual(result.returncode, 0, logs)
        self.assertEqual(report["status"], "checks_passed")

    def test_tensor_axis_failure_blocks(self):
        result, report, logs = self.run_case("shape")
        self.assertEqual(result.returncode, 1, logs)
        self.assertEqual(report["checks"][0]["status"], "failed")
        self.assertIn("axis contract violated", logs)

    def test_optimizer_omission_blocks(self):
        result, report, logs = self.run_case("optimizer")
        self.assertEqual(result.returncode, 1, logs)
        self.assertEqual(report["checks"][1]["status"], "failed")
        self.assertIn("optimizer omitted parameters", logs)

    def test_unused_mask_blocks(self):
        result, report, logs = self.run_case("mask")
        self.assertEqual(result.returncode, 1, logs)
        self.assertEqual(report["checks"][2]["status"], "failed")
        self.assertIn("masked values affected output", logs)


if __name__ == "__main__":
    unittest.main()
