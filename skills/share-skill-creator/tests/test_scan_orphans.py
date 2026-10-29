"""Tests for scripts/scan_orphans.py using temporary skill trees."""
from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "scan_orphans.py"
spec = importlib.util.spec_from_file_location("scan_orphans", SCRIPT)
so = importlib.util.module_from_spec(spec)
spec.loader.exec_module(so)


def make_skill(root: Path, name: str, md: str, scripts: dict[str, str]) -> Path:
    skill = root / name
    (skill / "scripts").mkdir(parents=True)
    (skill / "SKILL.md").write_text(md)
    for fname, text in scripts.items():
        (skill / "scripts" / fname).write_text(text)
    return skill


def orphan_names(skill: Path) -> list[str]:
    return [name for name, _, _ in so.scan_skill(skill)]


def test_helpers_imported_via_scripts_package_are_not_orphans(tmp_path):
    skill = make_skill(tmp_path, "s", "Run `python -m scripts.run_loop`.", {
        "run_loop.py": "from scripts.utils import parse\nfrom scripts.generate_report import html\n",
        "package_skill.py": "from scripts.quick_validate import validate_skill\n",
        "utils.py": "def parse(): ...\n",
        "generate_report.py": "def html(): ...\n",
        "quick_validate.py": "def validate_skill(): ...\n",
    })
    # package_skill.py is not referenced anywhere, so it and its helper stay orphans
    assert orphan_names(skill) == ["package_skill.py", "quick_validate.py"]


def test_plain_and_relative_imports(tmp_path):
    skill = make_skill(tmp_path, "s", "Use main_tool.py", {
        "main_tool.py": "from helper import x\nfrom .other import y\nimport third\n",
        "helper.py": "", "other.py": "", "third.py": "",
    })
    assert orphan_names(skill) == []


def test_unreachable_caller_does_not_rescue_helper(tmp_path):
    skill = make_skill(tmp_path, "s", "nothing referenced", {
        "dead.py": "from scripts.dead_helper import f\n",
        "dead_helper.py": "",
    })
    result = {name: who for name, _, who in so.scan_skill(skill)}
    assert result == {"dead.py": [], "dead_helper.py": ["dead.py"]}


def test_substring_names_do_not_count_as_imports(tmp_path):
    skill = make_skill(tmp_path, "s", "Use runner.py", {
        "runner.py": "import utilsx\n",
        "utils.py": "",
    })
    assert orphan_names(skill) == ["utils.py"]


def test_cli_scans_only_named_skills(tmp_path, capsys, monkeypatch):
    make_skill(tmp_path, "a", "", {"lonely.py": ""})
    b = make_skill(tmp_path, "b", "", {"alone.py": ""})
    monkeypatch.setattr(so, "SKILLS", tmp_path)
    so.main([str(b)])
    out = capsys.readouterr().out
    assert "alone.py" in out and "lonely.py" not in out
    so.main([])
    out = capsys.readouterr().out
    assert "alone.py" in out and "lonely.py" in out
    so.main(["a"])
    assert "lonely.py" in capsys.readouterr().out
