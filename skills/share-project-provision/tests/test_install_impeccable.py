"""Behavior checks for the single-module installer, with no network or engine."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/install_impeccable.py"
spec = importlib.util.spec_from_file_location("impeccable_installer", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class InstallerBehavior(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.files = {root + "/SKILL.md": (b"---\nname: impeccable\n---\n", 0o644)
                      for root in module.ROOTS}

    def test_preview_is_read_only_then_install_and_verify(self):
        self.assertEqual(module.install(self.project, self.files, False)["status"], "preview")
        self.assertEqual(list(self.project.iterdir()), [])
        module.install(self.project, self.files, True)
        self.assertEqual(module.verify(self.project)["status"], "verified")
        self.assertFalse((self.project / ".codex").exists())
        self.assertFalse((self.project / ".claude/settings.json").exists())

    def test_existing_design_skill_is_never_overwritten(self):
        existing = self.project / ".codex/skills/frontend-design/SKILL.md"
        existing.parent.mkdir(parents=True)
        existing.write_text("user content")
        with self.assertRaisesRegex(ValueError, "existing design"):
            module.install(self.project, self.files, True)
        self.assertEqual(existing.read_text(), "user content")
        self.assertFalse((self.project / module.RECEIPT).exists())

    def test_reinstall_refuses_and_preserves_local_edit(self):
        module.install(self.project, self.files, True)
        entry = self.project / module.ROOTS[0] / "SKILL.md"
        entry.write_text("local edit")
        with self.assertRaises(ValueError):
            module.install(self.project, self.files, True)
        self.assertEqual(entry.read_text(), "local edit")
        with self.assertRaisesRegex(ValueError, "modified"):
            module.verify(self.project)

    def test_symlink_parent_cannot_escape_project(self):
        with tempfile.TemporaryDirectory() as external:
            (self.project / ".agents").symlink_to(external, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "unsafe parent"):
                module.install(self.project, self.files, True)
            self.assertEqual(list(Path(external).iterdir()), [])

    def test_missing_extra_and_symlink_files_fail_verification(self):
        module.install(self.project, self.files, True)
        extra = self.project / module.ROOTS[0] / "extra.md"
        extra.write_text("unexpected")
        with self.assertRaisesRegex(ValueError, "extra"):
            module.verify(self.project)
        extra.unlink()
        entry = self.project / module.ROOTS[0] / "SKILL.md"
        entry.unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            module.verify(self.project)
        entry.symlink_to(self.project / module.ROOTS[1] / "SKILL.md")
        with self.assertRaisesRegex(ValueError, "symlink"):
            module.verify(self.project)

    def test_verifies_declared_version_rather_than_latest_recipe(self):
        module.install(self.project, self.files, True)
        receipt = self.project / module.RECEIPT
        record = json.loads(receipt.read_text())
        record["commit"] = "a" * 40
        record["recipe"] = 2
        receipt.write_text(json.dumps(record))
        self.assertEqual(module.verify(self.project)["commit"], "a" * 40)

    def test_invalid_receipt_path_is_rejected(self):
        module.install(self.project, self.files, True)
        receipt = self.project / module.RECEIPT
        record = json.loads(receipt.read_text())
        record["files"]["../../outside"] = {"sha256": "a" * 64, "mode": 0o644}
        receipt.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, "invalid receipt"):
            module.verify(self.project)

    def test_incomplete_copy_rolls_back_only_own_install(self):
        unrelated = self.project / "notes.txt"
        unrelated.write_text("keep")
        with patch.object(module.shutil, "copytree", side_effect=OSError("copy failed")):
            with self.assertRaisesRegex(OSError, "copy failed"):
                module.install(self.project, self.files, True)
        self.assertEqual(unrelated.read_text(), "keep")
        self.assertFalse((self.project / module.RECEIPT).exists())
        self.assertTrue(all(not (self.project / root).exists() for root in module.ROOTS))
        self.assertFalse((self.project / ".impeccable-install.lock").exists())

    def test_stale_lock_refuses_without_touching_project(self):
        (self.project / ".impeccable-install.lock").mkdir()
        with self.assertRaises(FileExistsError):
            module.install(self.project, self.files, True)
        self.assertEqual([p.name for p in self.project.iterdir()], [".impeccable-install.lock"])

    def test_non_object_receipt_is_reported_as_invalid(self):
        module.install(self.project, self.files, True)
        (self.project / module.RECEIPT).write_text("[]")
        with self.assertRaisesRegex(ValueError, "JSON object"):
            module.verify(self.project)


if __name__ == "__main__":
    unittest.main()
