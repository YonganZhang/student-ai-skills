"""Exercise public process behavior; also runnable after copying the template."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


CLI = Path(__file__).resolve().parents[1] / "cli.py"


class CLITest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / "样本 data.txt"
        self.target.write_bytes(b"abc\x00\xff")

    def run_cli(self, *args, cli=CLI):
        return subprocess.run(
            [sys.executable, str(cli), *map(str, args)],
            cwd=self.root, stdin=subprocess.DEVNULL, capture_output=True,
            text=True, timeout=5,
        )

    def test_root_and_command_help(self):
        for args in (("--help",), ("inspect", "--help")):
            with self.subTest(args=args):
                run = self.run_cli(*args)
                self.assertEqual(run.returncode, 0)
                self.assertIn("python3 cli.py", run.stdout)
                self.assertEqual(run.stderr, "")

    def test_text_result_and_read_only(self):
        before = self.target.read_bytes()
        run = self.run_cli("inspect", self.target)
        self.assertEqual(run.returncode, 0)
        self.assertIn("5 bytes", run.stdout)
        self.assertIn(str(self.target), run.stdout)
        self.assertEqual(run.stderr, "")
        self.assertEqual(self.target.read_bytes(), before)

    def test_json_flag_positions_and_contract(self):
        for args in (("--json", "inspect", self.target), ("inspect", self.target, "--json")):
            with self.subTest(args=args):
                run = self.run_cli(*args)
                self.assertEqual(run.returncode, 0)
                self.assertEqual(run.stderr, "")
                self.assertEqual(json.loads(run.stdout), {
                    "schema_version": 1, "ok": True,
                    "data": {"path": str(self.target), "kind": "file", "size_bytes": 5},
                })

    def test_directory_result(self):
        run = self.run_cli("inspect", ".", "--json")
        self.assertEqual(run.returncode, 0)
        result = json.loads(run.stdout)["data"]
        self.assertEqual(result["path"], str(self.root))
        self.assertEqual(result["kind"], "directory")

    def test_missing_target_has_real_failure_in_both_modes(self):
        for flags in ((), ("--json",)):
            with self.subTest(flags=flags):
                run = self.run_cli("inspect", self.root / "absent", *flags)
                self.assertEqual(run.returncode, 1)
                self.assertEqual(run.stdout, "")
                self.assertIn("读取失败", run.stderr)

    def test_usage_failures_are_two_and_do_not_emit_results(self):
        for args in ((), ("inspect",), ("unknown",), ("inspect", self.target, "--invalid"), ("--js", "inspect", self.target)):
            with self.subTest(args=args):
                run = self.run_cli(*args)
                self.assertEqual(run.returncode, 2)
                self.assertEqual(run.stdout, "")
                self.assertTrue(run.stderr)

    def test_option_like_path_is_data_after_separator(self):
        target = self.root / "--json"
        target.write_bytes(b"x")
        run = self.run_cli("inspect", "--", "--json")
        self.assertEqual(run.returncode, 0)
        self.assertIn("1 bytes", run.stdout)

    def test_symlink_target_and_dangling_symlink(self):
        link = self.root / "link"
        link.symlink_to(self.target)
        run = self.run_cli("inspect", link, "--json")
        self.assertEqual(run.returncode, 0)
        self.assertEqual(json.loads(run.stdout)["data"]["path"], str(self.target))
        self.target.unlink()
        failed = self.run_cli("inspect", link)
        self.assertEqual(failed.returncode, 1)
        self.assertEqual(failed.stdout, "")

    def test_copied_template_has_no_global_runtime_dependency(self):
        copied = self.root / "copy"
        shutil.copytree(CLI.parent, copied, ignore=shutil.ignore_patterns("__pycache__"))
        run = self.run_cli("inspect", self.target, "--json", cli=copied / "cli.py")
        self.assertEqual(run.returncode, 0)
        self.assertEqual(json.loads(run.stdout)["data"]["size_bytes"], 5)

    def test_symlink_loop_is_a_read_failure_without_traceback(self):
        loop = self.root / "loop"
        loop.symlink_to("loop")
        run = self.run_cli("inspect", loop, "--json")
        self.assertEqual(run.returncode, 1)
        self.assertEqual(run.stdout, "")
        self.assertIn("读取失败", run.stderr)
        self.assertNotIn("Traceback", run.stderr)


if __name__ == "__main__":
    unittest.main()
