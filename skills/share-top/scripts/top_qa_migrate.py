#!/usr/bin/env python3
"""`plan rewrite 草稿.md --to qa`: turn a legacy or outline plan into a question-and-answer plan.

The draft is one Markdown file: the root part (title, `<!-- plan-format: qa … -->`, `## 目标`)
followed by one block per question, each starting with `# Q<n> 问题` and written like a work
file (`## 为什么问` / `## 怎样算答清` / `## 答案` / `## 尝试` / `## 旧编号` / `## 笔记`). Block
order is the order of the questions.

Preview checks: the draft parses and passes the hard checks; every old ID (tasks, phases,
archived tasks) appears on the left of some `## 旧编号` line (`P5.*` covers a whole prefix);
every old open task maps to something still open, or is listed in `dropped_open`.
Apply: under the project lock, re-read the old plan, snapshot the old root, details article
and plan archive into `_logs/plan-history/<time>-before-qa/`, put the work files in place,
write the root last (that switches the format), log one line. Interrupted before the root
write, the project still reads as the old format; a rerun moves the leftover aside.
"""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import qa_format as qf
import top_plan
import top_qa
from top_common import PlanConflict, PlanError, parse_plan, read_text

DETAILS_NAME = "_plan_details.md"


def split_draft(text: str) -> tuple[str, list[str]]:
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if re.match(r"^#\s+Q\d+\s", line)]
    if not starts:
        return text, []
    root = "\n".join(lines[: starts[0]]) + "\n"
    blocks = ["\n".join(lines[a:b]).strip("\n") + "\n" for a, b in zip(starts, starts[1:] + [len(lines)])]
    return root, blocks


def _old_ids(plan_path: Path) -> tuple[list[str], list[str], str]:
    """(all old IDs, old open task IDs, old format) of the plan being replaced."""
    if not plan_path.is_file():
        return [], [], "none"
    state = parse_plan(plan_path)
    if state.format == "qa":
        raise PlanError("已经是问答格式了")
    ids = [item.id for item in state.items] + [phase.id for phase in state.phases]
    ids += sorted(top_plan._archived_ids(plan_path) - set(ids))
    open_ids = [item.id for item in state.items if not item.closed]
    return list(dict.fromkeys(ids)), open_ids, state.format


def _plan_build(root_dir: Path, plan_path: Path, root_text: str, blocks: list[str]):
    """Parse the draft into a project model and the rendered files, without touching disk."""
    root = qf.parse_root_text(root_text)
    if root.errors:
        raise PlanError("草稿开头不对：" + "；".join(m for _, m in root.errors)
                        + f"（第二行写 <!-- plan-format: qa · top-version={qf.PLAN_VERSION} -->）")
    if root.version is not None and root.version > qf.PLAN_VERSION:
        raise PlanError(f"草稿版本 v{root.version} 高于本 skill 的 v{qf.PLAN_VERSION}；先更新 skill")
    root.version = qf.PLAN_VERSION
    files: dict[str, str] = {}
    order: list[str] = []
    errors: list[tuple[str, str]] = []
    for block in blocks:
        question = qf.parse_question_text(block)
        errors += question.errors
        if not question.id:
            continue
        if question.id in order:
            errors.append(("QA_ID_DUP", f"草稿里 {question.id} 出现两次"))
            continue
        if not question.created:
            question.created = datetime.now().strftime("%Y-%m-%d")
        order.append(question.id)
        files[f"{question.id}.md"] = qf.render_question(question)
    root.order = order
    placeholder = qf.render_root(root, {}, [])
    proj = top_qa._build(root_dir, plan_path, placeholder, files)
    proj.root.order = order
    proj.parse_errors += errors
    return proj, files


def migrate(project: str, draft: str, *, apply: bool = False, accept_dropped: bool = False) -> dict[str, Any]:
    root_dir, plan_path = top_plan._plan_path(project)
    draft_path = Path(draft).expanduser()
    if not draft_path.is_absolute():
        draft_path = (Path.cwd() / draft_path).resolve()
    if not draft_path.is_file():
        raise PlanError(f"找不到草稿 {draft_path}")
    root_text, blocks = split_draft(read_text(draft_path))
    if not blocks:
        raise PlanError("草稿里没有问题块（每个问题以 `# Q<n> 问题` 开头）")
    source_sha = qf.text_sha256(read_text(plan_path)) if plan_path.is_file() else ""
    proj, files = _plan_build(root_dir, plan_path, root_text, blocks)
    errors = [{"code": c, "message": m} for c, m in top_qa.hard_errors(proj)]
    old_ids, old_open, old_format = _old_ids(plan_path)
    aliases = [(old, targets) for q in proj.questions.values() for old, targets in q.aliases]
    missing = [old for old in old_ids if not any(qf.alias_covers(a, old) for a, _ in aliases)]
    if missing:
        errors.append({"code": "QA_ALIAS_MISSING",
                       "message": f"{len(missing)} 个旧编号没有对照（写进某个问题的 ## 旧编号；P5.* 可以一次盖住一整段）："
                                  + "、".join(missing[:20]) + ("…" if len(missing) > 20 else "")})
    open_new = {a.id for a in proj.all_attempts() if not a.closed}
    open_new |= {q.id for q in proj.questions.values() if q.state not in ("closed", "dropped")}
    dropped_open = []
    for old in old_open:
        targets = [t for a, ts in aliases if qf.alias_covers(a, old) for t in ts]
        if not any(t in open_new for t in targets):
            dropped_open.append(old)
    warns = top_qa.warnings(proj)
    warns = [w for w in warns if w["code"] != "QA_MIRROR_STALE"]
    result: dict[str, Any] = {
        "schema_version": top_plan.SCHEMA_VERSION, "tool": "plan-rewrite-qa", "format": "qa",
        "apply": False, "old_format": old_format, "questions": len(files),
        "attempts": len(proj.all_attempts()), "old_ids": len(old_ids),
        "files": [f"{qf.QUESTIONS_DIR}/{name}" for name in files], "errors": errors, "warnings": warns,
        "dropped_open": dropped_open,
        "preview": [f"{q.mark} {q.id} {q.text}" + (f" — {qf.answer_summary(q)}" if qf.answer_summary(q) else "")
                    for q in proj.ordered()],
    }
    if errors:
        result.update(verdict="block", next_hint="修好草稿再预览")
        return result
    if dropped_open and not accept_dropped:
        result.update(verdict="block" if apply else "warn",
                      next_hint="旧计划里这些未完成的任务在新计划里没有开着的去处：补进草稿，或确认放弃后加 --accept-dropped")
        if apply:
            return result
    if not apply:
        result.setdefault("verdict", "ok")
        result.setdefault("next_hint", "预览通过：确认后加 --apply")
        return result
    return _apply(root_dir, plan_path, proj, files, result, source_sha)


def _apply(root_dir: Path, plan_path: Path, proj, files: dict[str, str], result: dict[str, Any],
           source_sha: str) -> dict[str, Any]:
    top = plan_path.parent
    qdir = top / qf.QUESTIONS_DIR
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    snapshot = top_plan._log_dir(plan_path) / "plan-history" / f"{stamp}-before-qa"
    with top_qa.project_lock(plan_path):
        current = read_text(plan_path) if plan_path.is_file() else ""
        if qf.is_qa_text(current):
            raise PlanError("已经是问答格式了（别处刚迁移过？）")
        if (qf.text_sha256(current) if current else "") != source_sha:
            raise PlanConflict("旧计划在检查之后又被改过：重新预览再 --apply")
        snapshot.mkdir(parents=True, exist_ok=True)
        moved = []
        for source in (plan_path, top / DETAILS_NAME, top_plan._log_dir(plan_path) / top_plan.ARCHIVE_NAME):
            if source.is_file():
                shutil.copy2(source, snapshot / source.name)
                moved.append(source.name)
        if qdir.exists():   # leftover of an interrupted migration
            shutil.move(str(qdir), str(snapshot / f"{qf.QUESTIONS_DIR}.leftover"))
        for stale in top.glob(f".{qf.QUESTIONS_DIR}.tmp-*"):   # temp dir of an interrupted apply
            shutil.move(str(stale), str(snapshot / stale.name.lstrip(".")))
        temp = top / f".{qf.QUESTIONS_DIR}.tmp-{stamp}"
        temp.mkdir()
        for name, text in files.items():
            (temp / name).write_text(text, encoding="utf-8")
        temp.rename(qdir)
        proj.files = dict(files)
        root_text = top_qa.render_root(proj)
        top_qa.atomic_write(plan_path, root_text)
        details = top / DETAILS_NAME
        if details.is_file():
            details.unlink()   # copied into the snapshot; its content now lives in the work files' notes
        log = top_plan._append_log_line(
            plan_path, f"migrate qa · questions={len(files)} · snapshot={snapshot.relative_to(top)}")
    check = top_qa.validate(str(root_dir))
    result.update(apply=True, snapshot=str(snapshot.relative_to(root_dir)), snapshot_files=moved, log=log,
                  verdict="ok" if check["verdict"] != "block" else "block", check=check,
                  next_hint=("已切换成问答格式：plan 和 plan check 核对；回滚 = 把快照里的文件拷回原位并删掉 "
                             f"{qf.QUESTIONS_DIR}/"))
    return result


def summary_text(result: dict[str, Any]) -> str:
    if result.get("errors"):
        return "✗ 草稿有问题：\n" + "\n".join(f"  {e['code']}：{e['message']}" for e in result["errors"])
    head = "已切换成问答格式" if result.get("apply") else "预览通过"
    lines = [f"{head}：{result['questions']} 个问题、{result['attempts']} 个尝试；旧编号 {result['old_ids']} 个都有对照"]
    lines += [f"  {line}" for line in result.get("preview") or []]
    for warning in result.get("warnings") or []:
        lines.append(f"  提醒 {warning['code']}：{warning['message']}")
    if result.get("dropped_open"):
        lines.append("  旧计划里这些未完成的任务没有开着的去处：" + "；".join(result["dropped_open"][:12]))
    if result.get("snapshot"):
        lines.append(f"  旧文件快照：{result['snapshot']}")
    lines.append(result.get("next_hint") or "")
    return "\n".join(line for line in lines if line)
