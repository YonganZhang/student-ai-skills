"""2026-10-16 question-and-answer plans (`plan-format: qa`): CLI, model, hooks, git hook, migration.

A project is a list of questions; people read questions and answers, the AI keeps attempts in a
work file per question. See references/qa-plan.md."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL / "scripts"
PLAN = SCRIPTS / "plan"
HINT = SCRIPTS / "top-session-hint.py"
TEMPLATE = SKILL / "tests" / "fixtures" / "outline-minimal"  # old outline project; templates/minimal is Q&A now
sys.path.insert(0, str(SCRIPTS))
import top_plan  # noqa: E402
import top_qa  # noqa: E402
from top_common import PlanError, parse_plan  # noqa: E402


def env_for(tmp_path: Path) -> dict[str, str]:
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(tmp_path), TOP_PROJECTS_DIR=str(tmp_path / "projects"),
               TMUX_TMPDIR=str(tmp_path / "no-tmux"), TOP_LOCK_DIR=str(tmp_path / "locks"))
    env.pop("TMUX", None)
    (tmp_path / "no-tmux").mkdir(exist_ok=True)
    return env


def run(tmp_path: Path, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(PLAN), *args], cwd=cwd, env=env_for(tmp_path), capture_output=True,
                          text=True, timeout=30, stdin=subprocess.DEVNULL)


def ok(tmp_path: Path, cwd: Path, *args: str) -> str:
    result = run(tmp_path, cwd, *args)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def fail(tmp_path: Path, cwd: Path, *args: str) -> str:
    result = run(tmp_path, cwd, *args)
    assert result.returncode != 0, result.stdout
    return result.stdout


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout


def qa_project(tmp_path: Path, name: str = "paper") -> Path:
    root = tmp_path / "projects" / name
    root.mkdir(parents=True)
    git(root, "init", "-q")
    ok(tmp_path, root, "init", "搞清楚加入波形数据能不能让分类更准，写成论文")
    return root


def plan_files(root: Path) -> tuple[Path, Path]:
    top = root / "_wiki-methodology" / "_top"
    return top / "_task_plan.md", top / "_questions"


def leak_story(tmp_path: Path) -> Path:
    """Two questions; the second one's answer gets withdrawn after a leak is found, then re-answered."""
    root = qa_project(tmp_path)
    ok(tmp_path, root, "ask", "数据切分对吗？", "--done-when", "训练井和盲测井完全分开")
    ok(tmp_path, root, "add", "按井切分数据")
    ok(tmp_path, root, "start", "Q1.1")
    ok(tmp_path, root, "done", "Q1.1", "切好了", "--ev", "data/split.json")
    ok(tmp_path, root, "answer", "Q1", "对：按井切分", "--ev", "Q1.1")
    ok(tmp_path, root, "ask", "新结构有用吗？", "--done-when", "多种子盲测稳定高于基线")
    ok(tmp_path, root, "add", "搭训练管线", "--to", "Q2")
    ok(tmp_path, root, "add", "多种子跑新结构", "--to", "Q2")
    for step, result, ev in (("Q2.1", "跑通", "src/train.py"), ("Q2.2", "比原来高 2 个百分点", "runs/v1")):
        ok(tmp_path, root, "start", step)
        ok(tmp_path, root, "done", step, result, "--ev", ev)
    ok(tmp_path, root, "answer", "Q2", "有用：比原来高 2 个百分点", "--ev", "Q2.2", "--because", "Q1")
    return root


# ---------- writing and reading ----------

def test_missing_version_is_inspected_before_stamping_and_never_downgrades(tmp_path: Path) -> None:
    root = qa_project(tmp_path)
    plan, _ = plan_files(root)
    original = plan.read_text()
    plan.write_text(original.replace(" · top-version=1", ""))
    assert "TOP_VERSION_MISSING" in run(tmp_path, root, "check").stdout
    assert "计划未标版本" in hook(root, "SessionStart", "v", tmp_path / "state").stdout
    assert "版本：未标" in ok(tmp_path, root, "now")
    assert "内容检查通过" in ok(tmp_path, root, "upgrade")
    assert "top-version" not in plan.read_text()                 # preview must not stamp
    plan.write_text(original.replace("top-version=1", "top-version=99"))
    assert "TOP_VERSION_NEW" in run(tmp_path, root, "check").stdout
    assert "高于" in fail(tmp_path, root, "upgrade", "--apply")
    assert "top-version=99" in plan.read_text()                  # never downgraded
    plan.write_text(original.replace(" · top-version=1", ""))
    assert "已升级计划版本" in ok(tmp_path, root, "upgrade", "--apply")
    assert "top-version=1" in plan.read_text()
    assert "TOP_VERSION" not in run(tmp_path, root, "check").stdout


def test_missing_version_with_bad_content_is_not_stamped(tmp_path: Path) -> None:
    root = qa_project(tmp_path)
    ok(tmp_path, root, "ask", "第一问？", "--done-when", "x")
    plan, qdir = plan_files(root)
    plan.write_text(plan.read_text().replace(" · top-version=1", ""))
    work = qdir / "Q1.md"
    work.write_text(work.read_text().replace("state=todo", "state=bogus"))
    assert "内容有错误" in fail(tmp_path, root, "upgrade", "--apply")
    assert "top-version" not in plan.read_text()


def test_sixone_cli_exposes_plan_upgrade_json(tmp_path: Path) -> None:
    root = qa_project(tmp_path)
    plan, _ = plan_files(root)
    plan.write_text(plan.read_text().replace(" · top-version=1", ""))
    result = subprocess.run([sys.executable, str(SCRIPTS / "sixone-cli.py"), "plan", "upgrade", str(root), "--apply"],
                            capture_output=True, text=True, env=env_for(tmp_path), timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["tool"] == "plan-upgrade" and data["to_version"] == 1
    assert "top-version=1" in plan.read_text()


def test_template_version_tracks_the_code_version() -> None:
    import qa_format
    text = (SKILL / "templates" / "minimal" / "_wiki-methodology" / "_top" / "_task_plan.md").read_text()
    assert f"top-version={qa_format.PLAN_VERSION}" in text


def test_init_ask_add_done_answer_reads_as_a_story(tmp_path: Path) -> None:
    root = leak_story(tmp_path)
    core = ok(tmp_path, root)
    assert "问答（2 个）" in core and "✔ Q1 数据切分对吗？ — 对：按井切分" in core
    assert "✔ Q2 新结构有用吗？ — 有用：比原来高 2 个百分点" in core
    plan, qdir = plan_files(root)
    text = plan.read_text()
    assert "<!-- plan-format: qa · top-version=1" in text and "### 新结构有用吗？ ✔ <!-- id=Q2 -->" in text
    assert "答：有用：比原来高 2 个百分点" in text and "Q2.2" not in text     # no IDs/steps in the mirror
    work = (qdir / "Q2.md").read_text()
    assert "- [x] Q2.2 多种子跑新结构 → 比原来高 2 个百分点 <!-- ev=runs/v1 -->" in work
    assert "- r1 有用：比原来高 2 个百分点" in work and "status=current" in work
    assert "没问题" in ok(tmp_path, root, "check")


def test_plan_now_omits_question_catalog(tmp_path: Path) -> None:
    root = leak_story(tmp_path)
    out = ok(tmp_path, root, "now")
    assert "目标：" in out and "正在弄清：" in out and "下一步：" in out
    assert "问答（" not in out
    assert len(out.splitlines()) < 10


def test_plan_now_json_is_machine_readable(tmp_path: Path) -> None:
    root = leak_story(tmp_path)
    data = json.loads(ok(tmp_path, root, "now", "--json"))
    assert data["format"] == "qa" and data["goal"]


def test_withdrawal_is_immediate_and_rerun_supersedes_explicitly(tmp_path: Path) -> None:
    root = leak_story(tmp_path)
    out = ok(tmp_path, root, "reopen", "Q1", "盲测井混进了训练井", "--because", "Q2.2", "--invalid", "Q1.1")
    assert "已撤回 Q1 的答案 r1" in out and "Q2 新结构有用吗？" in out          # Q2 cites Q1 → affected
    ok(tmp_path, root, "reopen", "Q2", "依赖的数据切分有泄漏", "--because", "Q1", "--invalid", "Q2.1..Q2.2")
    plan, qdir = plan_files(root)
    text = plan.read_text()
    assert "### 数据切分对吗？ ↺" in text and "旧答已撤回：盲测井混进了训练井；正在复核" in text
    data = top_qa.show(root)
    q2 = next(q for q in data["questions"] if q["id"] == "Q2")
    assert q2["mark"] == "↺" and q2["answer"] is None and q2["withdrawn"]["reason"] == "依赖的数据切分有泄漏"
    # rerun: a new attempt naming its sources; the old result stays as it was
    ok(tmp_path, root, "add", "按井号重新切分", "--to", "Q1", "--from", "Q1.1", "--because", "Q2.2")
    ok(tmp_path, root, "start", "Q1.2")
    ok(tmp_path, root, "done", "Q1.2", "无泄漏的数据集 v2", "--ev", "data/split_v2.json", "--supersedes", "Q1.1")
    ok(tmp_path, root, "answer", "Q1", "原来有泄漏，已改正", "--ev", "Q1.2")
    work = (qdir / "Q1.md").read_text()
    assert "- [x] Q1.1 按井切分数据 → 切好了" in work and "invalid=盲测井混进了训练井" in work
    assert "from=Q1.1" in work and "supersedes=Q1.1" in work
    q1 = top_qa.question_view(root, "Q1")
    assert [a["status"] for a in q1["question"]["answers"]] == ["withdrawn", "current"]
    old = next(a for a in q1["attempts"] if a["id"] == "Q1.1")
    assert old["superseded_by"] == "Q1.2" and not old["usable"]
    assert "（改过 1 次）" in plan.read_text()
    view = ok(tmp_path, root, "Q1")
    assert "旧答案 r1" in view and "撤回" in view and "已被 Q1.2 替代" in view


def test_sealed_results_are_never_rewritten(tmp_path: Path) -> None:
    root = leak_story(tmp_path)
    assert "做完的结果不改写" in fail(tmp_path, root, "reopen", "Q2.2")
    assert "结果不改写" in fail(tmp_path, root, "done", "Q2.2", "改个结果", "--ev", "x")
    assert "证据" in fail(tmp_path, root, "answer", "Q2", "没证据的答案")
    ok(tmp_path, root, "add", "再跑一次", "--to", "Q2")
    assert "证据" in fail(tmp_path, root, "done", "Q2.3", "跑完了")
    assert "结果" in fail(tmp_path, root, "done", "Q2.3", "--ev", "x")


def test_focus_and_next_are_explicit(tmp_path: Path) -> None:
    root = qa_project(tmp_path)
    ok(tmp_path, root, "ask", "论文写完了吗？", "--done-when", "数字与最新结果一致")
    ok(tmp_path, root, "ask", "投哪个期刊？", "--done-when", "作者认可的期刊")
    assert top_qa.show(root)["focus"]["id"] == "Q1"                       # first question becomes the focus
    assert "下一步：待选定" in ok(tmp_path, root)                          # nothing to pick from: say so
    ok(tmp_path, root, "add", "写英文初稿")
    ok(tmp_path, root, "add", "核对每个数字")
    nxt = top_qa.show(root)["next"]
    assert nxt["id"] == "Q1.1" and nxt["source"] == "candidate"          # only from the focus question
    ok(tmp_path, root, "start", "Q1.1")
    ok(tmp_path, root, "focus", "--next", "等初稿出来先给作者看", "--after")
    nxt = top_qa.show(root)["next"]
    assert nxt == {"id": None, "title": "等初稿出来先给作者看", "when": "after", "source": "explicit"}
    assert "下一步：等初稿出来先给作者看（做完当前这步后）" in plan_files(root)[0].read_text()
    ok(tmp_path, root, "focus", "--next", "Q1.2")
    ok(tmp_path, root, "done", "Q1.1", "初稿完成", "--ev", "paper/v1.pdf")
    ok(tmp_path, root, "start", "Q1.2")
    assert top_qa.show(root)["next"] is None or top_qa.show(root)["next"]["id"] != "Q1.2"   # cleared on start


def test_needs_you_shows_only_when_there_is_something(tmp_path: Path) -> None:
    root = qa_project(tmp_path)
    ok(tmp_path, root, "ask", "投哪个期刊？", "--done-when", "作者认可的期刊")
    plan = plan_files(root)[0]
    assert "需要你" not in plan.read_text()
    ok(tmp_path, root, "add", "列出候选期刊")
    ok(tmp_path, root, "start", "Q1.1")
    ok(tmp_path, root, "block", "Q1.1", "等你从三个候选里选一个", "--you")
    assert "- 需要你：等你从三个候选里选一个" in plan.read_text()
    assert top_qa.show(root)["needs_you"][0]["id"] == "Q1.1"
    assert "需要你：Q1.1 等你从三个候选里选一个" in ok(tmp_path, root)
    ok(tmp_path, root, "wait", "Q1", "等作者回邮件", "--you")
    assert "⏸" in ok(tmp_path, root)


def test_stale_revision_conflicts_and_changes_nothing(tmp_path: Path) -> None:
    root = leak_story(tmp_path)
    plan, qdir = plan_files(root)
    before = (plan.read_text(), (qdir / "Q2.md").read_text())
    assert "重读后再试" in fail(tmp_path, root, "add", "x", "--to", "Q2", "--expect", "0" * 64)
    assert (plan.read_text(), (qdir / "Q2.md").read_text()) == before
    revision = top_qa.show(root)["revision"]
    ok(tmp_path, root, "add", "x", "--to", "Q2", "--expect", revision)


def test_notes_survive_writes_and_unknown_sections_block_them(tmp_path: Path) -> None:
    root = leak_story(tmp_path)
    _, qdir = plan_files(root)
    work = qdir / "Q2.md"
    work.write_text(work.read_text() + "lr=3e-4，batch 64；第 3 个种子不稳定\n## 小结\n自己的小标题也算笔记\n")
    ok(tmp_path, root, "add", "换学习率再跑", "--to", "Q2")
    text = work.read_text()
    assert "lr=3e-4，batch 64" in text and "## 小结" in text and "Q2.3 换学习率再跑" in text
    broken = text.replace("## 为什么问", "## 背景")
    work.write_text(broken)
    assert "写入会丢内容" in fail(tmp_path, root, "add", "y", "--to", "Q2")
    assert work.read_text() == broken
    assert "QA_SECTION" in run(tmp_path, root, "check").stdout


def test_hand_edited_mirror_is_reported_and_rebuilt(tmp_path: Path) -> None:
    root = leak_story(tmp_path)
    plan, _ = plan_files(root)
    plan.write_text(plan.read_text().replace("答：有用：比原来高 2 个百分点", "答：手改的"))
    assert "QA_MIRROR_STALE" in run(tmp_path, root, "check").stdout
    assert top_qa.show(root)["questions"][1]["summary"].startswith("有用")   # readers use the work files
    ok(tmp_path, root, "note", "随手记一句")                                 # a note writes only the log
    ok(tmp_path, root, "flag", "Q2", "数据集要复核")
    assert "答：有用：比原来高 2 个百分点 · ⚠ 要重新确认：数据集要复核" in plan.read_text()


def test_outline_commands_and_raw_writes_are_refused_on_qa(tmp_path: Path) -> None:
    root = leak_story(tmp_path)
    assert "没有阶段" in fail(tmp_path, root, "phase", "新阶段")
    assert "回头重做" in fail(tmp_path, root, "insert", "Q2.1", "x")
    try:
        top_plan.set_goal(str(root), "绕过问答命令")
    except PlanError as exc:
        assert "问答" in str(exc)
    else:
        raise AssertionError("legacy writer must refuse a qa plan")


def test_attempts_are_tasks_for_read_only_consumers(tmp_path: Path) -> None:
    root = leak_story(tmp_path)
    ok(tmp_path, root, "add", "写论文", "--to", "Q2")
    ok(tmp_path, root, "start", "Q2.3")
    state = parse_plan(plan_files(root)[0])
    assert state.format == "qa" and [i.id for i in state.items if i.state == "in_progress"] == ["Q2.3"]
    assert top_plan.show(str(root))["current"]["id"] == "Q2.3"
    # prepare-commit-msg adds `Task: Q2.3` (the single step in progress)
    (root / "draft.md").write_text("x\n")
    git(root, "add", "draft.md")
    msg = root / ".git" / "COMMIT_EDITMSG"
    msg.write_text("draft\n")
    env = dict(os.environ, GIT_DIR=str(root / ".git"), GIT_WORK_TREE=str(root))
    subprocess.run([sys.executable, str(SKILL / "git-hooks" / "top_githook.py"), "prepare-commit-msg", str(msg)],
                   cwd=root, env=env, check=True, capture_output=True)
    assert "Task: Q2.3" in msg.read_text()


def test_ls_old_id_lookup_and_json(tmp_path: Path) -> None:
    root = leak_story(tmp_path)
    data = json.loads(ok(tmp_path, root, "--json"))
    assert data["format"] == "qa" and len(data["revision"]) == 64
    assert {"id", "text", "state", "mark", "answer", "withdrawn", "summary", "review", "wait", "attempts"} <= set(data["questions"][0])
    q = json.loads(ok(tmp_path, root, "Q2", "--json"))
    assert q["attempts_total"] == 2 and q["question"]["done_when"] == "多种子盲测稳定高于基线"
    assert "问答 2/2 已答" in ok(tmp_path, root, "ls", "--all")
    assert "没有 P3.2" in fail(tmp_path, root, "P3.2")


# ---------- migration ----------

def outline_trip(tmp_path: Path) -> Path:
    root = tmp_path / "projects" / "trip"
    shutil.copytree(TEMPLATE, root)
    for args in (("goal", "国庆去北京长城：机票酒店都订好"), ("add", "确认放假日期"),
                 ("phase", "查行情", "--summary", "问清需求后查票。"), ("add", "查往返机票", "--to", "P2"),
                 ("add", "查酒店", "--to", "P2"), ("start", "P1.1"), ("done", "P1.1", "--ev", "需求.md")):
        ok(tmp_path, root, *args)
    return root


DRAFT = """# trip — 计划
<!-- plan-format: qa · focus=Q2 -->

## 目标

国庆去北京长城：机票酒店都订好

# Q1 哪天出发？
<!-- id=Q1 · state=closed · answer=r1 -->

## 怎样算答清

日期确定

## 答案

- r1 10 月 1 日 <!-- date=2026-09-26 · ev=Q1.1 · status=current -->

## 尝试

- [x] Q1.1 确认放假日期 → 1 日出发 <!-- ev=需求.md -->

## 旧编号

- P1.* → Q1
- P1.1 → Q1.1

## 笔记

放假通知在学校网站。

# Q2 票和酒店订好了吗？
<!-- id=Q2 · state=active -->

## 怎样算答清

机票和酒店都有订单号

## 尝试

- [ ] Q2.1 查往返机票

## 旧编号

- P2 → Q2
- P2.1 → Q2.1
{extra}
"""


def test_rewrite_to_qa_requires_every_old_id_and_keeps_a_snapshot(tmp_path: Path) -> None:
    root = outline_trip(tmp_path)
    draft = tmp_path / "draft.md"
    draft.write_text(DRAFT.format(extra=""))
    out = fail(tmp_path, root, "rewrite", str(draft), "--to", "qa")
    assert "QA_ALIAS_MISSING" in out and "P2.2" in out
    draft.write_text(DRAFT.format(extra="- P2.2 → 历史\n"))
    out = run(tmp_path, root, "rewrite", str(draft), "--to", "qa").stdout
    assert "预览通过" in out and "P2.2" in out                       # open task without an open target
    assert "--accept-dropped" in fail(tmp_path, root, "rewrite", str(draft), "--to", "qa", "--apply")
    assert "## 各阶段" in plan_files(root)[0].read_text()             # refused: nothing switched
    out = ok(tmp_path, root, "rewrite", str(draft), "--to", "qa", "--apply", "--accept-dropped")
    assert "已切换成问答格式" in out
    plan, qdir = plan_files(root)
    assert "<!-- plan-format: qa · top-version=1 · focus=Q2 -->" in plan.read_text() and (qdir / "Q1.md").is_file()
    snapshots = list((root / "_wiki-methodology" / "_top" / "_logs" / "plan-history").glob("*-before-qa"))
    assert len(snapshots) == 1 and (snapshots[0] / "_task_plan.md").read_text().count("## 各阶段") == 1
    assert "P2.1 → Q2.1" in ok(tmp_path, root, "P2.1")
    # a window still holding old IDs is told where they went, not just refused
    assert "旧编号，现在是 Q2.1" in fail(tmp_path, root, "done", "P2.1", "订好了", "--ev", "x")
    assert "旧编号，现在是 Q2.1" in fail(tmp_path, root, "note", "x", "--on", "P2.1")
    assert "旧编号，现在是 Q1" in fail(tmp_path, root, "add", "再查一次", "--to", "P1")
    assert "旧编号，已归入历史" in fail(tmp_path, root, "start", "P2.2")
    assert "放假通知在学校网站" in (qdir / "Q1.md").read_text()
    assert "有错误" not in ok(tmp_path, root, "check")
    assert "已经是问答格式" in fail(tmp_path, root, "rewrite", str(draft), "--to", "qa", "--apply")


# ---------- hooks ----------

def hook(cwd: Path, event: str, session: str, state: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, TOP_HOOK_STATE=str(state))
    data = json.dumps({"cwd": str(cwd), "hook_event_name": event, "session_id": session})
    return subprocess.run([sys.executable, str(HINT)], input=data, text=True, env=env, capture_output=True,
                          timeout=30, cwd=str(cwd))


def committed(root: Path) -> Path:
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    return root


def test_hooks_speak_questions_and_only_remind_with_a_step_in_progress(tmp_path: Path) -> None:
    root = committed(leak_story(tmp_path))
    state = tmp_path / "state"
    start = hook(root, "SessionStart", "a", state).stdout
    assert "问答 2/2 已答清" in start and "没记进计划" not in start
    (root / "work.py").write_text("x = 1\n")
    assert hook(root, "Stop", "a", state).stdout == ""                      # nothing in progress: silent
    ok(tmp_path, root, "add", "写论文", "--to", "Q2")
    ok(tmp_path, root, "start", "Q2.3")
    hook(root, "SessionStart", "b", state)
    (root / "work2.py").write_text("y = 1\n")
    message = json.loads(hook(root, "Stop", "b", state).stdout)["systemMessage"]
    assert "Q2.3" in message and "跟它无关就不用管" in message
    line = hook(root, "UserPromptSubmit", "c", state).stdout.strip().splitlines()[-1]
    assert line.startswith("【TOP 当前】paper：正在弄清 Q2「新结构有用吗？」") and len(line) <= 200
    assert "当前判断" in line and "正在做 Q2.3" in line
    card = hook(root, "SessionStart", "c", state)
    data = json.dumps({"cwd": str(root), "hook_event_name": "SessionStart", "session_id": "c", "source": "compact"})
    card = subprocess.run([sys.executable, str(HINT)], input=data, text=True, capture_output=True, timeout=30,
                          cwd=str(root), env=dict(os.environ, TOP_HOOK_STATE=str(state))).stdout
    assert card.startswith("【TOP 恢复卡】paper") and "怎样算答清：多种子盲测稳定高于基线" in card
    assert "`plan Q2`" in card and len(card) <= 800


def test_template_placeholders_are_not_content_and_cards_get_a_cheap_summary(tmp_path: Path) -> None:
    root = qa_project(tmp_path)
    ok(tmp_path, root, "ask", "没写答清标准的问题？")
    _, qdir = plan_files(root)
    assert "（待补" in (qdir / "Q1.md").read_text()                     # the file shows what to fill in
    view = top_qa.question_view(root, "Q1")["question"]
    assert view["why"] == "" and view["done_when"] == ""                 # …but readers get nothing
    ok(tmp_path, root, "add", "第一步")
    ok(tmp_path, root, "start", "Q1.1")
    ok(tmp_path, root, "block", "Q1.1", "等你给数据", "--you")
    import qa_format
    summary = qa_format.load_summary(plan_files(root)[0])
    assert summary["focus"] == {"id": "Q1", "text": "没写答清标准的问题？"}
    assert summary["needs_you"] == 1 and summary["questions"] == 1 and summary["answered"] == 0
    assert summary["revision"] == top_qa.show(root)["revision"]


# ---------- review findings (2026-10-16) ----------

def test_sections_after_notes_and_unknown_content_block_writes(tmp_path: Path) -> None:
    root = leak_story(tmp_path)
    _, qdir = plan_files(root)
    work = qdir / "Q2.md"
    original = work.read_text()
    head, notes = original.split("## 笔记", 1)
    moved = head.replace("## 尝试", "## 笔记\n\n挪错位置的笔记\n\n## 尝试", 1)   # notes no longer last
    work.write_text(moved)
    assert "必须是最后一节" in run(tmp_path, root, "check").stdout
    assert "写入会丢内容" in fail(tmp_path, root, "add", "复核", "--to", "Q2")
    work.write_text(original.replace("<!-- ev=runs/v1 -->", "<!-- ev=runs/v1 · prio=high -->"))
    assert "QA_UNKNOWN" in run(tmp_path, root, "check").stdout
    work.write_text(original.replace("\n## 为什么问", "\n标题下的一段话\n\n## 为什么问", 1))
    assert "QA_UNKNOWN" in run(tmp_path, root, "check").stdout
    work.write_text(original.replace("（待补：这个问题和目标的关系）", "（待补：这个问题和目标的关系）\n审稿人二号要求补消融"))
    ok(tmp_path, root, "add", "补消融", "--to", "Q2")
    assert "审稿人二号要求补消融" in work.read_text()                  # text under the placeholder survives


def test_closing_and_focus_rules(tmp_path: Path) -> None:
    root = qa_project(tmp_path)
    ok(tmp_path, root, "ask", "第一问？", "--done-when", "x")
    ok(tmp_path, root, "ask", "第二问？", "--done-when", "y")
    ok(tmp_path, root, "add", "第一步")
    ok(tmp_path, root, "start", "Q1.1")
    assert "进行中" in fail(tmp_path, root, "answer", "Q1", "对", "--ev", "Q1.1")
    ok(tmp_path, root, "focus", "--next", "给作者看")
    ok(tmp_path, root, "done", "Q1.1", "完成", "--ev", "a")
    ok(tmp_path, root, "answer", "Q1", "对", "--ev", "Q1.1")
    data = top_qa.show(root)
    assert data["focus"] is None and data["next"] is None                 # the text next step left with its question
    assert "不知道加到哪个问题" in fail(tmp_path, root, "add", "没有焦点")      # never falls back to a closed one
    ok(tmp_path, root, "add", "再补一个消融", "--to", "Q1")                    # explicit: fine, queued
    ok(tmp_path, root, "start", "Q1.2")
    q1 = top_qa.show(root)["questions"][0]
    assert q1["state"] == "active" and q1["answer"]["text"] == "对"          # more work; the answer stays
    ok(tmp_path, root, "wait", "Q2", "等你定期刊", "--you")
    ok(tmp_path, root, "answer", "Q2", "倾向 A 刊", "--ev", "note", "--keep-open")
    assert top_qa.show(root)["needs_you"][0]["id"] == "Q2"               # still waiting on you
    assert "不在问答目录" not in fail(tmp_path, root, "move", "Q2", "--after", "Q9")


def test_alias_targets_must_exist_and_legacy_writers_refuse_first(tmp_path: Path) -> None:
    root = leak_story(tmp_path)
    _, qdir = plan_files(root)
    work = qdir / "Q1.md"
    work.write_text(work.read_text().replace("## 笔记", "## 旧编号\n\n- P2.2 → Q1.9\n\n## 笔记"))
    assert "指向不存在的 Q1.9" in run(tmp_path, root, "check").stdout
    work.write_text(work.read_text().replace("- P2.2 → Q1.9", "- P2.2 → 历史"))
    assert "有错误" not in ok(tmp_path, root, "check")
    archive = root / "_wiki-methodology" / "_top" / "_logs" / "plan-archive.md"
    out = subprocess.run([sys.executable, str(SCRIPTS / "sixone-cli.py"), "plan", "archive", str(root)],
                         capture_output=True, text=True, env=env_for(tmp_path))
    assert "问答格式" in out.stdout + out.stderr and not archive.exists()
    assert "问答格式" in fail(tmp_path, root, "phase", "x")
    assert "带空格的间隔号" in fail(tmp_path, root, "focus", "--next", "跑完再看 ·")
    assert json.loads(ok(tmp_path, root, "P1.1", "--json"))["hits"] == []


def test_new_project_template_is_an_empty_qa_plan_that_stays_quiet(tmp_path: Path) -> None:
    root = tmp_path / "projects" / "fresh"
    shutil.copytree(SKILL / "templates" / "minimal", root)
    git(root, "init", "-q")
    assert "plan-format: qa" in plan_files(root)[0].read_text(encoding="utf-8")
    assert "没问题" in ok(tmp_path, root, "check")
    hint = SKILL / "scripts" / "top-session-hint.py"
    turn = subprocess.run([sys.executable, str(hint)], input=json.dumps(
        {"hook_event_name": "UserPromptSubmit", "cwd": str(root), "session_id": "t", "prompt": "hi"}),
        env=env_for(tmp_path), capture_output=True, text=True, timeout=30)
    assert turn.returncode == 0 and turn.stdout.strip() == ""
    ok(tmp_path, root, "goal", "弄清一件事")
    assert "弄清一件事" in plan_files(root)[0].read_text(encoding="utf-8")


def session_hint(tmp_path: Path, root: Path) -> str:
    hint = SKILL / "scripts" / "top-session-hint.py"
    result = subprocess.run([sys.executable, str(hint)], input=json.dumps(
        {"hook_event_name": "SessionStart", "cwd": str(root), "session_id": "s", "source": "startup"}),
        env=env_for(tmp_path), capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_session_hint_asks_to_upgrade_old_formats(tmp_path: Path) -> None:
    root = outline_trip(tmp_path)
    assert "旧格式" in session_hint(tmp_path, root)
    fresh = qa_project(tmp_path, "fresh")
    assert "旧格式" not in session_hint(tmp_path, fresh)


def test_session_hint_names_oversized_workbooks(tmp_path: Path) -> None:
    root = qa_project(tmp_path)
    ok(tmp_path, root, "ask", "波形有用吗？", "--done-when", "有对照实验")
    assert "工作本过大" not in session_hint(tmp_path, root)
    workbook = plan_files(root)[1] / "Q1.md"
    workbook.write_text(workbook.read_text(encoding="utf-8") + "\n### 旧笔记\n\n" + "细节" * 9000 + "\n",
                        encoding="utf-8")
    out = session_hint(tmp_path, root)
    assert "工作本过大" in out and "Q1" in out
