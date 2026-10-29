#!/usr/bin/env python3
"""Regression tests for TOP planning status/lint helpers."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS))

from top_common import current_phase_from_text, current_stamp_token_from_text, frontmatter_value, phase_files_for, project_root  # noqa: E402


def write_plan(root: Path, body: str) -> Path:
    top = root / "_wiki-methodology" / "_top"
    top.mkdir(parents=True)
    plan = top / "_task_plan.md"
    plan.write_text(body, encoding="utf-8")
    return top


def run_tool(script: str, root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), str(root), "--format", "tsv"] if script == "top-lint.py" else [sys.executable, str(SCRIPTS / script), str(root)],
        text=True,
        capture_output=True,
        check=False,
    )


def test_phase_only_comes_from_current_stamp_line() -> None:
    text = """# Plan

> Done Criteria: compare with [P2] and write a conclusion
"""
    assert current_stamp_token_from_text(text) == ""
    assert current_phase_from_text(text) == ""


def test_current_stamp_is_case_insensitive_and_allows_non_p_token() -> None:
    p_text = "> **current: [P1.2] run pilot**"
    non_p_text = "> **Current: [配置 multi-node] inspect config**"

    assert current_stamp_token_from_text(p_text) == "P1.2"
    assert current_phase_from_text(p_text) == "P1.2"
    assert current_stamp_token_from_text(non_p_text) == "配置 multi-node"
    assert current_phase_from_text(non_p_text) == ""


def test_frontmatter_allows_leading_blank_and_bom() -> None:
    text = "\ufeff\n\n---\nphase_id: P3.2\n---\nbody\n"
    assert frontmatter_value(text, "phase_id") == "P3.2"


def test_project_root_walks_up_from_nested_paths(tmp_path: Path) -> None:
    project = tmp_path / "project"
    nested = project / "_code" / "pkg"
    nested.mkdir(parents=True)
    (project / "_codemap.md").write_text("# map\n", encoding="utf-8")

    assert project_root(nested) == project


def test_phase_files_match_top_level_phase_only(tmp_path: Path) -> None:
    top = write_plan(
        tmp_path,
        """# Plan

> **🧭 当前: [P2.3] work**
> Done Criteria: produce a concrete gate
""",
    )
    phases = top / "_phases"
    phases.mkdir()
    expected = phases / "P2_work.md"
    expected.write_text("---\nphase_id: P2\n---\n", encoding="utf-8")
    (phases / "P20_wrong.md").write_text("---\nphase_id: P20\n---\n", encoding="utf-8")
    (phases / "P2a_wrong.md").write_text("---\nphase_id: P2a\n---\n", encoding="utf-8")

    assert phase_files_for(top, "P2.3") == [expected]


def test_top_status_prints_valid_phase(tmp_path: Path) -> None:
    top = write_plan(
        tmp_path,
        """# Plan

> **🧭 当前: [P0.1] frame problem**
> Done Criteria: produce a concrete gate
""",
    )
    phases = top / "_phases"
    phases.mkdir()
    (phases / "P0_problem.md").write_text(
        """---
phase_id: P0
---

# Problem

- [x] define target
- [ ] write acceptance gate
""",
        encoding="utf-8",
    )

    result = run_tool("top-status.py", tmp_path)

    assert result.returncode == 0
    assert "- phase_id: P0.1" in result.stdout
    assert "- checklist: done=1 open=1 total=2" in result.stdout
    assert "## Freshness" in result.stdout
    assert "- task_plan_updated:" in result.stdout


def test_top_status_counts_checkboxes_beyond_display_head(tmp_path: Path) -> None:
    top = write_plan(
        tmp_path,
        """# Plan

> **🧭 当前: [P2.1] long phase**
> Done Criteria: count the whole phase checklist
""",
    )
    phases = top / "_phases"
    phases.mkdir()
    padding = "\n".join(f"intro line {index}" for index in range(30))
    (phases / "P2_long.md").write_text(
        f"""---
phase_id: P2
---

# Long Phase

{padding}
- [x] late done
- [ ] late open
""",
        encoding="utf-8",
    )

    result = run_tool("top-status.py", tmp_path)

    assert result.returncode == 0
    assert "- checklist: done=1 open=1 total=2" in result.stdout


def test_lint_blocks_stray_phase_without_current_stamp(tmp_path: Path) -> None:
    write_plan(
        tmp_path,
        """# Plan

> Done Criteria: compare with [P2] and write a conclusion
""",
    )

    result = run_tool("top-lint.py", tmp_path)

    assert result.returncode == 1
    assert "STAMP_MISSING" in result.stdout
    assert "NON_PHASE_STAMP" not in result.stdout


def test_duplicate_filename_phase_reports_once(tmp_path: Path) -> None:
    top = write_plan(
        tmp_path,
        """# Plan

> **🧭 当前: [P1.1] design**
> Done Criteria: produce a concrete gate
""",
    )
    phases = top / "_phases"
    phases.mkdir()
    (phases / "P1_a.md").write_text("---\nphase_id: P1\n---\n", encoding="utf-8")
    (phases / "P1_b.md").write_text("---\nphase_id: P1\n---\n", encoding="utf-8")

    result = run_tool("top-lint.py", tmp_path)

    assert result.returncode == 1
    assert result.stdout.count("PHASE_DUPLICATE\t") == 1
    assert "PHASE_DUPLICATE_YAML" not in result.stdout


def test_duplicate_yaml_phase_across_filename_groups_blocks(tmp_path: Path) -> None:
    top = write_plan(
        tmp_path,
        """# Plan

> **🧭 当前: [P0.1] frame**
> Done Criteria: produce a concrete gate
""",
    )
    phases = top / "_phases"
    phases.mkdir()
    (phases / "P1_real.md").write_text("---\nphase_id: P1\n---\n", encoding="utf-8")
    (phases / "P2_wrong.md").write_text("---\nphase_id: P1\n---\n", encoding="utf-8")

    result = run_tool("top-lint.py", tmp_path)

    assert result.returncode == 1
    assert "PHASE_DUPLICATE_YAML" in result.stdout


def test_lint_reports_multiple_independent_faults(tmp_path: Path) -> None:
    top = write_plan(
        tmp_path,
        """# Plan

> Done Criteria: TBD
""",
    )
    phases = top / "_phases"
    phases.mkdir()
    (phases / "P1_a.md").write_text("---\nphase_id: P1\n---\n", encoding="utf-8")
    (phases / "P1_b.md").write_text("---\nphase_id: P1\n---\n", encoding="utf-8")
    findings = top / "_findings"
    findings.mkdir()
    (findings / "bad.md").write_text("# Bad Finding\n\n## Evidence\n- x\n", encoding="utf-8")
    logs = top / "_logs"
    logs.mkdir()
    (logs / "polluted.md").write_text(
        "---\nphase_id: nope\n---\n\n# Log\n\n## Decision\nThis should not be in a log.\n",
        encoding="utf-8",
    )

    result = run_tool("top-lint.py", tmp_path)

    assert result.returncode == 1
    for code in (
        "STAMP_MISSING",
        "DONE_CRITERIA_WEAK",
        "PHASE_DUPLICATE",
        "FINDING_PHASE_ID",
        "FINDING_SHAPE",
        "LOG_PHASE_ID",
        "LOG_POLLUTION",
    ):
        assert code in result.stdout
