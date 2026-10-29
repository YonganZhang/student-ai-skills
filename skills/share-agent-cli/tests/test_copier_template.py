"""Exercise the actual Copier executable with isolated, versioned templates.

Run with Python >=3.11 and Copier 9.18.2 in the same task environment.
No network, install hooks, or global configuration reads are needed by these tests.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import tomllib
import unittest


SKILL = Path(__file__).resolve().parents[1]
SHARED = SKILL.parents[1]
COPIER = os.environ.get("CLI_TEMPLATE_COPIER", "copier")


def run(*args, cwd=None, check=True):
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=check)


class CopierTemplateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source"
        self.asset = self.source / "skills/share-agent-cli/assets/python-click"
        shutil.copytree(SKILL / "assets/python-click", self.asset)
        shutil.copy2(SHARED / "copier.yml", self.source / "copier.yml")
        (self.source / "unrelated-private-config.txt").write_text("DO_NOT_COPY")
        self.git_init(self.source)
        self.commit(self.source, "template v1")
        run("git", "tag", "v1.0.0", cwd=self.source)
        self.destination = self.root / "generated"

    @staticmethod
    def git_init(path):
        run("git", "init", "-q", str(path))
        run("git", "config", "user.name", "Template Test", cwd=path)
        run("git", "config", "user.email", "template@example.invalid", cwd=path)

    @staticmethod
    def commit(path, message):
        run("git", "add", ".", cwd=path)
        run("git", "commit", "-qm", message, cwd=path)

    def generate(self, name="example-cli", description="A test", check=True):
        return run(COPIER, "copy", "--defaults", "--vcs-ref", "v1.0.0",
                   "--data", f"command_name={name}", "--data", f"description={description}",
                   str(self.source), str(self.destination), check=check)

    def upgrade_source(self, filename, before, after):
        path = self.asset / "template" / filename
        path.write_text(path.read_text().replace(before, after))
        self.commit(self.source, "template v2")
        run("git", "tag", "v2.0.0", cwd=self.source)

    def test_generation_is_scoped_and_records_version(self):
        self.generate()
        self.assertFalse((self.destination / "unrelated-private-config.txt").exists())
        self.assertFalse((self.destination / "skills").exists())
        answers = (self.destination / ".copier-answers.yml").read_text()
        self.assertIn("_commit: v1.0.0", answers)
        self.assertIn(str(self.source), answers)
        self.assertIn("command_name: example-cli", answers)
        self.assertTrue((self.destination / "src/example_cli/cli.py").exists())
        workflow = (self.destination / ".github/workflows/test.yml").read_text()
        self.assertIn("${{ matrix.python-version }}", workflow)
        self.assertNotIn("id-token", workflow)

    def test_metadata_escapes_quotes_and_newlines(self):
        description = '中文 "quotes"\\path\nsecond line'
        self.generate(name="class", description=description)
        metadata = tomllib.loads((self.destination / "pyproject.toml").read_text())
        self.assertEqual(metadata["project"]["description"], description)
        entry = self.destination / "src/class_cli/cli.py"
        self.assertTrue(entry.exists())
        compile(entry.read_text(), str(entry), "exec")

    def test_invalid_names_are_rejected_without_escape(self):
        for name in ["../escape", "BadName", "has space", "", "a/b"]:
            with self.subTest(name=name):
                result = self.generate(name=name, check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((self.root / "escape").exists())
                self.assertFalse((self.destination / "pyproject.toml").exists())

    def test_upgrade_preserves_project_edits(self):
        self.generate()
        self.git_init(self.destination)
        readme = self.destination / "README.md"
        readme.write_text(readme.read_text() + "\nPROJECT_LOCAL_NOTE\n")
        (self.destination / "business.txt").write_text("LOCAL_BUSINESS")
        self.commit(self.destination, "local business")
        self.upgrade_source("README.md.jinja", "# {{ command_name }}", "# {{ command_name }} v2")
        run(COPIER, "update", "--defaults", "--vcs-ref", "v2.0.0", cwd=self.destination)
        self.assertIn("v2", readme.read_text().splitlines()[0])
        self.assertIn("PROJECT_LOCAL_NOTE", readme.read_text())
        self.assertEqual((self.destination / "business.txt").read_text(), "LOCAL_BUSINESS")
        self.assertIn("_commit: v2.0.0", (self.destination / ".copier-answers.yml").read_text())
        run("git", "diff", "--check", cwd=self.destination)

    def test_upgrade_conflicts_require_explicit_check(self):
        self.generate()
        self.git_init(self.destination)
        pyproject = self.destination / "pyproject.toml"
        pyproject.write_text(pyproject.read_text().replace('version = "0.1.0"', 'version = "0.1.9"'))
        self.commit(self.destination, "local version")
        self.upgrade_source("pyproject.toml.jinja", 'version = "0.1.0"', 'version = "0.2.0"')
        result = run(COPIER, "update", "--defaults", "--vcs-ref", "v2.0.0",
                     cwd=self.destination, check=False)
        # An exit-zero update can still contain unresolved conflicts.
        self.assertIn("<<<<<<<", pyproject.read_text(), result.stderr)
        self.assertNotEqual(run("git", "diff", "--check", cwd=self.destination, check=False).returncode, 0)


if __name__ == "__main__":
    unittest.main()
