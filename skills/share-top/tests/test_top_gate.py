#!/usr/bin/env python3
"""Regression tests for the aggregate TOP gate."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_DIR / "scripts"


def run_gate(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "top-gate.py"), str(root), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def write_v4_project(root: Path) -> None:
    (root / "_wiki-methodology" / "_top").mkdir(parents=True)
    (root / "_wiki-methodology" / "_top" / "_task_plan.md").write_text(
        "# Plan\n\n> **Current: [P1.1] ship**\n> Done Criteria: concrete gate\n",
        encoding="utf-8",
    )
    (root / "_wiki-methodology" / "_wiki").mkdir(parents=True)
    (root / "_wiki-methodology" / "_wiki" / "README.md").write_text("# Wiki\n", encoding="utf-8")
    (root / "_wiki-methodology" / "_tests").mkdir(parents=True)
    (root / "_wiki-methodology" / "_tests" / "README.md").write_text("# Tests\n", encoding="utf-8")
    (root / "_meta").mkdir()
    (root / "_meta" / "_registry.yml").write_text(
        "entries:\n  - id: api\n    path: src/api.py\n    status: active\n",
        encoding="utf-8",
    )
    (root / "_meta" / "_data_registry.yml").write_text("assets: []\n", encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "api.py").write_text("def api():\n    return 1\n", encoding="utf-8")
    (root / "_codemap.md").write_text("# Map\n", encoding="utf-8")


def init_git(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, text=True, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, text=True, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Topic Test"], cwd=root, text=True, capture_output=True, check=True)
    subprocess.run(["git", "add", "."], cwd=root, text=True, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=root, text=True, capture_output=True, check=True)


def test_top_gate_aggregates_closeout_blocks(tmp_path: Path) -> None:
    write_v4_project(tmp_path)
    init_git(tmp_path)
    (tmp_path / "src" / "new_feature.py").write_text("def run():\n    return 2\n", encoding="utf-8")

    result = run_gate(tmp_path, "--format", "tsv")

    assert result.returncode == 1
    assert "block\tcloseout:CLOSEOUT_CODEMAP_MISSING\t_codemap.md" in result.stdout
    assert "block\tcloseout:CLOSEOUT_REGISTRY_MISSING\t_meta/_registry.yml" in result.stdout


def test_top_gate_text_summary_is_compact(tmp_path: Path) -> None:
    write_v4_project(tmp_path)
    phase_dir = tmp_path / "_wiki-methodology" / "_top" / "_phases"
    phase_dir.mkdir(parents=True)
    (phase_dir / "P1_a.md").write_text("---\nphase_id: P1\n---\n", encoding="utf-8")
    (phase_dir / "P1_b.md").write_text("---\nphase_id: P1\n---\n", encoding="utf-8")

    result = run_gate(tmp_path, "--max-per-severity", "2")

    assert result.returncode == 1
    assert "[top-gate] project=" in result.stdout
    assert "SUMMARY: block=1" in result.stdout
    assert "BLOCK\tlint:PHASE_DUPLICATE\t_wiki-methodology/_top/_phases" in result.stdout


def test_top_gate_returns_zero_without_blocks(tmp_path: Path) -> None:
    write_v4_project(tmp_path)

    result = run_gate(tmp_path, "--format", "tsv")

    assert result.returncode == 0
    assert "\tcloseout:" not in result.stdout
    assert "block\t" not in result.stdout


def test_top_gate_claude_governance_files_are_not_mainline_code(tmp_path: Path) -> None:
    # Editing .claude/ governance (hooks/rules/settings) must NOT demand a
    # codemap/registry closeout — it is not mainline code.
    write_v4_project(tmp_path)
    init_git(tmp_path)
    hooks = tmp_path / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "my-gate.sh").write_text("#!/usr/bin/env bash\necho hi\n", encoding="utf-8")

    result = run_gate(tmp_path, "--format", "tsv")

    assert "CLOSEOUT_CODEMAP_MISSING" not in result.stdout
    assert "CLOSEOUT_REGISTRY_MISSING" not in result.stdout


def test_top_gate_still_flags_mainline_code_without_closeout(tmp_path: Path) -> None:
    # Guard: the governance carve-out must not gut the real check — a changed
    # mainline source file with no codemap/registry update still blocks.
    write_v4_project(tmp_path)
    init_git(tmp_path)
    (tmp_path / "src" / "new_mod.py").write_text("def f():\n    return 1\n", encoding="utf-8")

    result = run_gate(tmp_path, "--format", "tsv")

    assert "CLOSEOUT_CODEMAP_MISSING" in result.stdout


def test_top_gate_claude_skills_code_is_mainline(tmp_path: Path) -> None:
    # Narrowed carve-out (self-review A-F5): executable code under .claude/skills/
    # is real code some projects ship — it must STILL demand a closeout, unlike
    # .claude/hooks|rules|commands|agents governance scripts.
    write_v4_project(tmp_path)
    # Track .claude/ before init so the new file shows as a full path in
    # porcelain output (a brand-new untracked dir collapses to `?? .claude/`).
    scripts = tmp_path / ".claude" / "skills" / "my-skill" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "__init__.py").write_text("", encoding="utf-8")
    init_git(tmp_path)
    (scripts / "run.py").write_text("def run():\n    return 1\n", encoding="utf-8")

    result = run_gate(tmp_path, "--format", "tsv")

    assert "CLOSEOUT_CODEMAP_MISSING" in result.stdout


def test_top_gate_pipelines_and_wiki_root_are_not_mainline_code(tmp_path: Path) -> None:
    # _pipelines/ holds TOP pipeline declarations (validated by doctor --links)
    # and wiki-methodology/ is the knowledge root — neither demands a
    # codemap/registry closeout (self-review A-F6 untested-exclusion gap).
    write_v4_project(tmp_path)
    init_git(tmp_path)
    (tmp_path / "_pipelines").mkdir()
    (tmp_path / "_pipelines" / "train.yml").write_text("pipeline: train\n", encoding="utf-8")
    wiki_scripts = tmp_path / "wiki-methodology" / "scripts"
    wiki_scripts.mkdir(parents=True)
    (wiki_scripts / "gen_index.py").write_text("print('x')\n", encoding="utf-8")

    result = run_gate(tmp_path, "--format", "tsv")

    assert "CLOSEOUT_CODEMAP_MISSING" not in result.stdout
    assert "CLOSEOUT_REGISTRY_MISSING" not in result.stdout
