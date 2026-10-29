from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from test_sixone_plan_cli import make_project

HINT = Path(__file__).resolve().parents[1] / "scripts" / "top-session-hint.py"


def run_hint(cwd: Path, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    data = json.dumps({"cwd": str(cwd), "hook_event_name": "SessionStart"}) if stdin is None else stdin
    return subprocess.run([sys.executable, str(HINT)], input=data, text=True,
                          capture_output=True, timeout=20, cwd=str(cwd))


def tree_digest(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(root)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def test_normal_project_reports_current_task_read_only(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    before = tree_digest(root)
    result = run_hint(root)
    assert result.returncode == 0
    assert result.stdout.startswith("【TOP 主线】")  # must not start with { or [ (Codex parses those as JSON)
    assert "进行中 P1.0.E1" in result.stdout
    assert "以用户当前请求为准" in result.stdout
    assert tree_digest(root) == before


def test_subdirectory_finds_project_root(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    sub = root / "src" / "deep"
    sub.mkdir(parents=True)
    result = run_hint(sub)
    assert result.returncode == 0 and "进行中 P1.0.E1" in result.stdout


def test_non_top_directory_prints_nothing(tmp_path: Path) -> None:
    result = run_hint(tmp_path)
    assert result.returncode == 0 and result.stdout == ""


def test_conflicting_plan_is_flagged_without_picking_a_task(tmp_path: Path) -> None:
    root = make_project(tmp_path, multi_active=True)
    before = tree_digest(root)
    result = run_hint(root)
    assert result.returncode == 0
    assert "计划存在冲突" in result.stdout and "PLAN_MULTI_INPROGRESS" in result.stdout
    assert "进行中" not in result.stdout and "下一步" not in result.stdout
    assert tree_digest(root) == before


def test_unreadable_plan_reports_read_failure(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    plan = root / "_wiki-methodology" / "_top" / "_task_plan.md"
    plan.chmod(0)
    try:
        result = run_hint(root)
    finally:
        plan.chmod(0o600)
    assert result.returncode == 0 and "读取失败" in result.stdout


def test_garbage_stdin_never_fails(tmp_path: Path) -> None:
    result = run_hint(tmp_path, stdin="not json")
    assert result.returncode == 0


# ---------- Stop / UserPromptSubmit (non-blocking closeout reminder) ----------

import os
import time


def run_event(cwd: Path, event: str, session: str, state: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, TOP_HOOK_STATE=str(state))
    data = json.dumps({"cwd": str(cwd), "hook_event_name": event, "session_id": session})
    return subprocess.run([sys.executable, str(HINT)], input=data, text=True, env=env,
                          capture_output=True, timeout=20, cwd=str(cwd))


def git_project(tmp_path: Path) -> Path:
    root = make_project(tmp_path)
    for args in (["init", "-q"], ["add", "-A"],
                 ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init"]):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    return root


def test_stop_reminds_once_when_work_happened_without_plan_update(tmp_path: Path) -> None:
    root, state = git_project(tmp_path), tmp_path / "state"
    assert "版本：分支" in run_event(root, "SessionStart", "s1", state).stdout
    time.sleep(0.05)
    (root / "work.py").write_text("x = 1\n")
    before = tree_digest(root)
    first = run_event(root, "Stop", "s1", state)
    assert first.returncode == 0
    message = json.loads(first.stdout)["systemMessage"]  # Codex requires JSON for Stop
    assert "收尾提醒" in message and "P1.0.E1" in message and "跟它无关就不用管" in message
    assert "说明原因" not in message                                    # never asks to explain
    assert run_event(root, "Stop", "s1", state).stdout == ""          # same change set: no repeat
    delivered = run_event(root, "UserPromptSubmit", "s1", state).stdout
    assert delivered.startswith("【TOP 收尾提醒】")                      # queued for the model once
    assert "收尾提醒" not in run_event(root, "UserPromptSubmit", "s1", state).stdout
    assert tree_digest(root) == before                                  # hooks never write the project


def test_stop_is_silent_after_plan_update_or_without_changes(tmp_path: Path) -> None:
    root, state = git_project(tmp_path), tmp_path / "state"
    run_event(root, "SessionStart", "s2", state)
    assert run_event(root, "Stop", "s2", state).stdout == ""           # nothing changed
    time.sleep(0.05)
    (root / "work.py").write_text("x = 1\n")
    plan = root / "_wiki-methodology" / "_top" / "_task_plan.md"
    plan.write_text(plan.read_text() + "\n")
    assert run_event(root, "Stop", "s2", state).stdout == ""           # plan updated this session


def test_stop_without_session_or_outside_top_does_nothing(tmp_path: Path) -> None:
    root, state = git_project(tmp_path), tmp_path / "state"
    assert run_event(root, "Stop", "", state).stdout == ""
    outside = tmp_path / "outside"
    outside.mkdir()
    result = run_event(outside, "Stop", "s3", state)
    assert result.returncode == 0 and result.stdout == ""


def test_resume_keeps_queued_reminder(tmp_path: Path) -> None:
    root, state = git_project(tmp_path), tmp_path / "state"
    run_event(root, "SessionStart", "s4", state)
    time.sleep(0.05)
    (root / "work.py").write_text("x = 1\n")
    assert "收尾提醒" in run_event(root, "Stop", "s4", state).stdout
    run_event(root, "SessionStart", "s4", state)                        # resume / compact of same session
    assert run_event(root, "UserPromptSubmit", "s4", state).stdout.startswith("【TOP 收尾提醒】")


# ---------- per-turn compact line and notes ----------


def test_prompt_line_skips_right_after_start_then_shows_task_and_note(tmp_path: Path) -> None:
    root, state = git_project(tmp_path), tmp_path / "state"
    run_event(root, "SessionStart", "s5", state)
    assert run_event(root, "UserPromptSubmit", "s5", state).stdout == ""     # full hint just shown
    subprocess.run([sys.executable, str(HINT.parent / "sixone-cli.py"), "plan", "note", str(root),
                    "--kind", "fail", "loader crashed on empty csv"], check=True, capture_output=True)
    line = run_event(root, "UserPromptSubmit", "s5", state).stdout
    assert line.startswith("【TOP 当前】") and "P1.0.E1" in line
    assert "上次失败" in line and "loader crashed" in line and len(line) < 260
    env_off = dict(os.environ, TOP_HOOK_STATE=str(state), TOP_INJECT="off")
    data = json.dumps({"cwd": str(root), "hook_event_name": "UserPromptSubmit", "session_id": "s5"})
    off = subprocess.run([sys.executable, str(HINT)], input=data, text=True, env=env_off,
                         capture_output=True, timeout=20)
    assert off.returncode == 0 and off.stdout == ""


def test_prompt_line_is_silent_outside_top(tmp_path: Path) -> None:
    outside = tmp_path / "plain"
    outside.mkdir()
    result = run_event(outside, "UserPromptSubmit", "s6", tmp_path / "state")
    assert result.returncode == 0 and result.stdout == ""


def test_note_counts_as_recording_progress(tmp_path: Path) -> None:
    root, state = git_project(tmp_path), tmp_path / "state"
    run_event(root, "SessionStart", "s7", state)
    time.sleep(0.05)
    (root / "work.py").write_text("x = 1\n")
    subprocess.run([sys.executable, str(HINT.parent / "sixone-cli.py"), "plan", "note", str(root),
                    "half way: parser done"], check=True, capture_output=True)
    assert run_event(root, "Stop", "s7", state).stdout == ""                 # note resets the window


def test_start_hint_shows_last_note_without_counting_unrecorded_work(tmp_path: Path) -> None:
    root, state = git_project(tmp_path), tmp_path / "state"
    subprocess.run([sys.executable, str(HINT.parent / "sixone-cli.py"), "plan", "note", str(root),
                    "parser done, writer next"], check=True, capture_output=True)
    (root / "extra.py").write_text("y = 2\n")
    subprocess.run(["git", "-C", str(root), "add", "extra.py"], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "w"],
                   check=True)
    hint = run_event(root, "SessionStart", "s8", state).stdout
    assert "上次进展" in hint and "parser done" in hint
    # commits without a plan step are normal (short or unrelated work stays out of the plan)
    assert "没记进计划" not in hint and "次提交" not in hint
