"""2026-09-26 `plan`: the short, text-first front end (scripts/plan → top_plan_cli.py).

Reads print a few plain lines; writes answer in one or two; old sixone-style calls pass through."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
PLAN = SKILL / "scripts" / "plan"
TEMPLATE = SKILL / "tests" / "fixtures" / "outline-minimal"  # old outline project; templates/minimal is Q&A now
sys.path.insert(0, str(SKILL / "scripts"))
from top_common import parse_plan  # noqa: E402


def env_for(tmp_path: Path) -> dict[str, str]:
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(tmp_path), TOP_PROJECTS_DIR=str(tmp_path / "projects"),
               TMUX_TMPDIR=str(tmp_path / "no-tmux"))   # no tmux server: window lookups find nothing
    env.pop("TMUX", None)
    (tmp_path / "no-tmux").mkdir(exist_ok=True)
    return env


def plan(tmp_path: Path, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(PLAN), *args], cwd=cwd, env=env_for(tmp_path), capture_output=True,
                          text=True, timeout=30, stdin=subprocess.DEVNULL)


def ok(tmp_path: Path, cwd: Path, *args: str) -> str:
    result = plan(tmp_path, cwd, *args)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def project(tmp_path: Path, name: str = "trip") -> Path:
    root = tmp_path / "projects" / name
    shutil.copytree(TEMPLATE, root)
    return root


def trip(tmp_path: Path) -> Path:
    root = project(tmp_path)
    for args in (("goal", "国庆去北京长城：机票酒店都订好"),
                 ("summary", "P1", "先问清人数和预算，后面按这里来。"),
                 ("add", "确认放假日期"),
                 ("phase", "查行情", "--summary", "问清需求后查票。"),
                 ("add", "查往返机票", "--to", "P2", "--gate", "两家报价"),
                 ("add", "查酒店", "--to", "P2"),
                 ("start", "P1.1"), ("done", "P1.1", "--ev", "findings.md#需求"),
                 ("block", "P1.2", "等放假通知"), ("start", "P2.1")):
        ok(tmp_path, root, *args)
    return root


def test_help_is_one_screen_with_every_verb() -> None:
    # the outline (目录格式) cheat sheet is `plan help 旧`; a bare `plan help` outside an old-format
    # project shows the question-and-answer one (tests/test_plan_qa.py)
    out = subprocess.run([str(PLAN), "help", "旧"], capture_output=True, text=True, timeout=10).stdout
    assert len(out.splitlines()) <= 40
    for verb in ("plan ls", "plan add", "plan insert", "plan done", "plan block", "plan replan", "plan rename",
                 "plan note", "plan phase", "plan summary", "plan drop", "plan goal", "plan rewrite", "--细节"):
        assert verb in out


def test_core_view_is_short_text(tmp_path: Path) -> None:
    root = trip(tmp_path)
    out = ok(tmp_path, root)
    assert out.splitlines() == [
        "trip · 目标：国庆去北京长城：机票酒店都订好",
        "  ⏸ 1 P1 摸清要做什么",
        "→ 🔄 2 P2 查行情",
        "正在做：P2.1 查往返机票（验收：两家报价）",
        "下一步：P2.2 查酒店",
        "卡点：P1.2 确认放假日期（等放假通知）",
    ]
    assert not out.lstrip().startswith("{")


def test_plan_now_outline_uses_outline_view(tmp_path: Path) -> None:
    root = project(tmp_path)
    out = ok(tmp_path, root, "now")
    assert "P1" in out and "下一步：P1.1" in out
    assert "问答（" not in out


def test_phase_scopes_and_details(tmp_path: Path) -> None:
    root = trip(tmp_path)
    current = ok(tmp_path, root, "当前")
    assert current.splitlines()[0] == "第 2/2 阶段 · P2 查行情（进行中，0/2）"
    assert "  ▶ P2.1 查往返机票（验收：两家报价）" in current and "  小结：问清需求后查票。" in current
    assert ok(tmp_path, root, "prev").splitlines()[0].startswith("第 1/2 阶段 · P1 ")
    assert ok(tmp_path, root, "上一") == ok(tmp_path, root, "P1")
    assert "当前已经是最后一个阶段" in plan(tmp_path, root, "下一").stdout
    everything = ok(tmp_path, root, "全部")
    assert "P1.2 确认放假日期（等放假通知）" in everything and "P2.2 查酒店" in everything
    assert "还没有细节文章" in ok(tmp_path, root, "P2", "--细节")
    (root / "_wiki-methodology" / "_top" / "_plan_details.md").write_text(
        "# 细节\n\n## P1 摸清要做什么\n\n- 一\n\n## P2 查行情\n\n- 大兴 1830 元\n", encoding="utf-8")
    detailed = ok(tmp_path, root, "P2", "--details")
    assert "## P2 查行情" in detailed and "大兴 1830 元" in detailed and "## P1" not in detailed


def test_other_projects_by_name_or_path_and_ls(tmp_path: Path) -> None:
    root = trip(tmp_path)
    other = project(tmp_path, "novel-world")
    assert ok(tmp_path, other, "trip", "当前") == ok(tmp_path, root, "当前")
    assert ok(tmp_path, other, str(root)) == ok(tmp_path, root)
    project(tmp_path, "trip-2")
    ambiguous = plan(tmp_path, other, "trip")
    assert ambiguous.returncode == 1 and "对上 2 个项目" in ambiguous.stdout
    listing = ok(tmp_path, other, "ls", "--all")
    assert any("trip " in line and "2/2 查行情" in line and "▶ 查往返机票" in line and "卡 1" in line
               for line in listing.splitlines())
    assert "novel-world" in listing
    outside = plan(tmp_path, tmp_path, "当前")
    assert outside.returncode == 1 and "不在任何有计划的项目里" in outside.stdout


def test_writes_answer_in_a_line_or_two(tmp_path: Path) -> None:
    root = trip(tmp_path)
    out = ok(tmp_path, root, "add", "比价", "--gate", "三家对比")
    assert out.splitlines() == ["已加 P2.3「比价」", "现在：第 2/2 阶段；正在做 P2.1 查往返机票；下一步 P2.2 查酒店"]
    insert = ok(tmp_path, root, "insert", "P2.1", "顺便查高铁", "--why", "比价")
    assert insert.startswith("改了什么：在 P2.1「查往返机票」之后插入 P2.1a「顺便查高铁」")
    assert ok(tmp_path, root, "done", "P2.1", "--ev", "findings.md#机票").startswith("完成 P2.1")
    assert ok(tmp_path, root, "rename", "P2.2", "查城区酒店").startswith("改名 P2.2")
    assert ok(tmp_path, root, "rename", "P2", "查票").startswith("改名 P2")
    assert ok(tmp_path, root, "note", "大兴没票", "--fail", "--on", "P2.2").startswith("已记（失败，P2.2）")
    ok(tmp_path, root, "phase", "下单")
    ok(tmp_path, root, "add", "付款前确认", "--to", "P3")
    assert ok(tmp_path, root, "drop", "P3", "改成自驾").startswith("放弃阶段 P3（取消 1 步）")
    state = parse_plan(root / "_wiki-methodology" / "_top" / "_task_plan.md")
    assert [p.title for p in state.phases] == ["摸清要做什么", "查票", "下单"]
    assert {i.id: i.state for i in state.items}["P2.1"] == "done"


def test_errors_are_plain_and_fuzzy_writes_to_other_projects_are_refused(tmp_path: Path) -> None:
    root = trip(tmp_path)
    for args, text in ((("done", "P2.2"), "完成要给证据"),
                       (("start", "P2.2"), "已经有一步在做（P2.1）"),
                       (("drop", "P9", "x"), "没有阶段 P9"),
                       (("add", "子步骤", "--to", "P2.1"), "两层"),
                       (("add", "x", "-p", "trip"), "不接受模糊名字"),
                       (("add",), "用法：plan add")):
        result = plan(tmp_path, root, *args)
        assert result.returncode == 1 and text in result.stdout, (args, result.stdout)
    other = project(tmp_path, "other")
    out = ok(tmp_path, other, "note", "替别人记一笔", "-p", str(root))
    assert "改的是别的项目 trip 的计划" in out


def test_json_and_old_sixone_style_still_work(tmp_path: Path) -> None:
    root = trip(tmp_path)
    assert json.loads(ok(tmp_path, root, "--json"))["format"] == "outline"
    assert json.loads(ok(tmp_path, root, "show", "--fast"))["tool"] == "plan-show"
    old = json.loads(ok(tmp_path, root, "complete", str(root), "P2.1", "--evidence", "x"))
    assert old["tool"] == "plan-complete" and old["verdict"] == "ok"
    assert json.loads(ok(tmp_path, root, "add", "y", "--json"))["item_id"] == "P2.3"


def test_legacy_plan_view_points_to_the_rewrite(tmp_path: Path) -> None:
    from test_sixone_plan_cli import make_project
    root = make_project(tmp_path)
    out = ok(tmp_path, root)
    assert "旧格式计划" in out and "plan rewrite" in out and "正在做：P1.0.E1 First active task" in out


def test_long_note_with_slash_is_text_not_a_project_path(tmp_path: Path) -> None:
    root = trip(tmp_path)
    note = "对照 A/B 两版结果：" + "数据清洗与指标核对完成；" * 40
    assert ok(tmp_path, root, "note", note, "--on", "P2.1").startswith("已记（进展，P2.1）")
