"""Exercise public process behavior of the markdown-count CLI."""

import json
import os
from pathlib import Path
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
        self.docs = self.root / "docs"
        self.docs.mkdir()
        # Two direct .md regular files.
        (self.docs / "a.md").write_text("a")
        (self.docs / "b.md").write_text("b")
        # Noise that must NOT be counted.
        (self.docs / "notes.txt").write_text("x")          # wrong suffix
        (self.docs / "sub.md").mkdir()                      # directory named *.md
        (self.docs / "nested").mkdir()
        (self.docs / "nested" / "deep.md").write_text("d")  # recursion guard

    def run_cli(self, *args, cli=CLI):
        return subprocess.run(
            [sys.executable, str(cli), *map(str, args)],
            cwd=self.root, stdin=subprocess.DEVNULL, capture_output=True,
            text=True, timeout=5,
        )

    def test_root_and_command_help(self):
        for args in (("--help",), ("count", "--help")):
            with self.subTest(args=args):
                run = self.run_cli(*args)
                self.assertEqual(run.returncode, 0)
                self.assertIn("python3 cli.py", run.stdout)
                self.assertEqual(run.stderr, "")

    def test_text_count_and_read_only(self):
        before = sorted(os.listdir(self.docs))
        run = self.run_cli("count", self.docs)
        self.assertEqual(run.returncode, 0)
        self.assertIn("2 markdown files", run.stdout)
        self.assertIn(str(self.docs), run.stdout)
        self.assertEqual(run.stderr, "")
        self.assertEqual(sorted(os.listdir(self.docs)), before)

    def test_json_flag_positions_and_contract(self):
        for args in (("--json", "count", self.docs), ("count", self.docs, "--json")):
            with self.subTest(args=args):
                run = self.run_cli(*args)
                self.assertEqual(run.returncode, 0)
                self.assertEqual(run.stderr, "")
                self.assertEqual(json.loads(run.stdout), {
                    "schema_version": 1, "ok": True,
                    "data": {"path": str(self.docs), "markdown_files": 2},
                })

    def test_non_recursive_and_ignores_directory_named_md(self):
        # docs has 2 real .md files; nested/deep.md and sub.md/ must be excluded.
        run = self.run_cli("count", self.docs, "--json")
        self.assertEqual(json.loads(run.stdout)["data"]["markdown_files"], 2)

    def test_child_symlink_to_md_is_not_counted(self):
        (self.docs / "link.md").symlink_to(self.docs / "a.md")
        run = self.run_cli("count", self.docs, "--json")
        self.assertEqual(run.returncode, 0)
        self.assertEqual(json.loads(run.stdout)["data"]["markdown_files"], 2)

    def test_empty_directory_is_zero(self):
        empty = self.root / "empty"
        empty.mkdir()
        run = self.run_cli("count", empty, "--json")
        self.assertEqual(run.returncode, 0)
        self.assertEqual(json.loads(run.stdout)["data"]["markdown_files"], 0)

    def test_missing_target_fails_in_both_modes(self):
        for flags in ((), ("--json",)):
            with self.subTest(flags=flags):
                run = self.run_cli("count", self.root / "absent", *flags)
                self.assertEqual(run.returncode, 1)
                self.assertEqual(run.stdout, "")
                self.assertIn("统计失败", run.stderr)

    def test_file_target_is_not_a_directory_failure(self):
        afile = self.root / "plain.md"
        afile.write_text("x")
        run = self.run_cli("count", afile)
        self.assertEqual(run.returncode, 1)
        self.assertEqual(run.stdout, "")
        self.assertIn("不是目录", run.stderr)

    def test_usage_failures_are_two_and_do_not_emit_results(self):
        for args in ((), ("count",), ("unknown",), ("count", self.docs, "--bad"), ("--js", "count", self.docs)):
            with self.subTest(args=args):
                run = self.run_cli(*args)
                self.assertEqual(run.returncode, 2)
                self.assertEqual(run.stdout, "")
                self.assertTrue(run.stderr)

    def test_option_like_path_is_data_after_separator(self):
        weird = self.root / "--json"
        weird.mkdir()
        (weird / "x.md").write_text("x")
        run = self.run_cli("count", "--", "--json")
        self.assertEqual(run.returncode, 0)
        self.assertIn("1 markdown files", run.stdout)

    def test_symlink_dir_target_is_followed(self):
        link = self.root / "docs-link"
        link.symlink_to(self.docs)
        run = self.run_cli("count", link, "--json")
        self.assertEqual(run.returncode, 0)
        self.assertEqual(json.loads(run.stdout)["data"]["markdown_files"], 2)

    def test_symlink_loop_is_a_failure_without_traceback(self):
        loop = self.root / "loop"
        loop.symlink_to("loop")
        run = self.run_cli("count", loop)
        self.assertEqual(run.returncode, 1)
        self.assertEqual(run.stdout, "")
        self.assertIn("统计失败", run.stderr)
        self.assertNotIn("Traceback", run.stderr)


if __name__ == "__main__":
    unittest.main()
