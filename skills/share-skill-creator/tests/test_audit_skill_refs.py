"""Detect dead nested-workflow references, including wildcard migration paths."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / "scripts/audit_skill_refs.py"
SPEC = importlib.util.spec_from_file_location("tested_skill_ref_audit", SOURCE)
AUDIT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = AUDIT
SPEC.loader.exec_module(AUDIT)


class NestedReferenceTests(unittest.TestCase):
    def test_migrated_workflows_reject_old_literal_and_wildcard_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent = root / "skills/writing"
            child = parent / "sub-skills/share-nature-writing"
            child.mkdir(parents=True)
            (child / "REFERENCE.md").write_text("Current workflow\n")
            (parent / "SKILL.md").write_text(
                "Read `sub-skills/share-nature-writing/SKILL.md`\n"
                "Read `sub-skills/share-nature-*/SKILL.md`\n"
                "Read `sub-skills/share-nature-*/REFERENCE.md`\n"
            )
            refs = AUDIT.audit_repo(str(root))
            self.assertEqual(len(refs), 3)
            self.assertEqual([ref.status for ref in refs], ["missing", "missing", "ok-local"])

    def test_absolute_and_cross_skill_wildcards_must_have_live_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent = root / "skills/writing"
            target = root / "skills/other/references/current"
            parent.mkdir(parents=True)
            target.mkdir(parents=True)
            (target / "REFERENCE.md").write_text("Current workflow\n")
            (parent / "SKILL.md").write_text(
                "Read `other/references/*/REFERENCE.md`\n"
                "Read `other/references/*/SKILL.md`\n"
            )
            refs = AUDIT.audit_repo(str(root))
            self.assertEqual([ref.status for ref in refs], ["ok-cross-skill", "missing"])
            live = str(target.parent / "*/REFERENCE.md")
            dead = str(target.parent / "*/SKILL.md")
            with patch.object(Path, "expanduser", return_value=Path(live)):
                self.assertEqual(AUDIT.classify(root, parent / "SKILL.md", "~/.claude/skills/other/references/*/REFERENCE.md", "")[0], "ok-absolute")
            with patch.object(Path, "expanduser", return_value=Path(dead)):
                self.assertEqual(AUDIT.classify(root, parent / "SKILL.md", "~/.claude/skills/other/references/*/SKILL.md", "")[0], "missing")


if __name__ == "__main__":
    unittest.main()
