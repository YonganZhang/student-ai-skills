"""2026-09-26 outline (目录格式) plans: the plan reads like planning-with-files' task_plan.md —
goal, where we are, a table of contents of 3–7 phases with a one-sentence summary each, plain
steps under them — while IDs, gates and evidence stay in trailing HTML comments."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from test_sixone_plan_cli import no_git_env, run_cli
from test_top_session_hint import run_event

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
from top_common import parse_plan  # noqa: E402

TEMPLATE = SKILL / "tests" / "fixtures" / "outline-minimal"  # old outline project; templates/minimal is Q&A now


def plan_file(root: Path) -> Path:
    return root / "_wiki-methodology" / "_top" / "_task_plan.md"


def cli(tmp_path: Path, *args: str) -> tuple[int, dict]:
    result = run_cli(*args, env=no_git_env(tmp_path))
    return result.returncode, json.loads(result.stdout)


def ok(tmp_path: Path, *args: str) -> dict:
    code, out = cli(tmp_path, *args)
    assert code == 0 and out.get("verdict") != "block", out
    return out


def fresh(tmp_path: Path) -> Path:
    root = tmp_path / "trip"
    shutil.copytree(TEMPLATE, root)
    return root


def trip(tmp_path: Path) -> Path:
    """Template → a three-phase trip plan with one blocked and one running step."""
    root = fresh(tmp_path)
    p = str(root)
    ok(tmp_path, "plan", "goal", p, "国庆去北京长城：机票、酒店、门票都订好")
    ok(tmp_path, "plan", "phase", "edit", p, "P1", "--title", "问清需求", "--summary", "先问清人数和预算，后面按这里来。")
    ok(tmp_path, "plan", "add", p, "--parent", "P1", "--title", "确认放假日期")
    ok(tmp_path, "plan", "phase", "add", p, "--title", "查行情", "--summary", "问清需求后查票，每查两处写进 findings。")
    ok(tmp_path, "plan", "add", p, "--parent", "P2", "--title", "查往返机票", "--gate", "findings 有两家报价")
    ok(tmp_path, "plan", "add", p, "--parent", "P2", "--title", "查酒店")
    ok(tmp_path, "plan", "phase", "add", p, "--title", "下单")
    ok(tmp_path, "plan", "add", p, "--parent", "P3", "--title", "付款前请用户确认金额")
    ok(tmp_path, "plan", "start", p, "P1.1")
    ok(tmp_path, "plan", "complete", p, "P1.1", "--evidence", "findings.md#需求")
    ok(tmp_path, "plan", "start", p, "P1.2")
    ok(tmp_path, "plan", "block", p, "P1.2", "--reason", "等放假通知")
    ok(tmp_path, "plan", "start", p, "P2.1")
    return root


def test_template_is_an_outline_plan_that_validates(tmp_path: Path) -> None:
    root = fresh(tmp_path)
    state = parse_plan(plan_file(root))
    assert state.outline and [phase.id for phase in state.phases] == ["P1"]
    assert state.phases[0].summary.startswith("先把目标")
    out = ok(tmp_path, "plan", "validate", str(root))
    assert out["verdict"] == "ok" and out["warnings"] == []
    shown = ok(tmp_path, "plan", "show", str(root), "--fast")
    assert shown["format"] == "outline" and shown["phase"]["id"] == "P1" and shown["phase_count"] == 1
    assert shown["next"]["id"] == "P1.1" and shown["questions"] == [] and shown["now_stale"] is False


def test_the_file_reads_as_a_table_of_contents(tmp_path: Path) -> None:
    root = trip(tmp_path)
    text = plan_file(root).read_text(encoding="utf-8")
    assert "### P1 问清需求 ⏸" in text          # only open step is blocked
    assert "### P2 查行情 🔄" in text and "### P3 下单 ⏳" in text
    assert "- [x] P1.1 问清目标、约束和怎样算做完 <!-- ev=findings.md#需求 -->" in text
    assert "- [ ] P2.1 查往返机票 <!-- state=in_progress · gate=findings 有两家报价 -->" in text
    assert "- [ ] P2.2 查酒店\n" in text           # no metadata, no comment
    now = text.split("## 现在", 1)[1].split("## 各阶段", 1)[0]
    assert "- 阶段：第 2/3 阶段 · P2 查行情" in now
    assert "- 正在做：P2.1 查往返机票" in now and "- 下一步：P2.2 查酒店" in now
    assert "- 卡点：P1.2 等放假通知" in now
    assert "\n\n\n" not in text                    # edits never pile up blank lines
    # the heading order is the planning-with-files one
    order = [text.index(h) for h in ("## 目标", "## 现在", "## 各阶段", "### P1", "### P2", "### P3", "## 关键问题")]
    assert order == sorted(order)


def test_show_gives_the_core_for_people_and_hints(tmp_path: Path) -> None:
    root = trip(tmp_path)
    shown = ok(tmp_path, "plan", "show", str(root), "--fast")
    assert shown["goal"] == "国庆去北京长城：机票、酒店、门票都订好"
    assert [(p["id"], p["state"], p["done"], p["total"]) for p in shown["phases"]] == [
        ("P1", "blocked", 1, 2), ("P2", "in_progress", 0, 2), ("P3", "pending", 0, 1)]
    assert shown["phase"]["id"] == "P2" and shown["phase"]["summary"].startswith("问清需求后")
    assert shown["blockers"] == [{"id": "P1.2", "title": "确认放假日期", "reason": "等放假通知"}]
    assert "第 2/3 阶段 查行情" in shown["next_hint"]
    listed = ok(tmp_path, "plan", "list", str(root))
    assert {item["id"]: item["phase"] for item in listed["items"]}["P2.2"] == "P2"


def test_two_levels_only_and_inserts_keep_ids(tmp_path: Path) -> None:
    root = trip(tmp_path)
    p = str(root)
    code, out = cli(tmp_path, "plan", "add", p, "--parent", "P2.1", "--title", "两个机场都查")
    assert code == 1 and "两层" in out["errors"][0] and "plan insert" in out["errors"][0]
    code, out = cli(tmp_path, "plan", "add", p, "--id", "P2.1.1", "--title", "两个机场都查")
    assert code == 1 and "两层" in out["errors"][0]
    assert ok(tmp_path, "plan", "insert", p, "P2.1", "--title", "查高铁")["item_id"] == "P2.1a"
    lines = plan_file(root).read_text(encoding="utf-8").splitlines()
    at = lines.index("- [ ] P2.1a 查高铁")
    assert lines[at - 1].startswith("- [ ] P2.1 ") and lines[at + 1].startswith("- [ ] P2.2 ")
    # a hand-written third level is a structure error
    path = plan_file(root)
    path.write_text(path.read_text(encoding="utf-8").replace("- [ ] P2.2 查酒店", "  - [ ] P2.1.1 子步骤\n- [ ] P2.2 查酒店"),
                    encoding="utf-8")
    assert "PLAN_STEP_TOO_DEEP" in {e["code"] for e in cli(tmp_path, "plan", "validate", p)[1]["errors"]}


def test_adding_needs_a_phase(tmp_path: Path) -> None:
    root = trip(tmp_path)
    code, out = cli(tmp_path, "plan", "add", str(root), "--id", "P9.1", "--title", "无处可放")
    assert code == 1 and "phase add" in out["errors"][0]
    code, out = cli(tmp_path, "plan", "add", str(root), "--parent", "P9", "--title", "x")
    assert code == 1 and "unknown parent id: P9" in out["errors"][0]
    # --id inside an existing phase goes to the end of that phase
    ok(tmp_path, "plan", "add", str(root), "--id", "P1.9", "--title", "问预算")
    ids = [item.id for item in parse_plan(plan_file(root)).items]
    assert ids.index("P1.9") == ids.index("P1.2") + 1


def test_phase_edit_and_goal_rewrite_only_their_text(tmp_path: Path) -> None:
    root = trip(tmp_path)
    p = str(root)
    ok(tmp_path, "plan", "phase", "edit", p, "P3", "--summary", "方案选定后下单，付款前停下给用户确认。")
    ok(tmp_path, "plan", "phase", "edit", p, "P2", "--title", "查机票酒店")
    state = parse_plan(plan_file(root))
    assert state.phases[2].summary == "方案选定后下单，付款前停下给用户确认。"
    assert state.phases[1].title == "查机票酒店" and state.phases[1].summary.startswith("问清需求后")
    assert [item.id for item in state.items] == ["P1.1", "P1.2", "P2.1", "P2.2", "P3.1"]
    ok(tmp_path, "plan", "goal", p, "新目标")
    assert parse_plan(plan_file(root)).coordinate["goal"] == "新目标"
    assert cli(tmp_path, "plan", "phase", "edit", p, "P3", "--summary", "bad <!-- x -->")[0] == 1


def test_phase_cancel_drops_a_route_with_a_reason(tmp_path: Path) -> None:
    root = trip(tmp_path)
    out = ok(tmp_path, "plan", "phase", "cancel", str(root), "P3", "--reason", "改成自驾，不订票")
    assert out["cancelled"] == ["P3.1"]
    text = plan_file(root).read_text(encoding="utf-8")
    assert "### P3 下单 ✕" in text and "reason=阶段放弃：改成自驾，不订票" in text


def test_archive_folds_closed_phases_but_keeps_the_heading(tmp_path: Path) -> None:
    root = trip(tmp_path)
    p = str(root)
    ok(tmp_path, "plan", "cancel", p, "P1.2", "--reason", "不等了")
    ok(tmp_path, "plan", "phase", "edit", p, "P1", "--summary", "需求问清：两人、预算一万。")
    out = ok(tmp_path, "plan", "archive", p, "--keep", "0")
    assert out["archived_phases"] == ["P1"] and out["archived"] == 2
    state = parse_plan(plan_file(root))
    assert state.phases[0].mark == "✅" and state.phases[0].summary == "需求问清：两人、预算一万。"
    assert [item.id for item in state.items] == ["P2.1", "P2.2", "P3.1"]
    shown = ok(tmp_path, "plan", "show", p, "--fast")
    assert shown["phases"][0]["state"] == "done" and shown["phases_done"] == 1
    # folded steps stay readable (the card opens them from here), and the phase is not "bare"
    assert [(s["id"], s["state"]) for s in shown["phases"][0]["archived_steps"]] == [("P1.1", "done"), ("P1.2", "cancelled")]
    assert "PLAN_PHASE_NO_STEPS" not in {w["code"] for w in ok(tmp_path, "plan", "validate", p)["warnings"]}
    archive = (root / "_wiki-methodology" / "_top" / "_logs" / "plan-archive.md").read_text(encoding="utf-8")
    assert "收起阶段 P1 问清需求" in archive and "- [x] P1.1 " in archive
    # the phase number is never reused, not even after its steps left the file
    assert ok(tmp_path, "plan", "phase", "add", p, "--title", "复盘")["phase_id"] == "P4"
    assert ok(tmp_path, "plan", "add", p, "--parent", "P1", "--title", "补一步")["item_id"] == "P1.3"


def test_readability_warnings(tmp_path: Path) -> None:
    root = trip(tmp_path)
    p = str(root)
    ok(tmp_path, "plan", "edit", p, "P2.2", "--title", "查酒店" + "并且把所有候选的价格位置评价退改规则都整理成表格" * 2)
    ok(tmp_path, "plan", "phase", "edit", p, "P2", "--summary", "")
    for n in range(5):
        ok(tmp_path, "plan", "phase", "add", p, "--title", f"阶段{n}")
    codes = {w["code"] for w in ok(tmp_path, "plan", "validate", p)["warnings"]}
    assert {"PLAN_TITLE_LONG", "PLAN_PHASE_NO_SUMMARY", "PLAN_PHASES_MANY"} <= codes
    # a hand edit of the mirror is a warning that the next write repairs
    path = plan_file(root)
    path.write_text(path.read_text(encoding="utf-8").replace("- 下一步：P2.2", "- 下一步：随便"), encoding="utf-8")
    assert "PLAN_NOW_STALE" in {w["code"] for w in ok(tmp_path, "plan", "validate", p)["warnings"]}
    ok(tmp_path, "plan", "note", p, "查到两家", "--kind", "learn")   # a note never rewrites the plan…
    ok(tmp_path, "plan", "add", p, "--parent", "P3", "--title", "订酒店")  # …a write does
    assert "PLAN_NOW_STALE" not in {w["code"] for w in ok(tmp_path, "plan", "validate", p)["warnings"]}


def test_structure_errors(tmp_path: Path) -> None:
    root = trip(tmp_path)
    path = plan_file(root)
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("- [ ] P2.2 查酒店", "- [ ] P3.7 查酒店").replace("### P3 下单", "### 下单"),
                    encoding="utf-8")
    codes = {e["code"] for e in cli(tmp_path, "plan", "validate", str(root))[1]["errors"]}
    assert {"PLAN_STEP_OUTSIDE_PHASE", "PLAN_PHASE_MALFORMED"} <= codes


def test_migrate_replaces_a_legacy_plan_from_a_draft(tmp_path: Path) -> None:
    from test_sixone_plan_cli import make_project
    root = make_project(tmp_path)          # legacy: stamp + Current Coordinate + Active Work
    before = plan_file(root).read_text(encoding="utf-8")
    old_open = [i.id for i in parse_plan(plan_file(root)).items if not i.closed]
    draft = root / "_tmp" / "plan-draft.md"
    draft.parent.mkdir()
    draft.write_text((TEMPLATE / "_wiki-methodology" / "_top" / "_task_plan.md").read_text(encoding="utf-8")
                     .replace("<一两句人话：整件事做完是什么样>", "把演示项目做完"), encoding="utf-8")
    preview = ok(tmp_path, "plan", "migrate", str(root), "_tmp/plan-draft.md")
    assert preview["apply"] is False and preview["format_before"] == "legacy"
    assert [d.split(" ", 1)[0] for d in preview["dropped_open"]] == old_open
    assert plan_file(root).read_text(encoding="utf-8") == before            # preview writes nothing
    code, blocked = cli(tmp_path, "plan", "migrate", str(root), "_tmp/plan-draft.md", "--apply")
    assert code == 1 and blocked["verdict"] == "block"
    out = ok(tmp_path, "plan", "migrate", str(root), "_tmp/plan-draft.md", "--apply", "--accept-dropped")
    assert parse_plan(plan_file(root)).outline and out["phases"] == 1
    link = plan_file(root).parent / "_task_plan.before-migrate.md"
    assert link.is_symlink() and link.read_text(encoding="utf-8") == before
    log = next((root / "_wiki-methodology" / "_top" / "_logs").glob("*-plan.md")).read_text(encoding="utf-8")
    assert "migrate plan → 目录格式：1 个阶段 1 步" in log and "dropped=" in log


def test_migrate_rejects_a_broken_draft(tmp_path: Path) -> None:
    root = trip(tmp_path)
    draft = root / "draft.md"
    draft.write_text(plan_file(root).read_text(encoding="utf-8").replace("- [ ] P2.2 查酒店", "- [ ] P1.2 查酒店"),
                     encoding="utf-8")
    code, out = cli(tmp_path, "plan", "migrate", str(root), "draft.md")
    assert code == 1 and "PLAN_ID_DUPLICATE" in {e["code"] for e in out["errors"]}
    legacy = root / "legacy.md"
    legacy.write_text("# x\n\n## Active Work\n\n- [ ] P1.1 a\n", encoding="utf-8")
    code, out = cli(tmp_path, "plan", "migrate", str(root), "legacy.md")
    assert code == 1 and "不是目录格式" in out["errors"][0]


def test_compact_never_moves_the_table_of_contents(tmp_path: Path) -> None:
    root = trip(tmp_path)
    path = plan_file(root)
    path.write_text(path.read_text(encoding="utf-8").replace(
        "### P3 下单", "### P3 下单 2026-09-26 复盘\n\n" + "流水 " * 900 + "\n\n### P3 下单").replace(
        "### P3 下单 2026-09-26 复盘", "## 2026-09-26 流水"), encoding="utf-8")
    before = parse_plan(path)
    out = ok(tmp_path, "plan", "compact", str(root), "--apply")
    assert [m["title"] for m in out["moved"]] == ["2026-09-26 流水"]
    after = parse_plan(path)
    assert [p.id for p in after.phases] == [p.id for p in before.phases]
    assert [i.id for i in after.items] == [i.id for i in before.items]


def test_turn_hint_is_the_core_only(tmp_path: Path) -> None:
    root = trip(tmp_path)
    ok(tmp_path, "plan", "note", str(root), "山脚酒店少", "--kind", "learn")
    state = tmp_path / "hook-state"
    line = run_event(root, "UserPromptSubmit", "", state).stdout
    assert line.startswith("【TOP 当前】trip：第 2/3 阶段「查行情」｜正在做 P2.1 查往返机票｜下一步 P2.2 查酒店｜卡点 P1.2 等放假通知")
    assert "心得" not in line and "山脚" not in line
    start = run_event(root, "SessionStart", "", state).stdout
    assert "目标：国庆去北京长城" in start and "第 2/3 阶段「查行情」：问清需求后查票" in start


def test_marks_inside_a_phase_title_are_dropped(tmp_path: Path) -> None:
    root = trip(tmp_path)
    path = plan_file(root)
    path.write_text(path.read_text(encoding="utf-8").replace("### P3 下单 ⏳", "### P3 下单 ⏸ 等拍板 ⏸"), encoding="utf-8")
    assert parse_plan(path).phases[2].title == "下单 等拍板"
    ok(tmp_path, "plan", "add", str(root), "--parent", "P3", "--title", "订酒店")
    assert "### P3 下单 等拍板 ⏳\n" in path.read_text(encoding="utf-8")
    assert ok(tmp_path, "plan", "phase", "edit", str(root), "P3", "--title", "下单 ✅")["verdict"] == "ok"
    assert parse_plan(path).phases[2].title == "下单"
    assert cli(tmp_path, "plan", "phase", "add", str(root), "--title", "✅")[0] == 1


def test_misused_metadata_and_long_block_reasons_warn(tmp_path: Path) -> None:
    root = trip(tmp_path)
    path = plan_file(root)
    path.write_text(path.read_text(encoding="utf-8").replace(
        "- [ ] P2.2 查酒店", "- [ ] P2.2 查酒店 <!-- no_artifact_reason=还没开始，先等机票 -->"), encoding="utf-8")
    ok(tmp_path, "plan", "reopen", str(root), "P1.2")
    ok(tmp_path, "plan", "block", str(root), "P1.2", "--reason", "等放假通知 · 详见 _wiki/一个很长很长的路径/说明文档.md")
    codes = {w["code"] for w in ok(tmp_path, "plan", "validate", str(root))["warnings"]}
    assert {"PLAN_META_MISUSED", "PLAN_REASON_LONG"} <= codes


# ---------- review follow-ups (2026-09-26) ----------

def legacy_project(tmp_path: Path) -> Path:
    root = tmp_path / "legacy"
    top = root / "_wiki-methodology" / "_top"
    top.mkdir(parents=True)
    (top / "_task_plan.md").write_text(
        "# legacy\n\n🧭 当前 [P3] task=[none] 旧计划\n\n## Current Coordinate\n\n- Goal: g\n"
        "- Current task: none\n- Next task: P3.2\n- Latest learning: none\n- Blocker: none\n\n"
        "## Active Work\n\n- [x] P3.1 训练大模型 · ev=x.json\n- [ ] P3.2 写论文\n", encoding="utf-8")
    return root


def test_migrate_refuses_to_reuse_an_old_id_for_other_work(tmp_path: Path) -> None:
    root = legacy_project(tmp_path)
    draft = root / "draft.md"
    draft.write_text("# x\n\n## 目标\n\n目标\n\n## 各阶段\n\n### P3 新阶段\n\n- [ ] P3.1 买机票\n- [ ] P3.2 写论文\n",
                     encoding="utf-8")
    code, out = cli(tmp_path, "plan", "migrate", str(root), "draft.md")
    assert code == 1 and {e["code"] for e in out["errors"]} == {"PLAN_MIGRATE_ID_REUSED"}
    assert "训练大模型" in out["errors"][0]["message"]
    # the same step carried over under its old ID is fine (P3.2 stays open: nothing dropped)
    draft.write_text(draft.read_text(encoding="utf-8").replace("- [ ] P3.1 买机票", "- [x] P3.1 训练大模型 <!-- ev=x.json -->"),
                     encoding="utf-8")
    preview = ok(tmp_path, "plan", "migrate", str(root), "draft.md")
    assert preview["dropped_open"] == []


def test_migrate_wants_steps_under_done_phases(tmp_path: Path) -> None:
    root = legacy_project(tmp_path)
    draft = root / "draft.md"
    draft.write_text("# x\n\n## 目标\n\n目标\n\n## 各阶段\n\n### P1 早期工作 ✅\n\n小结。\n\n"
                     "### P4 接着做\n\n- [ ] P4.1 写论文\n", encoding="utf-8")
    code, out = cli(tmp_path, "plan", "migrate", str(root), "draft.md")
    assert code == 1 and [e["code"] for e in out["errors"]] == ["PLAN_PHASE_NO_STEPS"]


def test_rewriting_twice_keeps_the_link_on_the_legacy_original(tmp_path: Path) -> None:
    from test_sixone_plan_cli import make_project
    root = make_project(tmp_path)
    legacy = plan_file(root).read_text(encoding="utf-8")
    draft = root / "draft.md"
    draft.write_text("# x\n\n## 目标\n\n目标\n\n## 各阶段\n\n### P5 新阶段\n\n- [ ] P5.1 第一步\n", encoding="utf-8")
    ok(tmp_path, "plan", "migrate", str(root), "draft.md", "--apply", "--accept-dropped")
    draft.write_text(draft.read_text(encoding="utf-8").replace("第一步", "第一步（改说法）"), encoding="utf-8")
    second = ok(tmp_path, "plan", "migrate", str(root), "draft.md", "--apply")
    link = plan_file(root).parent / "_task_plan.before-migrate.md"
    assert link.read_text(encoding="utf-8") == legacy
    snapshots = sorted((plan_file(root).parent / "_logs" / "plan-history").glob("*-before-migrate.md"))
    assert len(snapshots) == 2 and Path(second["original_snapshot"]).read_text(encoding="utf-8") != legacy


def test_look_alike_marks_on_step_less_phases_are_kept(tmp_path: Path) -> None:
    root = trip(tmp_path)
    path = plan_file(root)
    path.write_text(path.read_text(encoding="utf-8").replace(
        "## 关键问题", "### P7 早就做完的阶段 ✅️\n\n### P8 放弃的路线 ❌\n\n### P9 暂停 ⏸️ 中\n\n## 关键问题"),
        encoding="utf-8")
    state = parse_plan(path)
    assert [(p.id, p.title, p.mark) for p in state.phases[3:]] == [
        ("P7", "早就做完的阶段", "✅"), ("P8", "放弃的路线", "✕"), ("P9", "暂停 中", "")]
    ok(tmp_path, "plan", "add", str(root), "--parent", "P3", "--title", "订酒店")
    text = path.read_text(encoding="utf-8")
    assert "### P7 早就做完的阶段 ✅\n" in text and "### P8 放弃的路线 ✕\n" in text and "️" not in text


def test_giving_up_a_half_done_phase_shows_it_as_given_up(tmp_path: Path) -> None:
    root = trip(tmp_path)
    ok(tmp_path, "plan", "complete", str(root), "P2.1", "--evidence", "findings.md#机票")
    ok(tmp_path, "plan", "phase", "cancel", str(root), "P2", "--reason", "改成自驾")
    shown = ok(tmp_path, "plan", "show", str(root), "--fast")
    assert {p["id"]: p["state"] for p in shown["phases"]}["P2"] == "cancelled"
    assert "### P2 查行情 ✕" in plan_file(root).read_text(encoding="utf-8")


def test_goal_and_summary_cannot_open_a_heading_or_a_step(tmp_path: Path) -> None:
    root = trip(tmp_path)
    before = plan_file(root).read_text(encoding="utf-8")
    for args in (("plan", "phase", "edit", str(root), "P1", "--summary", "## 小结"),
                 ("plan", "phase", "edit", str(root), "P1", "--summary", "- [ ] P9.1 偷渡的步骤"),
                 ("plan", "goal", str(root), "# 新目标")):
        code, out = cli(tmp_path, *args)
        assert code == 1 and "不能以 # 或勾选框开头" in out["errors"][0], out
    assert plan_file(root).read_text(encoding="utf-8") == before


def test_technical_titles_bare_phases_and_the_details_article(tmp_path: Path) -> None:
    root = trip(tmp_path)
    p = str(root)
    ok(tmp_path, "plan", "add", p, "--parent", "P3", "--title", "跑 _outputs/x.json 的 0.4563% 复核")
    ok(tmp_path, "plan", "add", p, "--parent", "P3", "--title", "Piggyback PackNet ZipIt 三种机制")
    ok(tmp_path, "plan", "add", p, "--parent", "P3", "--title", "按 GAIA 框架整理物性/岩相两个场景")   # a name and "/" are fine
    ok(tmp_path, "plan", "phase", "add", p, "--title", "以后再说")
    warnings = {w["code"]: w["message"] for w in ok(tmp_path, "plan", "validate", p)["warnings"]}
    assert "P3.2" in warnings["PLAN_TITLE_TECHNICAL"] and "P3.3" in warnings["PLAN_TITLE_TECHNICAL"]
    assert "P3.4" not in warnings["PLAN_TITLE_TECHNICAL"]
    assert "P4" in warnings["PLAN_PHASE_NO_STEPS"]
    assert ok(tmp_path, "plan", "show", p, "--fast")["details"] is None
    (plan_file(root).parent / "_plan_details.md").write_text("# 计划细节\n\n## P2 查行情\n\n- 报价表见 findings\n",
                                                            encoding="utf-8")
    assert ok(tmp_path, "plan", "show", p, "--fast")["details"] == "_plan_details.md"
