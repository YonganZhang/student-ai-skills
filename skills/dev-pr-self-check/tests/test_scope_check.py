import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "scope_check.py"
sys.path.insert(0, str(SCRIPT.parent))
from scope_check import high_risk  # noqa: E402

FAKE_KEY = "sk-" + "A1b2C3d4" * 4  # synthetic, not a real credential


def sh(cwd, *args):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


class ScopeCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        sh(self.repo, "git", "init", "-q", "-b", "main")
        sh(self.repo, "git", "config", "user.email", "t@example.com")
        sh(self.repo, "git", "config", "user.name", "t")
        sh(self.repo, "git", "config", "core.quotePath", "true")
        sh(self.repo, "git", "config", "core.hooksPath", "/dev/null")  # global secret hooks would reject fixtures
        self.write("a.py", "x = 1\n" * 100)
        self.write(".github/workflows/ci.yml", "on: push\n")
        self.write("中文/.env", "A=1\n")
        sh(self.repo, "git", "add", "-A")
        sh(self.repo, "git", "commit", "-qm", "base")
        sh(self.repo, "git", "checkout", "-qb", "feat")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, content):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def commit(self, name=None, content=None, msg="c"):
        if name:
            self.write(name, content)
        sh(self.repo, "git", "add", "-A")
        sh(self.repo, "git", "commit", "-qm", msg)

    def run_check(self, *extra, cwd=None):
        p = subprocess.run([sys.executable, str(SCRIPT), "--base", "main", "--json", *extra],
                           cwd=cwd or self.repo, capture_output=True, text=True)
        return p.returncode, json.loads(p.stdout) if p.stdout else None

    def reasons(self, r, key="blockers"):
        return " | ".join(f"{i['path']}: {i['reason']}" for i in r[key])

    def test_clean_change_passes(self):
        self.commit("a.py", "x = 2\n")
        code, r = self.run_check()
        self.assertEqual((code, r["files"], r["blockers"]), (0, 1, []))
        self.assertEqual(r["scope"], "committed-only")

    def test_env_file_and_assigned_secret_block(self):
        self.commit(".env", "A=1\n")
        self.commit("b.py", 'api_key = "abcd1234efgh5678"\n')
        code, r = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("env file", self.reasons(r))
        self.assertIn("b.py: possible assigned secret", self.reasons(r))
        self.assertEqual([b.get("line") for b in r["blockers"] if b["path"] == "b.py"], [1])

    def test_rename_to_env_is_not_lost(self):
        sh(self.repo, "git", "mv", "a.py", ".env")
        self.commit()
        code, r = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn(".env", r["changed"])
        self.assertIn("a.py", r["changed"])

    def test_rename_into_workflows_warns(self):
        sh(self.repo, "git", "mv", "a.py", ".github/workflows/x.yml")
        self.commit()
        code, r = self.run_check()
        self.assertEqual(code, 0)
        self.assertIn(".github/workflows/x.yml", self.reasons(r, "warnings"))

    def test_chinese_and_space_paths_are_scanned(self):
        self.commit("模块/配置.py", f'token = "{FAKE_KEY}"\n')
        self.commit("has space.py", f'k = "{FAKE_KEY}"\n')
        code, r = self.run_check()
        self.assertEqual(code, 1)
        paths = {b["path"] for b in r["blockers"]}
        self.assertEqual(paths, {"模块/配置.py", "has space.py"})

    def test_json_key_and_new_token_forms(self):
        self.commit("c.json", '{"api_key": "abcd1234efgh5678"}\n')
        self.commit("d.txt", "github_pat_" + "a1B2c3D4e5" * 5 + "\n" + "ASIA" + "ABCDEFGHIJKLMNOP" + "\n")
        code, r = self.run_check()
        self.assertEqual(code, 1)
        text = self.reasons(r)
        self.assertIn("c.json: possible assigned secret", text)
        self.assertIn("d.txt: possible GitHub token", text)
        self.assertIn("d.txt: possible AWS access key", text)

    def test_placeholder_is_warning_not_blocker(self):
        self.commit("e.py", 'password = "CHANGE_ME"\n')
        code, r = self.run_check()
        self.assertEqual(code, 0)
        self.assertIn("placeholder", self.reasons(r, "warnings"))

    def test_deleting_workflow_warns_and_deleting_env_does_not_block(self):
        sh(self.repo, "git", "rm", "-q", ".github/workflows/ci.yml", "中文/.env")
        self.commit()
        code, r = self.run_check()
        self.assertEqual((code, r["blockers"]), (0, []))
        self.assertIn("ci.yml: high-risk path deleted", self.reasons(r, "warnings"))

    def test_placeholder_does_not_hide_real_value_on_same_line(self):
        self.commit("f.py", 'password = "CHANGE_ME"; api_key = "synthetic12345678"\n')
        self.commit("g.json", '{"password": "CHANGE_ME", "secret": "REPLACE_ME"}\n')
        code, r = self.run_check()
        self.assertEqual(code, 1)
        self.assertEqual({b["path"] for b in r["blockers"]}, {"f.py"})
        self.assertIn("g.json: placeholder", self.reasons(r, "warnings"))

    def test_non_utf8_path_gives_valid_json(self):
        name = os.fsdecode(b"bad-\xff.py")
        with open(os.path.join(os.fsencode(self.repo), b"bad-\xff.py"), "w") as fh:
            fh.write('api_key = "abcd1234efgh5678"\n')
        self.commit()
        p = subprocess.run([sys.executable, str(SCRIPT), "--base", "main", "--json"], cwd=self.repo, capture_output=True)
        self.assertEqual(p.returncode, 1)
        r = json.loads(p.stdout.decode("utf-8"))  # strict UTF-8
        self.assertEqual(r["blockers"][0]["path"], name)
        self.assertEqual(os.fsencode(r["blockers"][0]["path"]), b"bad-\xff.py")

    def test_submodule_pointer_add_and_update(self):
        sub = Path(self.tmp.name) / "sub"
        sub.mkdir()
        for args in (("init", "-q", "-b", "main"), ("config", "user.email", "t@example.com"),
                     ("config", "user.name", "t"), ("config", "core.hooksPath", "/dev/null"),
                     ("commit", "-q", "--allow-empty", "-m", "s1")):
            sh(sub, "git", *args)
        sh(self.repo, "git", "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(sub), "vendor/lib")
        self.commit(msg="add submodule")
        code, r = self.run_check()
        self.assertEqual(code, 0, r)
        self.assertIn("vendor/lib: submodule pointer", self.reasons(r, "warnings"))
        sh(self.repo / "vendor/lib", "git", "-c", "user.email=t@example.com", "-c", "user.name=t",
           "commit", "-q", "--allow-empty", "-m", "s2")
        self.commit(msg="bump submodule")
        code, r = self.run_check()
        self.assertEqual(code, 0, r)

    def test_env_example_allowed(self):
        self.commit(".env.example", "A=\n")
        self.assertEqual(self.run_check()[0], 0)

    def test_dirty_tree_is_precondition_error_unless_allowed(self):
        self.commit("a.py", "x = 3\n")
        self.write(".env", "SECRET=1\n")  # untracked
        code, r = self.run_check()
        self.assertEqual(code, 2)
        self.assertIn("uncommitted", r["error"])
        code, r = self.run_check("--allow-dirty")
        self.assertEqual(code, 0)
        self.assertTrue(r["dirty"])

    def test_big_file_blocks(self):
        (self.repo / "big.bin").write_bytes(b"\0" * (5 * 1024 * 1024 + 1))
        self.commit()
        code, r = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("MiB", self.reasons(r))

    def test_runs_from_outside_skill_dir(self):
        self.commit("a.py", "x = 4\n")
        code, r = self.run_check()
        self.assertEqual(r["changed"], ["a.py"])

    def test_bad_inputs_exit_2(self):
        for args in (["--base", "nope"], ["--base", "main", "--max-lines", "-1"]):
            p = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=self.repo, capture_output=True, text=True)
            self.assertEqual(p.returncode, 2, args)

    def test_high_risk_matches_segments_not_substrings(self):
        self.assertTrue(high_risk("scripts/release_app.py"))
        self.assertTrue(high_risk("astrbot/core/auth/session.py"))
        self.assertTrue(high_risk(".github/CODEOWNERS"))
        self.assertFalse(high_risk("_tests/evidence/release-notes-2026/checks.jsonl"))
        self.assertFalse(high_risk("docs/guide.md"))


if __name__ == "__main__":
    unittest.main()
