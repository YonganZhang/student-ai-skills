from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]
CLI = SKILL / "scripts" / "sixone-cli.py"
TOP_COMMON = SKILL / "scripts" / "top_common.py"


def plan_text(*, multi_active: bool = False) -> str:
    second_state = " · state=in_progress" if multi_active else ""
    return f"""# Demo · Task Plan

🧭 当前 [P1.0] task=[P1.0.E1] First active task
> Done Criteria: finish the controlled plan lifecycle

## Current Coordinate

- Goal: test plan control
- Current task: P1.0.E1
- Next task: P1.0.E2
- Latest learning: none
- Blocker: none

## Active Work

- [x] P1.0.E0 Bootstrap · ev=_tests/bootstrap.txt
- [ ] P1.0.E1 First active task · state=in_progress · dep=P1.0.E0 · scope=symbol:Demo
- [ ] P1.0.E2 Second task{second_state} · dep=P1.0.E1
- [ ] P1.0.M1 Parent task · dep=P1.0.E2
- [ ] P1.0.L1 Later blocked task · state=blocked · dep=P1.0.M1 · reason=waiting for M1
"""


def make_project(tmp_path: Path, *, multi_active: bool = False) -> Path:
    root = tmp_path / "project"
    top = root / "_wiki-methodology" / "_top"
    top.mkdir(parents=True)
    (root / "_codemap.md").write_text("# map\n", encoding="utf-8")
    (top / "_task_plan.md").write_text(plan_text(multi_active=multi_active), encoding="utf-8")
    return root


def run_cli(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        text=True,
        capture_output=True,
        timeout=15,
        env=env,
    )


def no_git_env(tmp_path: Path) -> dict[str, str]:
    """Stop git discovery at tmp_path so an enclosing repository cannot leak in."""
    return dict(os.environ, GIT_CEILING_DIRECTORIES=str(tmp_path))


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.com",
         "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
        text=True, capture_output=True, timeout=15, check=True,
    )
    return result.stdout.strip()


def plan_log(root: Path, day: datetime | None = None) -> Path:
    day = day or datetime.now()
    return root / "_wiki-methodology" / "_top" / "_logs" / f"{day:%Y-%m-%d}-plan.md"


def payload(result: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(result.stdout)


def load_top_common():
    spec = importlib.util.spec_from_file_location("top_common_test", TOP_COMMON)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_show_and_validate_valid_plan(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    shown = run_cli("plan", "show", str(root))
    assert shown.returncode == 0, shown.stderr
    body = payload(shown)
    assert body["phase_id"] == "P1.0"
    assert body["current"]["id"] == "P1.0.E1"
    assert body["next"]["id"] == "P1.0.E2"
    assert body["counts"] == {
        "pending": 2,
        "in_progress": 1,
        "blocked": 1,
        "done": 1,
        "cancelled": 0,
    }
    checked = run_cli("plan", "validate", str(root))
    assert checked.returncode == 0, checked.stdout
    assert payload(checked)["verdict"] == "ok"


def test_complete_start_block_reopen_and_complete(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    completed = run_cli(
        "plan", "complete", str(root), "P1.0.E1",
        "--evidence", "_tests/e1.txt",
    )
    assert completed.returncode == 0, completed.stdout
    after_complete = payload(run_cli("plan", "show", str(root)))
    assert after_complete["current"] is None
    assert after_complete["next"]["id"] == "P1.0.E2"

    started = run_cli("plan", "start", str(root), "P1.0.E2")
    assert started.returncode == 0, started.stdout
    blocked = run_cli(
        "plan", "block", str(root), "P1.0.E2",
        "--reason", "需要补数据 · 保留中文标点",
    )
    assert blocked.returncode == 0, blocked.stdout
    item = payload(run_cli("plan", "inspect", str(root), "P1.0.E2"))["item"]
    assert item["state"] == "blocked"
    assert item["reason"] == "需要补数据 · 保留中文标点"

    reopened = run_cli("plan", "reopen", str(root), "P1.0.E2")
    assert reopened.returncode == 0, reopened.stdout
    assert run_cli("plan", "start", str(root), "P1.0.E2").returncode == 0
    done = run_cli(
        "plan", "complete", str(root), "P1.0.E2",
        "--no-artifact-reason", "状态转换 case 无独立产物",
    )
    assert done.returncode == 0, done.stdout
    assert payload(run_cli("plan", "validate", str(root)))["verdict"] == "ok"


def test_add_child_prevents_parent_completion_then_cancel(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    for item_id in ("P1.0.E1", "P1.0.E2"):
        if item_id == "P1.0.E1":
            result = run_cli("plan", "complete", str(root), item_id, "--evidence", f"_tests/{item_id}.txt")
        else:
            assert run_cli("plan", "start", str(root), item_id).returncode == 0
            result = run_cli("plan", "complete", str(root), item_id, "--evidence", f"_tests/{item_id}.txt")
        assert result.returncode == 0, result.stdout

    added = run_cli(
        "plan", "add", str(root), "--parent", "P1.0.M1",
        "--title", "Discovered repair", "--scope", "path:src/demo.py",
    )
    assert added.returncode == 0, added.stdout
    child_id = payload(added)["item_id"]
    assert child_id == "P1.0.M1.1"

    parent_done = run_cli(
        "plan", "complete", str(root), "P1.0.M1",
        "--evidence", "_tests/m1.txt",
    )
    assert parent_done.returncode == 1
    assert "open children" in payload(parent_done)["errors"][0]

    cancelled = run_cli(
        "plan", "cancel", str(root), child_id,
        "--reason", "route superseded",
    )
    assert cancelled.returncode == 0, cancelled.stdout
    child = payload(run_cli("plan", "inspect", str(root), child_id))["item"]
    assert child["state"] == "cancelled"
    assert child["reason"] == "route superseded"
    assert payload(run_cli("plan", "validate", str(root)))["verdict"] == "ok"


def test_edit_updates_open_task_and_rejects_dependency_cycle(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    edited = run_cli(
        "plan", "edit", str(root), "P1.0.E2",
        "--title", "Second task revised",
        "--remove-dep", "P1.0.E1", "--add-dep", "P1.0.E0",
        "--add-scope", "registry:foo", "--add-gate", "test:g1",
    )
    assert edited.returncode == 0, edited.stdout
    item = payload(run_cli("plan", "inspect", str(root), "P1.0.E2"))["item"]
    assert item["title"] == "Second task revised"
    assert item["deps"] == ["P1.0.E0"]
    assert item["scopes"] == ["registry:foo"]
    assert item["gates"] == ["test:g1"]

    cyclic = run_cli(
        "plan", "edit", str(root), "P1.0.E2", "--add-dep", "P1.0.M1",
    )
    assert cyclic.returncode == 1
    assert "PLAN_DEP_CYCLE" in payload(cyclic)["errors"][0]
    assert payload(run_cli("plan", "validate", str(root)))["verdict"] == "ok"

    closed = run_cli("plan", "edit", str(root), "P1.0.E0", "--title", "rewrite history")
    assert closed.returncode == 1
    assert "closed task cannot be edited" in payload(closed)["errors"][0]


def test_validate_rejects_multiple_in_progress(tmp_path: Path) -> None:
    root = make_project(tmp_path, multi_active=True)
    result = run_cli("plan", "validate", str(root))
    assert result.returncode == 1
    codes = {entry["code"] for entry in payload(result)["errors"]}
    assert "PLAN_MULTI_INPROGRESS" in codes


def test_complete_requires_evidence(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    result = run_cli("plan", "complete", str(root), "P1.0.E1")
    assert result.returncode == 1
    assert "requires --evidence" in payload(result)["errors"][0]


def test_atomic_replace_detects_concurrent_change(tmp_path: Path) -> None:
    module = load_top_common()
    plan = tmp_path / "_task_plan.md"
    plan.write_text("old\n", encoding="utf-8")
    expected = hashlib.sha256(b"old\n").hexdigest()
    plan.write_text("other writer\n", encoding="utf-8")
    try:
        module.atomic_replace_plan(plan, expected, "new\n")
    except module.PlanConflict:
        pass
    else:
        raise AssertionError("expected PlanConflict")
    assert plan.read_text(encoding="utf-8") == "other writer\n"


def test_no_remove_command(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    result = run_cli("plan", "remove", str(root), "P1.0.E1")
    assert result.returncode == 2
    assert "invalid choice" in result.stderr


def test_complete_appends_log_line_with_git_stamp(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init")
    short = git(root, "rev-parse", "--short", "HEAD")

    result = run_cli("plan", "complete", str(root), "P1.0.E1", "--evidence", "_tests/e1.txt")
    assert result.returncode == 0, result.stdout
    log = payload(result)["log"]
    log_file = plan_log(root)
    assert log["file"] == str(log_file)
    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert lines[0] == f"# {datetime.now():%Y-%m-%d} log"
    assert lines[-1] == log["line"]
    # plan file already rewritten before git status -> 1 dirty file
    assert re.fullmatch(
        rf"- \d\d:\d\d complete P1\.0\.E1 First active task · ev=_tests/e1\.txt"
        rf" · git=main@{short}\(\+1 dirty\)",
        log["line"],
    ), log["line"]

    blocked = run_cli("plan", "block", str(root), "P1.0.E2", "--reason", "等数据")
    assert blocked.returncode == 0, blocked.stdout
    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("# ") and lines.count(lines[0]) == 1
    assert " block P1.0.E2 Second task · ev=等数据 · git=main@" in lines[-1]


def test_non_git_project_logs_git_none(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    env = no_git_env(tmp_path)
    result = run_cli(
        "plan", "complete", str(root), "P1.0.E1",
        "--no-artifact-reason", "纯状态切换", env=env,
    )
    assert result.returncode == 0, result.stdout
    line = payload(result)["log"]["line"]
    assert line.endswith(" · ev=no_artifact:纯状态切换 · git=none"), line
    assert plan_log(root).read_text(encoding="utf-8").splitlines()[-1] == line

    cancelled = run_cli("plan", "cancel", str(root), "P1.0.E2", "--reason", "路线作废", env=env)
    assert cancelled.returncode == 0, cancelled.stdout
    assert payload(cancelled)["log"]["line"].endswith("cancel P1.0.E2 Second task · ev=路线作废 · git=none")
    reopened = run_cli("plan", "reopen", str(root), "P1.0.E2", env=env)
    assert reopened.returncode == 0, reopened.stdout
    assert payload(reopened)["log"]["line"].endswith("reopen P1.0.E2 Second task · ev=- · git=none")


def test_no_log_flag_skips_log(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    result = run_cli(
        "plan", "complete", str(root), "P1.0.E1",
        "--evidence", "_tests/e1.txt", "--no-log", env=no_git_env(tmp_path),
    )
    assert result.returncode == 0, result.stdout
    assert payload(result)["log"] is None
    assert not (root / "_wiki-methodology" / "_top" / "_logs").exists()
    assert payload(run_cli("plan", "inspect", str(root), "P1.0.E1"))["item"]["state"] == "done"


def test_log_failure_warns_without_rolling_back_plan(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    (root / "_wiki-methodology" / "_top" / "_logs").write_text("not a dir\n", encoding="utf-8")
    result = run_cli(
        "plan", "complete", str(root), "P1.0.E1",
        "--evidence", "_tests/e1.txt", env=no_git_env(tmp_path),
    )
    assert result.returncode == 0, result.stdout
    body = payload(result)
    assert body["log"]["file"] is None and body["log"]["error"]
    assert "[warn]" in result.stderr
    assert payload(run_cli("plan", "inspect", str(root), "P1.0.E1"))["item"]["state"] == "done"


def test_show_recent_log_reads_today_and_yesterday(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    assert payload(run_cli("plan", "show", str(root)))["recent_log"] == []

    yesterday = datetime.now() - timedelta(days=1)
    old = plan_log(root, yesterday)
    old.parent.mkdir(parents=True)
    old.write_text(
        f"# {yesterday:%Y-%m-%d} log\n\n- 09:00 complete P1.0.X1 a · ev=x · git=none\n"
        "- 10:00 complete P1.0.X2 b · ev=y · git=none\n",
        encoding="utf-8",
    )
    before = old.read_text(encoding="utf-8")
    shown = payload(run_cli("plan", "show", str(root)))["recent_log"]
    assert [line.split()[3] for line in shown] == ["P1.0.X1", "P1.0.X2"]

    env = no_git_env(tmp_path)
    assert run_cli("plan", "complete", str(root), "P1.0.E1", "--evidence", "e", env=env).returncode == 0
    assert run_cli("plan", "start", str(root), "P1.0.E2", env=env).returncode == 0
    assert run_cli("plan", "block", str(root), "P1.0.E2", "--reason", "r", env=env).returncode == 0
    shown = payload(run_cli("plan", "show", str(root)))["recent_log"]
    assert [line.split()[2:4] for line in shown] == [  # start is logged too
        ["complete", "P1.0.E1"],
        ["start", "P1.0.E2"],
        ["block", "P1.0.E2"],
    ]
    assert old.read_text(encoding="utf-8") == before


def test_multiline_reason_and_evidence_are_rejected_without_touching_the_plan(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    plan = root / "_wiki-methodology" / "_top" / "_task_plan.md"
    before = plan.read_text(encoding="utf-8")
    blocked = run_cli("plan", "block", str(root), "P1.0.E1", "--reason", "第一行\n- [ ] X1 注入的任务")
    assert blocked.returncode != 0
    completed = run_cli("plan", "complete", str(root), "P1.0.E1", "--evidence", "a.txt · state=done")
    assert completed.returncode != 0
    assert plan.read_text(encoding="utf-8") == before
    assert payload(run_cli("plan", "validate", str(root)))["verdict"] == "ok"
