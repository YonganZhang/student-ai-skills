"""diff-not-state Stop gate — safety tests.

The catastrophic direction is UNDER-blocking: a real new problem this turn that
the gate silently downgrades to info. Every integration test below uses a REAL
lint block (DONE_CRITERIA_MISSING) on a REAL file — not a synthetic path we
control — because a path-format mismatch would pass a synthetic test while
under-blocking in production.

State is isolated by running top-gate.py with HOME pointed at a temp dir, so the
baseline state files never touch ~/.claude/state or ~/.codex/state.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
GATE = SCRIPTS / "top-gate.py"
SID = "test-session-abc123"

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
}


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True, env={**os.environ, **GIT_ENV})


def build(repo: Path, *, done_criteria: bool = True) -> Path:
    """Minimal v4 project. Without Done Criteria, top-lint emits a real
    `block DONE_CRITERIA_MISSING <task_plan path>`."""
    (repo / "_codemap.md").write_text("# codemap\n", encoding="utf-8")
    top = repo / "_wiki-methodology" / "_top"
    top.mkdir(parents=True, exist_ok=True)
    plan = top / "_task_plan.md"
    body = "# Task Plan\n🧭 当前 [P1] doing the thing\n"
    if done_criteria:
        body += "## Done Criteria\n- ships\n"
    plan.write_text(body, encoding="utf-8")
    return plan


def commit_all(repo: Path, msg: str = "x") -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)


def run_gate(repo: Path, home: Path, *, session: str | None = None,
             since_baseline: bool = False,
             capture_baseline: bool = False) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(GATE), str(repo), "--format", "tsv"]
    if since_baseline:
        cmd += ["--since-baseline"]
    if session is not None:
        cmd += ["--session", session]
    if capture_baseline:
        cmd += ["--capture-baseline"]
    return subprocess.run(cmd, capture_output=True, text=True,
                          env={**os.environ, "HOME": str(home)})


def by_severity(tsv: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for line in tsv.splitlines():
        parts = line.split("\t", 3)
        if len(parts) == 4:
            out.setdefault(parts[0], []).append(parts[1])
    return out


def has_done_block(codes: list[str]) -> bool:
    return any("DONE_CRITERIA_MISSING" in c for c in codes)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "proj"
    r.mkdir()
    git(r, "init", "-q")
    return r


@pytest.fixture
def home(tmp_path: Path) -> Path:
    h = tmp_path / "home"
    h.mkdir()
    return h


# --- THE non-negotiable test --------------------------------------------------
def test_new_block_this_turn_still_blocks(repo, home):
    """Clean repo -> introduce a real block on a real file this turn -> MUST block."""
    build(repo, done_criteria=True)
    commit_all(repo)
    run_gate(repo, home, session=SID, capture_baseline=True)  # baseline = clean HEAD
    build(repo, done_criteria=False)  # this turn introduces the block on task_plan
    r = run_gate(repo, home, session=SID, since_baseline=True)
    sev = by_severity(r.stdout)
    assert has_done_block(sev.get("block", [])), f"new block was swallowed: {r.stdout}"
    assert r.returncode == 1


def test_preexisting_block_on_untouched_file_downgrades(repo, home):
    """Pre-existing block on a file this turn did NOT touch -> info, no block."""
    build(repo, done_criteria=False)  # block already present
    commit_all(repo)
    run_gate(repo, home, session=SID, capture_baseline=True)  # baseline includes block
    (repo / "notes.txt").write_text("touch an unrelated file\n", encoding="utf-8")
    r = run_gate(repo, home, session=SID, since_baseline=True)
    sev = by_severity(r.stdout)
    assert not has_done_block(sev.get("block", [])), f"old debt still blocked: {r.stdout}"
    assert has_done_block(sev.get("info", [])), "downgraded issue should stay visible as info"
    assert r.returncode == 0


def test_commit_mid_turn_still_blocks(repo, home):
    """Introduce a block AND commit it mid-turn -> still attributed to this turn."""
    build(repo, done_criteria=True)
    commit_all(repo)
    run_gate(repo, home, session=SID, capture_baseline=True)  # baseline = clean HEAD
    build(repo, done_criteria=False)
    commit_all(repo, "mid-turn commit")  # the change is now committed, HEAD moved
    r = run_gate(repo, home, session=SID, since_baseline=True)
    sev = by_severity(r.stdout)
    assert has_done_block(sev.get("block", [])), f"committed-mid-turn block lost: {r.stdout}"
    assert r.returncode == 1


# --- fail-closed + back-compat ------------------------------------------------
def test_missing_baseline_fails_closed(repo, home):
    """--session given but no baseline captured -> full mode, blocks (never silent)."""
    build(repo, done_criteria=False)
    commit_all(repo)
    r = run_gate(repo, home, session=SID, since_baseline=True)  # no capture_baseline beforehand
    sev = by_severity(r.stdout)
    assert has_done_block(sev.get("block", [])), f"missing baseline under-blocked: {r.stdout}"
    assert r.returncode == 1


def test_full_mode_without_session_unchanged(repo, home):
    """No --session -> original behavior: every block blocks."""
    build(repo, done_criteria=False)
    commit_all(repo)
    r = run_gate(repo, home)  # no session at all
    sev = by_severity(r.stdout)
    assert has_done_block(sev.get("block", []))
    assert r.returncode == 1


def test_non_git_dir_fails_closed(tmp_path, home):
    """Not a git repo + --session -> cannot diff -> full mode, blocks."""
    repo = tmp_path / "nogit"
    repo.mkdir()
    build(repo, done_criteria=False)
    # capture is a no-op (no git); consume finds no baseline -> full mode
    run_gate(repo, home, session=SID, capture_baseline=True)
    r = run_gate(repo, home, session=SID, since_baseline=True)
    sev = by_severity(r.stdout)
    assert has_done_block(sev.get("block", [])), f"non-git under-blocked: {r.stdout}"
    assert r.returncode == 1


def test_diff_mode_activates_without_session_id(repo, home):
    """If the host omits session_id, --since-baseline must STILL activate diff mode
    (root-only key) — otherwise the spam fix silently does nothing in production."""
    build(repo, done_criteria=False)  # pre-existing block
    commit_all(repo)
    # capture + consume both WITHOUT --session (session_id absent in payload)
    run_gate(repo, home, since_baseline=True, capture_baseline=True)
    (repo / "notes.txt").write_text("unrelated\n", encoding="utf-8")
    r = run_gate(repo, home, since_baseline=True)
    sev = by_severity(r.stdout)
    assert not has_done_block(sev.get("block", [])), f"no-session under-activated: {r.stdout}"
    assert has_done_block(sev.get("info", [])), "should downgrade to info even without session"
    assert r.returncode == 0


def test_nested_project_block_still_blocks(tmp_path, home):
    """project_root != git_root: a new block in a nested project MUST still block.
    Locks the absolute-path normalization on the under-block axis."""
    git_root = tmp_path / "r"
    git_root.mkdir()
    git(git_root, "init", "-q")
    proj = git_root / "sub"
    proj.mkdir()
    build(proj, done_criteria=True)
    git(git_root, "add", "-A")
    git(git_root, "commit", "-q", "-m", "init")
    run_gate(proj, home, session=SID, since_baseline=True, capture_baseline=True)
    build(proj, done_criteria=False)  # introduce block in nested project this turn
    r = run_gate(proj, home, session=SID, since_baseline=True)
    sev = by_severity(r.stdout)
    assert has_done_block(sev.get("block", [])), f"nested project under-blocked: {r.stdout}"
    assert r.returncode == 1


# --- unit: downgrade decision logic ------------------------------------------
def _load_gate_module():
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("top_gate_mod", GATE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["top_gate_mod"] = mod  # so @dataclass can resolve its own module
    spec.loader.exec_module(mod)
    return mod


def test_downgrade_logic_unit(tmp_path):
    mod = _load_gate_module()
    Issue = mod.Issue
    root = tmp_path
    real = (root / "real.md").resolve()
    # touched file stays block; untouched file -> info; path-less (.) -> info
    issues = [
        Issue("block", "S", "STAY", "real.md", "touched this turn"),
        Issue("block", "S", "DROP", "other.md", "untouched debt"),
        Issue("block", "S", "PATHLESS", ".", "project-wide"),
        Issue("warn", "S", "KEEPWARN", "x.md", "warn passes through"),
    ]
    out = {i.code: i.severity for i in mod.apply_diff_downgrade(issues, root, {real})}
    assert out["STAY"] == "block"      # in touched set -> still blocks
    assert out["DROP"] == "info"       # not touched -> downgraded
    assert out["PATHLESS"] == "info"   # path-less -> downgraded (documented limit)
    assert out["KEEPWARN"] == "warn"   # non-block untouched
