"""TOP plan x Git: notes, catch-up, duplicate warnings, archive, commit/worktree/merge."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from test_sixone_plan_cli import CLI, make_project, payload, plan_log, run_cli

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
    "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
}


def env_for(tmp_path: Path) -> dict[str, str]:
    return dict(os.environ, GIT_CEILING_DIRECTORIES=str(tmp_path), **GIT_ENV)


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], text=True, capture_output=True,
                            timeout=30, check=True, env=dict(os.environ, **GIT_ENV))
    return result.stdout.strip()


def cli(tmp_path: Path, *args: str) -> dict:
    result = run_cli(*args, env=env_for(tmp_path))
    assert result.returncode == 0, result.stderr
    return payload(result)


def repo_project(tmp_path: Path) -> Path:
    root = make_project(tmp_path)
    plan = root / "_wiki-methodology" / "_top" / "_task_plan.md"
    plan.write_text(plan.read_text(encoding="utf-8").replace(
        "- [ ] P1.0.E2 Second task · dep=P1.0.E1",
        "- [ ] P1.0.E2 Second task · dep=P1.0.E1 · scope=path:src/b.py"), encoding="utf-8")
    plan.write_text(plan.read_text(encoding="utf-8").replace(
        "scope=symbol:Demo", "scope=symbol:Demo · scope=path:src/a.py · gate=test:tests/test_a.py"),
        encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "a.py").write_text("a = 1\n")
    (root / "src" / "b.py").write_text("b = 1\n")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "init")
    return root


def test_note_kinds_show_up_in_plan_show(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    assert cli(tmp_path, "plan", "note", str(root), "loader reads v28 only")["item_id"] == "P1.0.E1"
    cli(tmp_path, "plan", "note", str(root), "--kind", "fail", "fit diverged with alpha=0.9")
    learned = cli(tmp_path, "plan", "note", str(root), "--kind", "learn", "alpha must stay below 0.5")
    assert learned["latest_learning"] == "alpha must stay below 0.5"
    shown = cli(tmp_path, "plan", "show", str(root))
    assert shown["latest_learning"] == "alpha must stay below 0.5"
    assert [n.split()[2] for n in shown["notes"]] == ["progress", "fail", "learn"]
    assert "fit diverged" in shown["notes"][1] and "git=" not in shown["notes"][1]
    assert shown["verdict"] == "ok"                                   # learn kept the plan valid
    bad = run_cli("plan", "note", str(root), "a · b", env=env_for(tmp_path))
    assert payload(bad)["verdict"] == "block"


def test_add_warns_about_same_scope_or_similar_title(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    same_scope = cli(tmp_path, "plan", "add", str(root), "--id", "P1.0.E3", "--title", "Rewrite demo",
                     "--scope", "symbol:Demo")
    assert any("P1.0.E1" in w and "同 scope" in w for w in same_scope["warnings"])
    similar = cli(tmp_path, "plan", "add", str(root), "--id", "P1.0.E4", "--title", "Second task again")
    assert any("P1.0.E2" in w for w in similar["warnings"])
    distinct = cli(tmp_path, "plan", "add", str(root), "--id", "P1.0.E5", "--title", "Unrelated export job")
    assert "warnings" not in distinct


def test_archive_moves_closed_tasks_but_keeps_dependencies(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    for n in range(1, 4):
        cli(tmp_path, "plan", "add", str(root), "--id", f"P1.0.D{n}", "--title", f"Done item number {n} xyz{n}")
        cli(tmp_path, "plan", "complete", str(root), f"P1.0.D{n}", "--evidence", f"e{n}")
    result = cli(tmp_path, "plan", "archive", str(root), "--keep", "1")
    plan = (root / "_wiki-methodology" / "_top" / "_task_plan.md").read_text()
    archive = (root / "_wiki-methodology" / "_top" / "_logs" / "plan-archive.md").read_text()
    assert "P1.0.E0" in plan                     # open P1.0.E1 depends on it
    assert "P1.0.D3" in plan                     # most recent closed group kept
    assert "P1.0.D1" not in plan and "P1.0.D1" in archive and "P1.0.D2" in archive
    assert result["archived"] == 2
    assert cli(tmp_path, "plan", "validate", str(root))["verdict"] == "ok"


def test_complete_commit_on_main_line_commits_only_task_files(tmp_path: Path) -> None:
    root = repo_project(tmp_path)
    (root / "src" / "a.py").write_text("a = 2\n")
    (root / "tests").mkdir()
    (root / "tests" / "test_a.py").write_text("def test_a(): pass\n")
    (root / "src" / "b.py").write_text("b = 2\n")               # another task's file
    (root / "notes.txt").write_text("staged by someone else\n")
    git(root, "add", "notes.txt")
    before = git(root, "rev-list", "--count", "HEAD")
    done = cli(tmp_path, "plan", "complete", str(root), "P1.0.E1", "--evidence", "path:tests/test_a.py",
               "--commit")
    commit = done["git"]["commits"][0]
    assert "error" not in commit, commit
    assert int(git(root, "rev-list", "--count", "HEAD")) == int(before) + 1
    files = set(git(root, "show", "--name-only", "--format=", "HEAD").splitlines())
    assert {"src/a.py", "tests/test_a.py", "_wiki-methodology/_top/_task_plan.md"} <= files
    assert not files & {"src/b.py", "notes.txt"}
    assert "Task: P1.0.E1" in git(root, "log", "-1", "--format=%B")
    assert git(root, "diff", "--cached", "--name-only") == "notes.txt"       # someone's staging kept
    assert done["git"]["uncommitted_outside_scope"]["count"] >= 1
    shown = cli(tmp_path, "plan", "show", str(root))
    assert shown["unrecorded"]["commits"] == 0


def test_unrecorded_counts_commits_and_edits_after_plan_update(tmp_path: Path) -> None:
    root = repo_project(tmp_path)
    (root / "src" / "b.py").write_text("b = 3\n")
    git(root, "commit", "-qam", "work without plan update")
    (root / "src" / "a.py").write_text("a = 9\n")
    unrecorded = cli(tmp_path, "plan", "show", str(root))["unrecorded"]
    assert unrecorded["commits"] == 1 and unrecorded["files"] == 1
    assert cli(tmp_path, "plan", "show", str(root), "--fast")["unrecorded"] is None


def test_worktree_task_commit_merge_and_cleanup(tmp_path: Path) -> None:
    root = repo_project(tmp_path)
    cli(tmp_path, "plan", "complete", str(root), "P1.0.E1", "--evidence", "e", "--commit")
    started = cli(tmp_path, "plan", "start", str(root), "P1.0.E2", "--worktree")
    checkout = Path(started["git"]["checkout"])
    assert checkout == root / ".worktrees" / "P1.0.E2" and checkout.is_dir()
    assert ".worktrees" not in git(root, "status", "--porcelain", "--untracked-files=all")  # excluded
    (checkout / "src" / "b.py").write_text("b = 42\n")
    # plan commands run inside the worktree still update the main worktree's plan
    cli(tmp_path, "plan", "note", str(checkout), "b now returns 42")
    assert "b now returns 42" in plan_log(root).read_text()
    assert "b now returns 42" not in plan_log(checkout).read_text()  # worktree copy untouched
    shown = cli(tmp_path, "plan", "show", str(root))
    assert shown["task_git"]["branch"] == "task/P1.0.E2"
    done = cli(tmp_path, "plan", "complete", str(checkout), "P1.0.E2", "--evidence", "e2", "--commit", "--merge")
    assert done["git"]["merge"]["merge"] == "fast-forward", done["git"]
    assert all("error" not in c for c in done["git"]["commits"]), done["git"]
    assert done["git"]["merge"]["worktree_removed"] and done["git"]["merge"]["branch_deleted"]
    assert (root / "src" / "b.py").read_text() == "b = 42\n"
    assert not checkout.exists() and git(root, "branch", "--list", "task/*") == ""
    # plan + log committed; afterwards only the log line gains `commit=<sha>` (no self-reference)
    code_sha = done["git"]["commits"][0]["commit"]
    assert git(root, "status", "--porcelain") == "M _wiki-methodology/_top/_logs/" + plan_log(root).name
    assert f"commit={code_sha}" in plan_log(root).read_text()
    assert done["git"]["log_commit_stamped"] == code_sha
    assert "state=" not in (root / "_wiki-methodology" / "_top" / "_task_plan.md").read_text().split(
        "P1.0.E2", 1)[1].splitlines()[0]
    assert "merge P1.0.E2" in plan_log(root).read_text()


def test_merge_conflict_is_aborted_and_reported(tmp_path: Path) -> None:
    root = repo_project(tmp_path)
    cli(tmp_path, "plan", "complete", str(root), "P1.0.E1", "--evidence", "e", "--commit")
    checkout = Path(cli(tmp_path, "plan", "start", str(root), "P1.0.E2", "--worktree")["git"]["checkout"])
    (checkout / "src" / "b.py").write_text("b = 'branch'\n")
    git(checkout, "commit", "-qam", "branch edit")
    (root / "src" / "b.py").write_text("b = 'main'\n")
    git(root, "commit", "-qam", "main edit")
    merged = cli(tmp_path, "plan", "merge", str(root), "P1.0.E2")
    assert merged["verdict"] == "warn" and merged["git"]["conflicts"] == ["src/b.py"]
    assert git(root, "status", "--porcelain") == ""                          # merge aborted cleanly
    assert checkout.is_dir() and git(root, "branch", "--list", "task/P1.0.E2")
