#!/usr/bin/env python3
"""`plan` for question-and-answer plans: plain-text views and the write verbs.

Called by top_plan_cli once the project's plan carries `plan-format: qa`. Reads print a
few lines (IDs included: this text is read by AIs; the card website hides them).
Spec: references/qa-plan.md.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import top_qa
from top_common import PlanError

STEP_ICONS = {"done": "✅", "in_progress": "▶", "pending": "☐", "blocked": "⏸", "cancelled": "✕"}

HELP = """plan — 问答式计划（一个项目 = 一串问题；人看问题和答案，AI 在每个问题的工作本里记尝试）

看（不写项目 = 当前目录的项目；别的项目：plan 论文 / plan 25 / plan ~/projects/x）
  plan now                  只打当前目标/焦点/在做/下一步/需要你（不含问答目录，省上下文）
  plan                      目标、正在弄清的问题、当前判断、正在做、下一步、需要你、问答目录
  plan Q4 [全部]            一个问题的工作本：答清标准、答案和历史、尝试（全部 = 全部尝试和笔记）
  plan 当前 | 全部          焦点问题 / 所有问题和答案
  plan P5.38                旧编号去了哪里（迁移前的编号照样能查）
  plan ls [--all] | plan check
  plan upgrade [--apply]    检查计划版本；无版本先检查内容，旧版本按迁移器升级

问题（写给人看：大白话，问题 ≤20 字、答案 ≤40 字，结论在前；不写路径和编号）
  plan ask "问题？" --done-when "怎样算答清" [--why "为什么问"] [--after Q3]
  plan answer Q4 "答案" --ev <证据> [--because Q3.11] [--keep-open]    默认答完就关闭问题
  plan reopen Q4 "原因" [--because Q3.11] [--invalid Q4.8,Q4.9]      撤回答案，立即生效
  plan flag Q5 "要重新确认什么" [--because Q3] | plan flag Q5 --clear
  plan wait Q4 "等谁/要什么" [--you] | plan wait Q4 --clear
  plan focus Q5 [--next Q5.10 | --next "一句话"] [--after]            焦点和下一步（显式，不猜）
  plan rename Q4 "新问法" | plan move Q4 --after Q2 | plan drop Q4 "原因" | plan goal "…"

尝试（写给自己：可以技术化；回头重做/重跑就新加一步并写来源，做完的结果不改写）
  plan add "做什么" [--to Q4] [--gate "怎样算做完"] [--from Q2.4..Q2.6] [--because Q3.11]
  plan start Q4.3 | plan done Q4.3 "结果" --ev <证据> [--supersedes Q4.1] [--commit]
  plan block Q4.3 "等谁/等什么" [--you] | plan cancel Q4.3 "原因" | plan reopen Q4.3
  plan note "一句话" [--on Q4.3|Q4] [--fail|--learn]                   进日志，不进计划

什么进计划：只有长周期的工作。短的、碎的、跟长期目标无关的事不进计划，做完就完。
新项目：plan init "目标"；旧计划改写：plan rewrite 草稿.md --to qa [--apply]
细则：~/.claude/skills/share-top/references/qa-plan.md（旧格式命令：plan help 旧）
"""


class QaCliError(Exception):
    pass


def _clip(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ---------- reading ----------

def _attempt_line(a: dict[str, Any], indent: str = "  ") -> str:
    text = f"{indent}{STEP_ICONS.get(a['state'], '·')} {a['id']} {a['title']}"
    if a.get("result"):
        text += f" → {a['result']}"
    extra = []
    if a.get("from"):
        extra.append("来自 " + ",".join(a["from"]))
    if a["state"] == "in_progress" and a.get("gates"):
        extra.append("验收：" + "；".join(a["gates"]))
    if a["state"] in ("blocked", "cancelled") and a.get("reason"):
        extra.append(("等你：" if a.get("who") == "you" else "") + a["reason"])
    if a.get("invalid"):
        extra.append(f"✗作废：{a['invalid']}" + (f"（{a['invalid_by']}）" if a.get("invalid_by") else ""))
    if a.get("superseded_by"):
        extra.append(f"已被 {a['superseded_by']} 替代")
    return text + (f"（{'；'.join(extra)}）" if extra else "")


def core(project: Path, *, include_questions: bool = True) -> str:
    data = top_qa.show(project)
    goal = data.get("goal") or "（还没写，plan goal \"…\"）"
    lines = [f"{project.name} · 目标：{goal}"]
    focus, current, upcoming = data.get("focus"), data.get("current"), data.get("next")
    if focus:
        lines.append(f"正在弄清：{focus['id']} {focus['text']}")
        lines.append(f"当前判断：{focus.get('summary') or '还没有答案'}")
    else:
        lines.append("正在弄清：没有焦点问题（plan focus Q<n>）")
    if current:
        gates = "；".join(current.get("gates") or [])
        lines.append(f"正在做：{current['id']} {current['title']}" + (f"（验收：{gates}）" if gates else ""))
    for other in data.get("running") or []:
        lines.append(f"也在跑：{other['id']} {other['title']}")
    if upcoming:
        tag = "（候选）" if upcoming.get("source") == "candidate" else ""
        tag += "（做完当前这步后）" if upcoming.get("when") == "after" else ""
        lines.append(f"下一步：{(upcoming.get('id') or '').strip()} {upcoming['title']}{tag}".replace("： ", "："))
    else:
        lines.append("下一步：待选定（plan focus --next …）")
    for need in data.get("needs_you") or []:
        lines.append(f"需要你：{need['id']} " + (f"{need['reason']}（{need['title']}）" if need.get("reason") else need["title"]))
    if include_questions:
        questions = data.get("questions") or []
        lines.append(f"问答（{len(questions)} 个）：" if questions else "问答：还没有问题（plan ask \"…？\"）")
        for q in questions:
            mark = "→" if q.get("focus") else " "
            summary = q.get("summary")
            lines.append(f"{mark} {q['mark']} {q['id']} {q['text']}" + (f" — {summary}" if summary else ""))
    for error in data.get("errors") or []:
        lines.append(f"✗ {error['code']}：{error['message']}")
    version, current = data.get("top_version"), data.get("top_version_current")
    if isinstance(current, int):
        if version is None:
            lines.append(f"版本：未标（当前 v{current}）；plan upgrade")
        elif isinstance(version, int) and version < current:
            lines.append(f"版本：v{version} 落后于 v{current}；plan upgrade")
        elif isinstance(version, int) and version > current:
            lines.append(f"版本：v{version} 高于本 skill v{current}；先更新 skill")
    return "\n".join(lines)


def question(project: Path, qid: str, *, full: bool) -> str:
    data = top_qa.question_view(project, qid, full=full)
    q = data["question"]
    lines = [f"{q['id']} {q['text']} · {q['state_text']} {q['mark']}"]
    lines.append(f"怎样算答清：{q.get('done_when') or '（没写）'}")
    if q.get("why"):
        lines.append(f"为什么问：{_clip(q['why'], 200) if not full else q['why']}")
    answers = q.get("answers") or []
    current = next((a for a in answers if a["status"] == "current"), None)
    if current:
        lines.append(f"答案：r{current['rev']} {current['text']}（{current['date']}；证据 {', '.join(current['ev'])}）")
    for old in reversed([a for a in answers if a["status"] != "current"]):
        label = "撤回" if old["status"] == "withdrawn" else "被替代"
        why = f"：{old['reason']}" if old.get("reason") else ""
        by = f" · {old['by']}" if old.get("by") else ""
        lines.append(f"  旧答案 r{old['rev']} {old['text']}（{label}{why}{by}）")
    if not answers:
        lines.append("答案：还没有")
    if q.get("review"):
        lines.append(f"⚠ 要重新确认：{q['review']['reason']}" + (f"（因为 {q['review']['because']}）" if q['review'].get('because') else ""))
    if q.get("wait"):
        lines.append(f"等待：{q['wait']['reason']}" + ("（等你）" if q["wait"].get("you") else ""))
    total = data["attempts_total"]
    shown = data["attempts"]
    head = f"尝试（共 {total} 个" + ("，显示开放的和最近做完的；plan " + q["id"] + " 全部 看全部）：" if data["attempts_truncated"] else "）：")
    lines.append(head if total else "尝试：还没有（plan add \"…\" --to " + q["id"] + "）")
    lines += [_attempt_line(a) for a in shown]
    if q.get("aliases"):
        lines.append("旧编号：" + "；".join(f"{a['old']} → {'、'.join(a['new']) or '历史'}" for a in q["aliases"][:12])
                     + (f"；共 {len(q['aliases'])} 条" if len(q["aliases"]) > 12 else ""))
    notes = (data.get("notes_md") or "").strip()
    if notes:
        if full:
            lines += ["笔记：", notes]
        else:
            lines.append(f"笔记：{len(notes.splitlines())} 行（plan {q['id']} 全部 看全文；文件 {q.get('file')}）")
    return "\n".join(lines)


def all_questions(project: Path) -> str:
    data = top_qa.show(project)
    lines = []
    for q in data.get("questions") or []:
        counts = q["attempts"]
        lines.append(f"{q['mark']} {q['id']} {q['text']}（{q['state_text']}；尝试 {counts['done']}/{counts['total']}）")
        if q.get("summary"):
            lines.append(f"    {q['summary']}")
    return "\n".join(lines) or "还没有问题"


def alias(project: Path, old_id: str) -> str:
    found = top_qa.resolve_alias(project, old_id)
    if not found:
        raise QaCliError(f"没有 {old_id}：这个计划是问答格式，旧编号只在迁移时登记的对照里（plan 看问题列表）")
    out = []
    for hit in found["hits"]:
        targets = "、".join(hit["new"]) or "历史（没有新对应）"
        out.append(f"{old_id} → {targets}（在 {hit['question']} {hit['question_text']}）")
    return "\n".join(out)


def view(project: Path, tokens: list[str]) -> str:
    """tokens after the project selector: [] | 当前 | 全部 | Q4 [全部] | P5.38"""
    if not tokens:
        return core(project)
    full = tokens[-1] in ("全部", "all")
    head = tokens[0]
    if re.fullmatch(r"Q\d+", head):
        return question(project, head, full=full and len(tokens) > 1)
    if re.fullmatch(r"Q\d+\.\d+", head):
        return question(project, head.split(".")[0], full=True)
    if head in ("当前", "current", "cur"):
        focus = top_qa.focus_question(top_qa.load(project))
        if focus is None:
            raise QaCliError("没有焦点问题：plan focus Q<n>")
        return question(project, focus.id, full=False)
    if head in ("全部", "all"):
        return all_questions(project)
    if re.fullmatch(r"P\d+(?:\.[A-Za-z0-9]+)*", head):
        return alias(project, head)
    raise QaCliError(f"看不懂 {' '.join(tokens)}：plan [Q4 [全部] | 当前 | 全部 | P5.38]")


def ls_row(project: Path) -> str:
    try:
        data = top_qa.show(project)
    except PlanError:
        return "问答 · 读不了"
    questions = data.get("questions") or []
    answered = sum(1 for q in questions if q["state"] == "closed" and q.get("answer"))
    text = f"问答 {answered}/{len(questions)} 已答"
    if data.get("focus"):
        text += f" · 正在弄清 {_clip(data['focus']['text'], 18)}"
    if data.get("current"):
        text += f" · ▶ {_clip(data['current']['title'], 18)}"
    if data.get("needs_you"):
        text += f" · 等你 {len(data['needs_you'])}"
    return text


def now_line(project: Path) -> str:
    data = top_qa.show(project)
    parts = []
    if data.get("focus"):
        parts.append(f"正在弄清 {data['focus']['id']} {_clip(data['focus']['text'], 24)}")
    if data.get("current"):
        parts.append(f"正在做 {data['current']['id']} {_clip(data['current']['title'], 24)}")
    if data.get("next"):
        parts.append(f"下一步 {(data['next'].get('id') or '').strip()} {_clip(data['next']['title'], 24)}".replace("  ", " "))
    return "现在：" + "；".join(parts) if parts else "现在：没有焦点问题（plan focus Q<n>）"


def check(project: Path) -> str:
    result = top_qa.validate(project)
    version = f"v{result['top_version']}" if isinstance(result.get("top_version"), int) else "未标版本"
    lines = [f"{project.name}（问答格式，{version}）：" + {"ok": "没问题", "warn": "有提醒", "block": "有错误"}[result["verdict"]]]
    lines += [f"  ✗ {e['code']}：{e['message']}" for e in result["errors"]]
    lines += [f"  提醒 {w['code']}：{w['message']}\n    → {w['hint']}" for w in result["warnings"]]
    return "\n".join(lines)


# ---------- writing ----------

QA_VERBS = {"ask", "answer", "reopen", "flag", "wait", "drop", "rename", "move", "add", "start", "done", "complete",
            "block", "cancel", "focus", "note", "goal"}
OUTLINE_ONLY = {"insert": "问答格式没有插入：回头重做就 plan add \"…\" --from <旧步骤> --because <原因>",
                "replan": "问答格式里换路线：plan reopen Q<n> \"原因\" 撤回旧答案，再 plan add 新做法",
                "phase": "问答格式没有阶段：plan ask \"问题？\" --done-when \"…\" 加问题",
                "summary": "问答格式没有阶段小结：问题的结论用 plan answer Q<n> \"…\" --ev …",
                "archive": "问答格式不用收起：已答清的问题在目录里只占一行",
                "rewrite": "已经是问答格式了", "migrate": "已经是问答格式了"}


def write(verb: str, args: list[str], project: Path, take, need) -> tuple[dict[str, Any], str]:
    """`take(args, *names, many=, flag=)` / `need(args, n, usage)` come from top_plan_cli."""
    if verb in OUTLINE_ONLY:
        raise QaCliError(OUTLINE_ONLY[verb])
    p = str(project)
    expect = take(args, "--expect")
    if verb == "upgrade":
        apply = take(args, "--apply", flag=True)
        need(args, 0, "plan upgrade [--apply]")
        r = top_qa.upgrade(p, apply=apply, expect=expect)
        if r.get("verdict") == "block":
            return r, "✗ 不能升级：\n" + "\n".join(f"  {e['code']}：{e['message']}" for e in r.get("errors") or []) + \
                f"\n  → {r.get('next_hint')}"
        if r.get("action") == "none":
            return r, f"计划版本已是最新 v{r['to_version']}"
        if r.get("action") == "stamp" and not apply:
            return r, f"计划没有版本号；内容检查通过。\n  → {r['next_hint']}"
        return r, f"已升级计划版本：{r.get('from_version') or '无版本'} → v{r['to_version']}"
    if verb == "ask":
        done_when = take(args, "--done-when", "--done")
        why = take(args, "--why")
        after = take(args, "--after")
        (text,) = need(args, 1, 'plan ask "问题？" --done-when "怎样算答清" [--why "…"] [--after Q3]')
        r = top_qa.ask(p, text, done_when=done_when, why=why, after=after, expect=expect)
        tail = "" if done_when else "\n提醒：没写怎样算答清——在工作本的 ## 怎样算答清 补一句"
        return r, f"已加问题 {r['item_id']}「{text}」" + ("（现在的焦点）" if r.get("focus") == r["item_id"] else "") + tail
    if verb == "answer":
        evidence = take(args, "--ev", "--evidence", many=True)
        because = take(args, "--because")
        cond = take(args, "--cond", "--when")
        keep_open = take(args, "--keep-open", flag=True)
        qid, text = need(args, 2, 'plan answer Q4 "答案" --ev <证据> [--because …] [--keep-open]')
        r = top_qa.answer(p, qid, text, evidence=evidence, because=because, keep_open=keep_open, cond=cond, expect=expect)
        out = f"{qid} 答案 r{r['rev']}：{text}" + ("（问题仍开着）" if keep_open else "（问题已答清）")
        if r.get("open_attempts"):
            out += f"\n提醒：{qid} 还有没关的尝试 {', '.join(r['open_attempts'])}：做完、取消或留着都行"
        if r.get("focus_cleared"):
            out += "\n焦点问题答清了：plan focus Q<n> 选下一个要弄清的问题"
        return r, out
    if verb == "reopen":
        target = args[0] if args else ""
        if re.fullmatch(r"Q\d+\.\d+", target):
            (aid,) = need(args, 1, "plan reopen Q4.3")
            r = top_qa.reopen_attempt(p, aid, expect=expect)
            return r, f"重开 {aid}"
        because = take(args, "--because")
        invalid = take(args, "--invalid", many=True)
        qid, reason = need(args, 2, 'plan reopen Q4 "原因" [--because Q3.11] [--invalid Q4.8,Q4.9]')
        r = top_qa.reopen_question(p, qid, reason, because=because, invalid=invalid, expect=expect)
        out = (f"已撤回 {qid} 的答案 r{r['withdrawn']}：{reason}" if r.get("withdrawn") else f"重开 {qid}：{reason}")
        if r.get("invalid"):
            out += f"\n标为作废：{', '.join(r['invalid'])}"
        if r.get("affected"):
            out += ("\n这些问题的答案引用了被撤回的结果，看要不要标复核："
                    + "；".join(f"{a['id']} {a['text']}" for a in r["affected"])
                    + f"\n  → plan flag <Q> \"依赖的 {qid} 被撤回\" --because {qid}")
        return r, out
    if verb == "flag":
        clear = take(args, "--clear", flag=True)
        because = take(args, "--because")
        if clear:
            (qid,) = need(args, 1, "plan flag Q5 --clear")
            return top_qa.flag(p, qid, None, clear=True, expect=expect), f"{qid} 已复核，去掉 ⚠"
        qid, reason = need(args, 2, 'plan flag Q5 "要重新确认什么" [--because Q3]')
        return top_qa.flag(p, qid, reason, because=because, expect=expect), f"{qid} 标了 ⚠ 要重新确认：{reason}"
    if verb == "wait":
        clear = take(args, "--clear", flag=True)
        you = take(args, "--you", flag=True)
        if clear:
            (qid,) = need(args, 1, "plan wait Q4 --clear")
            return top_qa.wait(p, qid, None, clear=True, expect=expect), f"{qid} 不再等待"
        qid, reason = need(args, 2, 'plan wait Q4 "等谁/要什么" [--you]')
        return top_qa.wait(p, qid, reason, you=you, expect=expect), f"{qid} 等待：{reason}" + ("（等你）" if you else "")
    if verb == "drop":
        qid, reason = need(args, 2, 'plan drop Q4 "原因"')
        r = top_qa.drop(p, qid, reason, expect=expect)
        return r, f"放弃 {qid}：{reason}" + (f"（取消 {len(r['cancelled'])} 步）" if r.get("cancelled") else "")
    if verb == "rename":
        target, text = need(args, 2, 'plan rename Q4 "新问法" | plan rename Q4.3 "新说法"')
        return top_qa.rename(p, target, text, expect=expect), f"改名 {target}「{text}」"
    if verb == "move":
        after = take(args, "--after")
        first = take(args, "--first", flag=True)
        (qid,) = need(args, 1, "plan move Q4 --after Q2 | plan move Q4 --first")
        if not after and not first:
            raise QaCliError("放哪：--after Q2，或 --first 放最前")
        return top_qa.move(p, qid, after=after, expect=expect), f"已移动 {qid}" + (f" 到 {after} 后面" if after else " 到最前")
    if verb == "add":
        to = take(args, "--to", "--question")
        gates = take(args, "--gate", many=True)
        from_ids = take(args, "--from", many=True)
        because = take(args, "--because")
        (title,) = need(args, 1, 'plan add "做什么" [--to Q4] [--gate "…"] [--from Q2.4..Q2.6] [--because Q3.11]')
        r = top_qa.add(p, title, to=to, gates=gates, from_ids=from_ids, because=because, expect=expect)
        return r, f"已加 {r['item_id']}「{title}」"
    if verb == "start":
        (aid,) = need(args, 1, "plan start Q4.3")
        r = top_qa.start(p, aid, expect=expect)
        return r, f"开始 {aid}（焦点 {r['focus']}）"
    if verb in ("done", "complete"):
        evidence = take(args, "--ev", "--evidence", many=True)
        no_artifact = take(args, "--no-artifact", "--no-artifact-reason")
        supersedes = take(args, "--supersedes", many=True)
        result_text = take(args, "--result")
        commit = take(args, "--commit", flag=True)
        if result_text is None and len(args) == 2:
            result_text = args.pop(1)
        (aid,) = need(args, 1, 'plan done Q4.3 "结果" --ev <证据> [--supersedes Q4.1] [--commit]')
        if not result_text:
            raise QaCliError(f'做完要写一句结果：plan done {aid} "结果" --ev <证据>')
        r = top_qa.done(p, aid, result_text, evidence=evidence, no_artifact=no_artifact, supersedes=supersedes,
                        expect=expect)
        out = f"完成 {aid}：{result_text}" + (f"（替代 {', '.join(r['supersedes'])}）" if r.get("supersedes") else "")
        if commit:
            git = top_qa.commit_done(p, aid)
            r["git"] = git
            shas = [c.get("commit") for c in git.get("commits", []) if c.get("commit")]
            errors = [c.get("error") for c in git.get("commits", []) if c.get("error")]
            out += f"，已提交 {shas[0]}" if shas else ""
            out += f"\n提交失败：{errors[0]}" if errors else ""
            if git.get("track_hint"):
                out += f"\n提醒：{git['track_hint']}"
        return r, out
    if verb in ("block", "cancel"):
        you = take(args, "--you", flag=True) if verb == "block" else False
        aid, reason = need(args, 2, f'plan {verb} Q4.3 "原因"' + (" [--you]" if verb == "block" else ""))
        if verb == "block":
            return top_qa.block(p, aid, reason, you=you, expect=expect), f"卡住 {aid}：{reason}" + ("（等你）" if you else "")
        return top_qa.cancel(p, aid, reason, expect=expect), f"取消 {aid}：{reason}"
    if verb == "focus":
        next_step = take(args, "--next")
        after = take(args, "--after", flag=True)
        rest = need(args, len(args), "plan focus Q5 [--next Q5.10 | --next \"一句话\"] [--after]")
        if len(rest) > 1:
            raise QaCliError("用法：plan focus Q5 [--next Q5.10 | --next \"一句话\"] [--after]")
        qid = rest[0] if rest else None
        if qid is None and next_step is None:
            raise QaCliError("用法：plan focus Q5 [--next …]")
        r = top_qa.focus(p, qid, next_step=next_step, after=after, expect=expect)
        return r, f"焦点 {r.get('item_id') or '无'}" + (f"；下一步 {r['next']}" if r.get("next") else "")
    if verb == "note":
        kind = "fail" if take(args, "--fail", flag=True) else "learn" if take(args, "--learn", flag=True) else "progress"
        on = take(args, "--on", "--id")
        (text,) = need(args, 1, 'plan note "一句话" [--on Q4.3|Q4] [--fail|--learn]')
        r = top_qa.note(p, text, on=on, kind=kind)
        line = f"已记（{ {'fail': '失败', 'learn': '心得', 'progress': '进展'}[kind] }，{r['item_id']}）"
        if r.get("escalate"):
            line += f"\n⚠ {r['next_hint']}"
        return r, line
    if verb == "goal":
        (text,) = need(args, 1, 'plan goal "一两句：做完是什么样"')
        return top_qa.set_goal(p, text, expect=expect), "已改目标"
    raise QaCliError(f"不认识的命令 {verb}；plan help")


def not_qa_hint(verb: str) -> str:
    return (f"plan {verb} 是问答格式的命令，这个项目还是旧格式/目录格式计划。"
            "改成问答格式：按 references/qa-plan.md 写草稿，plan rewrite 草稿.md --to qa 预览，确认后加 --apply")
