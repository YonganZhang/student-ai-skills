"""2026-09-24 absorbed from planning-with-files (3b7690e): insert/replan, 3-strike escalation,
richer per-turn line, compaction recovery card, opt-in stop gate, phase-style template."""

from __future__ import annotations

import re

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from test_sixone_plan_cli import make_project, no_git_env, plan_log, run_cli
from test_top_session_hint import HINT, git_project, run_event, tree_digest

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
from top_common import parse_plan  # noqa: E402

TEMPLATE = SKILL / "tests" / "fixtures" / "outline-minimal"  # old outline project; templates/minimal is Q&A now


def plan_file(root: Path) -> Path:
    return root / "_wiki-methodology" / "_top" / "_task_plan.md"


def cli(tmp_path: Path, *args: str) -> tuple[int, dict]:
    result = run_cli(*args, env=no_git_env(tmp_path))
    return result.returncode, json.loads(result.stdout)


def task_ids(root: Path) -> list[str]:
    return [item.id for item in parse_plan(plan_file(root)).items]


def with_child(tmp_path: Path) -> Path:
    """Demo plan where P1.0.E1 has a child line right below it."""
    root = make_project(tmp_path)
    path = plan_file(root)
    path.write_text(path.read_text().replace(
        "- [ ] P1.0.E2 Second task",
        "- [ ] P1.0.E1.1 Child step\n- [ ] P1.0.E2 Second task").replace(
        "- Next task: P1.0.E2", "- Next task: P1.0.E1.1"))    # the dependency-free child is next
    assert not parse_plan(path).malformed_task_lines
    return root


# ---------- plan insert ----------

def test_insert_goes_after_the_subtree_with_letter_ids(tmp_path: Path) -> None:
    root = with_child(tmp_path)
    code, out = cli(tmp_path, "plan", "insert", str(root), "P1.0.E1", "--title", "Probe", "--reason", "need a probe")
    assert code == 0, out
    assert out["item_id"] == "P1.0.E1a" and out["inserted"][0]["deps"] == []
    assert task_ids(root)[:5] == ["P1.0.E0", "P1.0.E1", "P1.0.E1.1", "P1.0.E1a", "P1.0.E2"]
    # again after the same task: next free letter, placed right after the subtree again
    assert cli(tmp_path, "plan", "insert", str(root), "P1.0.E1", "--title", "Second probe")[1]["item_id"] == "P1.0.E1b"
    assert task_ids(root)[2:5] == ["P1.0.E1.1", "P1.0.E1b", "P1.0.E1a"]
    # after an inserted task the stem is kept: P1.0.E1a -> P1.0.E1c (a, b taken)
    assert cli(tmp_path, "plan", "insert", str(root), "P1.0.E1a", "--title", "Third")[1]["item_id"] == "P1.0.E1c"
    assert cli(tmp_path, "plan", "validate", str(root))[1]["verdict"] == "ok"
    line = plan_log(root).read_text().splitlines()[2]
    assert "insert P1.0.E1a Probe · after=P1.0.E1 · ev=need a probe" in line


def test_insert_change_summary_and_no_rewire_keeps_dependencies(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    code, out = cli(tmp_path, "plan", "insert", str(root), "P1.0.E1", "--title", "Probe", "--gate", "probe ok")
    assert code == 0 and out["rewired"] == []
    summary = out["change_summary"]
    assert len(summary) == 3
    assert summary[0].startswith("改了什么：在 P1.0.E1「First active task」之后插入 P1.0.E1a「Probe」")
    assert "验收：probe ok" in summary[0]
    assert summary[1] == "为什么：未填写（下次用 --reason 写一句原因）"
    assert summary[2].startswith("影响哪些后续任务：没有任务改依赖") and "下一步 P1.0.E1a Probe" in summary[2]
    assert parse_plan(plan_file(root)).by_id()["P1.0.E2"].deps == ["P1.0.E1"]


def test_insert_rewire_moves_open_dependents_but_not_started_ones(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    code, out = cli(tmp_path, "plan", "insert", str(root), "P1.0.E1", "--title", "Probe", "--rewire", "--reason", "gap")
    assert code == 0, out
    by_id = parse_plan(plan_file(root)).by_id()
    assert by_id["P1.0.E1a"].deps == ["P1.0.E1"] and by_id["P1.0.E2"].deps == ["P1.0.E1a"]
    assert out["rewired"] == ["P1.0.E2"]
    assert "P1.0.E2 原依赖 P1.0.E1，现改为依赖 P1.0.E1a" in out["change_summary"][2]
    assert "rewire=P1.0.E2" in plan_log(root).read_text()
    # P1.0.E1 is in progress on P1.0.E0: rewiring must not hang it on a new pending task
    out = cli(tmp_path, "plan", "insert", str(root), "P1.0.E0", "--title", "Late check", "--rewire")[1]
    assert out["rewired"] == [] and by_id["P1.0.E1"].deps == ["P1.0.E0"]
    assert parse_plan(plan_file(root)).by_id()["P1.0.E1"].deps == ["P1.0.E0"]
    assert cli(tmp_path, "plan", "validate", str(root))[1]["verdict"] == "ok"


def test_insert_rejects_unknown_id_and_never_reuses_archived_ids(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    before = plan_file(root).read_text()
    code, out = cli(tmp_path, "plan", "insert", str(root), "P1.0.X9", "--title", "Nope")
    assert code == 1 and "unknown task id" in out["errors"][0]
    assert plan_file(root).read_text() == before
    logs = root / "_wiki-methodology" / "_top" / "_logs"
    logs.mkdir()
    (logs / "plan-archive.md").write_text("# archive\n\n- [x] P1.0.E1a Old probe · ev=x\n")
    assert cli(tmp_path, "plan", "insert", str(root), "P1.0.E1", "--title", "Probe")[1]["item_id"] == "P1.0.E1b"


# ---------- plan replan ----------

def test_replan_cancels_inserts_chain_rewires_and_logs_a_failure(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    assert cli(tmp_path, "plan", "edit", str(root), "P1.0.E2", "--add-gate", "bench < 2s")[0] == 0
    code, out = cli(tmp_path, "plan", "replan", str(root), "P1.0.E2", "--reason", "old loader too slow",
                    "--replace-with", "Try arrow loader", "--replace-with", "Benchmark it")
    assert code == 0, out
    by_id = parse_plan(plan_file(root)).by_id()
    old = by_id["P1.0.E2"]
    assert old.state == "cancelled" and old.reason == "换路线：old loader too slow"
    assert by_id["P1.0.E2a"].deps == ["P1.0.E1"] and by_id["P1.0.E2b"].deps == ["P1.0.E2a"]
    assert by_id["P1.0.E2b"].gates == ["bench < 2s"] and by_id["P1.0.E2a"].gates == []
    assert by_id["P1.0.M1"].deps == ["P1.0.E2b"] and out["rewired"] == ["P1.0.M1"]
    assert task_ids(root)[2:5] == ["P1.0.E2", "P1.0.E2a", "P1.0.E2b"]      # in the old place
    summary = out["change_summary"]
    assert len(summary) == 3
    assert "P1.0.E2「Second task」标为取消（换路线）" in summary[0]
    assert "P1.0.E2a「Try arrow loader」 → P1.0.E2b「Benchmark it」" in summary[0]
    assert summary[1] == "为什么：old loader too slow"
    assert "P1.0.M1 原依赖 P1.0.E2，现改为依赖 P1.0.E2b" in summary[2]
    log = plan_log(root).read_text()
    assert "replan P1.0.E2 Second task · ev=换路线：old loader too slow · to=P1.0.E2a,P1.0.E2b" in log
    assert "note:fail P1.0.E2 换路线：old loader too slow" in log
    assert out["note"]["fail_count"] == 1 and out["note"]["escalate"] is False
    assert cli(tmp_path, "plan", "validate", str(root))[1]["verdict"] == "ok"


def test_replan_of_the_task_in_progress_clears_the_stamp(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    code, out = cli(tmp_path, "plan", "replan", str(root), "P1.0.E1", "--reason", "wrong approach",
                    "--replace-with", "New approach")
    assert code == 0, out
    state = parse_plan(plan_file(root))
    assert state.stamp_task_id == "none" and state.coordinate["next_task"] == "P1.0.E1a"
    assert state.by_id()["P1.0.E1a"].deps == ["P1.0.E0"] and state.by_id()["P1.0.E2"].deps == ["P1.0.E1a"]


def test_replan_refuses_closed_tasks_open_children_and_missing_replacements(tmp_path: Path) -> None:
    root = with_child(tmp_path)
    before = plan_file(root).read_text()
    code, out = cli(tmp_path, "plan", "replan", str(root), "P1.0.E0", "--reason", "x", "--replace-with", "y")
    assert code == 1 and "already closed" in out["errors"][0]
    code, out = cli(tmp_path, "plan", "replan", str(root), "P1.0.E1", "--reason", "x", "--replace-with", "y")
    assert code == 1 and "open children prevent replan: P1.0.E1.1" in out["errors"][0]
    missing = run_cli("plan", "replan", str(root), "P1.0.E2", "--reason", "x", env=no_git_env(tmp_path))
    assert missing.returncode == 2                                        # argparse: --replace-with required
    assert plan_file(root).read_text() == before
    assert not plan_log(root).exists()


# ---------- 3-strike protocol ----------

def test_third_failure_of_one_task_escalates(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    logs = root / "_wiki-methodology" / "_top" / "_logs"
    logs.mkdir()
    old = datetime.now() - timedelta(days=40)                             # counted beyond the 14-day note window
    (logs / f"{old:%Y-%m-%d}-plan.md").write_text(
        f"# {old:%Y-%m-%d} log\n\n- 09:00 note:fail P1.0.E1 tried pandas · git=none\n")
    code, out = cli(tmp_path, "plan", "note", str(root), "--kind", "fail", "tried polars")
    assert code == 0 and out["fail_count"] == 2 and out["escalate"] is False and out["verdict"] == "ok"
    third = run_cli("plan", "note", str(root), "--kind", "fail", "tried duckdb", env=no_git_env(tmp_path))
    out = json.loads(third.stdout)
    assert third.returncode == 0 and out["fail_count"] == 3 and out["escalate"] is True
    assert out["verdict"] == "warn"
    assert out["next_hint"] == "同一任务已失败 3 次：停下来找用户，列出试过的三种做法和各自结果"
    assert "[→ AI 行动] 同一任务已失败 3 次" in third.stderr              # tail note for the AI
    other = cli(tmp_path, "plan", "note", str(root), "--kind", "fail", "--id", "P1.0.E2", "x")[1]
    assert other["fail_count"] == 1 and other["escalate"] is False       # counted per task
    progress = cli(tmp_path, "plan", "note", str(root), "just progress")[1]
    assert "escalate" not in progress and "fail_count" not in progress


def test_replan_counts_toward_escalation(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    for text in ("a failed", "b failed"):
        cli(tmp_path, "plan", "note", str(root), "--kind", "fail", "--id", "P1.0.E2", text)
    out = cli(tmp_path, "plan", "replan", str(root), "P1.0.E2", "--reason", "c failed too",
              "--replace-with", "Ask for data")[1]
    assert out["escalate"] is True and out["note"]["fail_count"] == 3
    assert out["next_hint"].startswith("同一任务已失败 3 次")


# ---------- hooks: per-turn line, recovery card, stop gate ----------

def write_log(root: Path, day: datetime, *lines: str) -> None:
    logs = root / "_wiki-methodology" / "_top" / "_logs"
    logs.mkdir(exist_ok=True)
    (logs / f"{day:%Y-%m-%d}-plan.md").write_text(f"# {day:%Y-%m-%d} log\n\n" + "\n".join(lines) + "\n")


def prompt_line(root: Path, tmp_path: Path) -> str:
    return run_event(root, "UserPromptSubmit", "t1", tmp_path / "state").stdout.strip()


def test_turn_line_shows_next_step_and_recent_failure(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    now = datetime.now()
    write_log(root, now,
              f"- {now - timedelta(minutes=5):%H:%M} note:fail P1.0.E1 csv loader crashed · git=none",
              f"- {now:%H:%M} note:progress P1.0.E1 switched to arrow · git=none")
    line = prompt_line(root, tmp_path)
    assert line.startswith("【TOP 当前】project：进行中 P1.0.E1 First active task")
    assert "｜下一步 P1.0.E2 Second task" in line
    assert "上次失败" in line and "csv loader crashed" in line
    assert "上次进展" in line and "switched to arrow" in line
    assert line.endswith("（只读，以用户当前请求为准）") and "\n" not in line and len(line) <= 200


def test_turn_line_drops_failures_older_than_a_day(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    old = datetime.now() - timedelta(days=3)
    write_log(root, old, "- 10:00 note:fail P1.0.E1 csv loader crashed · git=none",
              "- 10:05 note:progress P1.0.E1 switched to arrow · git=none")
    line = prompt_line(root, tmp_path)
    assert "上次失败" not in line and "上次进展" in line


def test_turn_line_is_truncated_but_keeps_its_suffix(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    path = plan_file(root)
    path.write_text(path.read_text().replace("First active task", "First " + "very long title " * 12)
                    .replace("Second task", "Second " + "long " * 30))
    now = datetime.now()
    write_log(root, now, f"- {now:%H:%M} note:fail P1.0.E1 {'boom ' * 60}· git=none")
    line = prompt_line(root, tmp_path)
    assert len(line) <= 200 and line.endswith("（只读，以用户当前请求为准）") and "…" in line


def test_precompact_prints_a_bounded_recovery_card_read_only(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    assert cli(tmp_path, "plan", "edit", str(root), "P1.0.E1", "--add-gate", "pytest -q tests/test_demo.py")[0] == 0
    now = datetime.now()
    write_log(root, now, f"- {now:%H:%M} note:fail P1.0.E1 fixture missing · git=none")
    before = tree_digest(root)
    card = run_event(root, "PreCompact", "c1", tmp_path / "state")
    assert card.returncode == 0
    text = card.stdout.strip()
    assert text.startswith("【TOP 恢复卡】project") and len(text) <= 800
    for expected in ("目标：test plan control", "当前：P1.0.E1 First active task｜验收：pytest -q tests/test_demo.py",
                     "下一步：P1.0.E2 Second task", "上次失败", "fixture missing",
                     "计划：" + str(plan_file(root)), "接上前先 `plan` 和 `plan 当前`"):
        assert expected in text, expected
    assert tree_digest(root) == before
    # SessionStart after a compaction delivers the same card to the model (PreCompact stdout is not shown)
    env = dict(os.environ, TOP_HOOK_STATE=str(tmp_path / "state"))
    data = json.dumps({"cwd": str(root), "hook_event_name": "SessionStart", "source": "compact", "session_id": "c1"})
    after = subprocess.run([sys.executable, str(HINT)], input=data, text=True, env=env, capture_output=True, timeout=20)
    assert after.returncode == 0 and after.stdout.strip() == text


def test_recovery_card_stays_under_800_chars(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    path = plan_file(root)
    path.write_text(path.read_text().replace("- Goal: test plan control", "- Goal: " + "目标很长" * 200)
                    .replace("- Latest learning: none", "- Latest learning: " + "心得" * 200)
                    .replace("- Blocker: none", "- Blocker: " + "卡住" * 200))
    text = run_event(root, "PreCompact", "c2", tmp_path / "state").stdout.strip()
    assert len(text) <= 800 and "计划：" in text and "`plan 当前`" in text


def test_precompact_is_silent_outside_top_and_survives_garbage(tmp_path: Path) -> None:
    outside = tmp_path / "plain"
    outside.mkdir()
    result = run_event(outside, "PreCompact", "c3", tmp_path / "state")
    assert result.returncode == 0 and result.stdout == ""
    for garbage in ("{not json", "[]", '{"hook_event_name": "PreCompact", "cwd": 42}'):
        bad = subprocess.run([sys.executable, str(HINT)], input=garbage, text=True,
                             capture_output=True, timeout=20, cwd=str(outside))
        assert bad.returncode == 0


def stop_message(root: Path, tmp_path: Path, session: str) -> str:
    state = tmp_path / "state"
    run_event(root, "SessionStart", session, state)
    time.sleep(0.05)
    (root / f"work_{session}.py").write_text("x = 1\n")
    result = run_event(root, "Stop", session, state)
    assert result.returncode == 0
    return json.loads(result.stdout)["systemMessage"]


def test_stop_gate_is_off_by_default(tmp_path: Path) -> None:
    root = git_project(tmp_path)
    assert cli(tmp_path, "plan", "edit", str(root), "P1.0.E1", "--add-gate", "pytest ok")[0] == 0
    message = stop_message(root, tmp_path, "g1")
    assert message.startswith("【TOP 收尾提醒】") and "完成门" not in message


def test_stop_gate_on_firms_up_wording_for_a_gated_task(tmp_path: Path) -> None:
    root = git_project(tmp_path)
    subprocess.run(["git", "-C", str(root), "config", "top.stopGate", "true"], check=True)
    assert cli(tmp_path, "plan", "edit", str(root), "P1.0.E1", "--add-gate", "pytest ok")[0] == 0
    before = plan_file(root).read_text()
    message = stop_message(root, tmp_path, "g2")
    assert message.startswith("【TOP 收尾提醒·完成门】") and "P1.0.E1" in message
    assert "声明了验收：pytest ok" in message and "plan complete P1.0.E1" in message
    assert "不阻止结束" in message and len(message) <= 900
    assert plan_file(root).read_text() == before                          # still read-only, never blocks


def test_stop_gate_on_without_a_task_gate_keeps_normal_wording(tmp_path: Path) -> None:
    root = git_project(tmp_path)
    subprocess.run(["git", "-C", str(root), "config", "top.stopGate", "true"], check=True)
    message = stop_message(root, tmp_path, "g3")
    assert message.startswith("【TOP 收尾提醒】") and "完成门" not in message


# ---------- template ----------

def test_phase_template_validates_and_takes_steps_under_phases(tmp_path: Path) -> None:
    root = tmp_path / "fresh"
    shutil.copytree(TEMPLATE, root)
    code, out = cli(tmp_path, "plan", "validate", str(root))
    assert code == 0 and out["verdict"] == "ok", out
    text = plan_file(root).read_text()
    # planning-with-files order: goal, where we are, the phases (a table of contents), then the rest
    order = [text.index(marker) for marker in ("## 目标", "## 现在", "## 各阶段", "### P1 ", "## 关键问题", "## 决定", "## 错误")]
    assert order == sorted(order)
    state = parse_plan(plan_file(root))
    assert state.outline and [phase.id for phase in state.phases] == ["P1"]
    assert [item.id for item in state.items] == ["P1.1"]
    assert cli(tmp_path, "plan", "next", str(root))[1]["ready"][0]["id"] == "P1.1"
    assert cli(tmp_path, "plan", "add", str(root), "--parent", "P1", "--title", "List constraints")[1]["item_id"] == "P1.2"
    assert cli(tmp_path, "plan", "start", str(root), "P1.2")[0] == 0
    assert cli(tmp_path, "plan", "insert", str(root), "P1.1", "--title", "Spike", "--rewire")[1]["item_id"] == "P1.1a"
    assert cli(tmp_path, "plan", "validate", str(root))[1]["verdict"] == "ok"


def test_add_with_parent_places_step_after_its_phase_subtree(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    added = run_cli("plan", "add", str(root), "--parent", "P1.0.E1", "--title", "第一个子步骤")
    assert added.returncode == 0, added.stdout
    lines = (root / "_wiki-methodology" / "_top" / "_task_plan.md").read_text(encoding="utf-8").splitlines()
    ids = [re.match(r"^\s*- \[[ xX]\] (\S+)", line).group(1) for line in lines if re.match(r"^\s*- \[[ xX]\] ", line)]
    assert ids.index("P1.0.E1.1") == ids.index("P1.0.E1") + 1      # not appended at the end
    assert json.loads(run_cli("plan", "validate", str(root)).stdout)["verdict"] == "ok"
