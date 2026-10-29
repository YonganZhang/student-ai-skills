"""Project initialization keeps one instruction source without rewriting old files."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1]
INIT = SKILL / "scripts" / "init-research.sh"
LINT = SKILL / "scripts" / "lint-claude-md.sh"
REGISTRY_INIT = SKILL / "templates" / "registry-architecture" / "init.sh"
ENTRY = "# Project\n\n- Plan: _wiki-methodology/_top/_task_plan.md\n"


def run(script: Path, target: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(script), str(target), *args],
        text=True, capture_output=True, timeout=60,
    )


def test_full_initialization_uses_only_agents_entry(tmp_path: Path) -> None:
    target = tmp_path / "project"
    result = run(INIT, target, "--kind", "dev", "--with", "full")
    assert result.returncode == 0, result.stderr
    assert (target / "AGENTS.md").is_file()
    assert not list(target.rglob("CLAUDE.md"))
    assert run(LINT, target).returncode == 0


@pytest.mark.parametrize("has_agents", [False, True])
def test_initialization_preserves_existing_instructions(tmp_path: Path, has_agents: bool) -> None:
    target = tmp_path / "project"
    target.mkdir()
    legacy = b"# Existing Claude instructions\n\nKeep the project's special build steps.\n"
    (target / "CLAUDE.md").write_bytes(legacy)
    if has_agents:
        (target / "AGENTS.md").write_text(ENTRY)

    result = run(INIT, target)
    assert (target / "CLAUDE.md").read_bytes() == legacy
    if has_agents:
        assert result.returncode == 0, result.stderr
        assert (target / "AGENTS.md").read_text() == ENTRY
    else:
        assert result.returncode == 2
        assert "先将有效指令迁入 AGENTS.md" in result.stderr
        assert list(target.iterdir()) == [target / "CLAUDE.md"]


@pytest.mark.parametrize("legacy", [None, "@AGENTS.md\n", "# Distinct old rules\n"])
def test_lint_requires_agents_as_the_only_entry(tmp_path: Path, legacy: str | None) -> None:
    (tmp_path / "AGENTS.md").write_text(ENTRY)
    if legacy is not None:
        (tmp_path / "CLAUDE.md").write_text(legacy)
    result = run(LINT, tmp_path)
    assert result.returncode == (0 if legacy is None else 1), result.stdout
    if legacy is not None:
        assert "L0 ERROR" in result.stdout


def test_lint_legacy_only_reports_migration(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text(ENTRY)
    result = run(LINT, tmp_path)
    assert result.returncode == 2
    assert "迁移旧 CLAUDE.md" in result.stdout


@pytest.mark.parametrize("has_agents", [False, True])
def test_registry_installer_only_writes_agents(tmp_path: Path, has_agents: bool) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    legacy = "# Distinct old instructions\n"
    (tmp_path / "CLAUDE.md").write_text(legacy)
    if has_agents:
        (tmp_path / "AGENTS.md").write_text(ENTRY)
    result = run(REGISTRY_INIT, tmp_path)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "CLAUDE.md").read_text() == legacy
    if has_agents:
        agents = (tmp_path / "AGENTS.md").read_text()
        assert agents.startswith(ENTRY)
        assert "_query_registry.py --report" in agents
    else:
        assert not (tmp_path / "AGENTS.md").exists()
        assert "未发现 AGENTS.md" in result.stdout
