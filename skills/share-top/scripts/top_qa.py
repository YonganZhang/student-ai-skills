#!/usr/bin/env python3
"""Question-and-answer plans: views, checks and writes (format `qa`, see references/qa-plan.md).

Reads never write. Every write takes a per-project lock (kept under ~/.cache so it is
never committed), rereads the files inside it, optionally compares the caller's revision
(`expect`), applies one semantic change to the in-memory model, refuses a change that adds
an error, then writes the touched work files first (the source of truth), the root second
and the log last. A crash between those steps can leave a stale summary (rebuilt by the
next write) or a new work file missing from the order (re-attached at the end by the next
write); a focus change in the root can be lost. Readers always compute from the work files.
"""

from __future__ import annotations

import fcntl
import hashlib
import os
import re
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Generator

import qa_format as qf
import top_plan
from top_common import PlanConflict, PlanError, PlanItem

QUESTION_CHARS = 20
ANSWER_CHARS = 40
GOAL_CHARS = 80
RECENT_DONE = 8
NOTES_LIMIT = 20_000
LOCK_TIMEOUT_S = 15.0
# codes that mean the files could not be read completely: writing would lose content
LOSSY = {"QA_FORMAT_MARK", "QA_ROOT_HEADING", "QA_WORK_HEADER", "QA_LINE", "QA_SECTION", "QA_ID_MISMATCH",
         "QA_UNKNOWN", "QA_VERSION"}
DONE_TEXT = {"closed": "答清了", "dropped": "放弃了", "waiting": "在等待", "active": "在弄", "todo": "还没开始"}


@dataclass
class QaProject:
    root_dir: Path
    plan_path: Path
    root: qf.QaRoot
    questions: dict[str, qf.Question]
    root_text: str
    files: dict[str, str]
    revision: str
    parse_errors: list[tuple[str, str]]

    def attempt(self, attempt_id: str) -> qf.Attempt | None:
        question = self.questions.get(attempt_id.split(".", 1)[0])
        return question.attempt(attempt_id) if question else None

    def ordered(self) -> list[qf.Question]:
        return [self.questions[qid] for qid in self.root.order if qid in self.questions]

    def all_attempts(self) -> list[qf.Attempt]:
        return [a for q in self.ordered() for a in q.attempts]


def is_qa(plan_path: Path) -> bool:
    try:
        with plan_path.open(encoding="utf-8", errors="replace") as handle:
            head = "".join(handle.readline() for _ in range(6))
    except OSError:
        return False
    return qf.is_qa_text(head)


def _build(root_dir: Path, plan_path: Path, root_text: str, files: dict[str, str]) -> QaProject:
    root = qf.parse_root_text(root_text)
    errors = list(root.errors)
    questions: dict[str, qf.Question] = {}
    qdir = qf.questions_dir(plan_path)
    for name, text in files.items():
        question = qf.parse_question_text(text, qdir / name)
        errors += question.errors
        if question.id and question.id != Path(name).stem:
            errors.append(("QA_ID_MISMATCH", f"{name} 的标题写的是 {question.id}"))
        questions[Path(name).stem] = question
    _derive_all(questions)
    return QaProject(root_dir, plan_path, root, questions, root_text, files,
                     qf.revision(root_text, files), errors)


def _derive_all(questions: dict[str, qf.Question]) -> None:
    """`superseded_by` of every attempt from the `supersedes` of done ones, across questions."""
    by_id = {a.id: a for q in questions.values() for a in q.attempts}
    for attempt in by_id.values():
        attempt.superseded_by = ""
    for attempt in by_id.values():
        if attempt.state == "done":
            for old in attempt.supersedes:
                if old in by_id:
                    by_id[old].superseded_by = attempt.id


def load(project: str | Path) -> QaProject:
    root_dir, plan_path = top_plan._plan_path(str(project))
    if not plan_path.is_file():
        raise PlanError(f"task plan not found: {plan_path}")
    root_text, files = qf.read_project(plan_path)
    return _build(root_dir, plan_path, root_text, files)


# ---------- checks ----------

def _known_ids(proj: QaProject) -> set[str]:
    ids = set(proj.questions)
    for question in proj.questions.values():
        ids |= {a.id for a in question.attempts}
    return ids


_OLD_ID_RE = re.compile(r"^P\d+(?:\.[A-Za-z0-9]+)*$")


def _unknown(proj: QaProject, token: str, message: str) -> PlanError:
    """Refusal for an ID that is not in the plan; a pre-migration ID says where it went, so a
    window still holding old IDs can carry on instead of guessing."""
    if not _OLD_ID_RE.match(token or ""):
        return PlanError(message)
    hits = [(old, targets) for q in proj.ordered() for old, targets in q.aliases if qf.alias_covers(old, token)]
    exact = [targets for old, targets in hits if old == token]
    targets = [t for group in (exact or [t for _old, t in hits]) for t in group]
    if targets:
        return PlanError(f"{token} 是迁移前的旧编号，现在是 {'、'.join(dict.fromkeys(targets))}（plan {token} 看对照）")
    if hits:
        return PlanError(f"{token} 是迁移前的旧编号，已归入历史，没有新对应（plan 看问题列表）")
    return PlanError(f"{token} 是旧格式的编号，迁移时没有登记（plan 看问题列表）")


def hard_errors(proj: QaProject) -> list[tuple[str, str]]:
    errors = list(proj.parse_errors)
    known = _known_ids(proj)
    for qid in proj.root.order:
        if qid not in proj.questions:
            errors.append(("QA_MISSING", f"问答节列了 {qid}，但没有 {qf.QUESTIONS_DIR}/{qid}.md"))
    for qid in proj.questions:
        if qid not in proj.root.order:
            errors.append(("QA_ORPHAN", f"{qf.QUESTIONS_DIR}/{qid}.md 没有列在问答节里"))
    seen_attempts: set[str] = set()
    for qid, question in proj.questions.items():
        if question.state not in qf.QUESTION_STATES:
            errors.append(("QA_STATE", f"{qid} 的状态 {question.state} 不认识（{'/'.join(qf.QUESTION_STATES)}）"))
        if question.state == "waiting" and not question.wait:
            errors.append(("QA_WAIT", f"{qid} 在等待，但没写等谁、要什么"))
        revs = [a.rev for a in question.answers]
        if len(revs) != len(set(revs)):
            errors.append(("QA_ID_DUP", f"{qid} 的答案修订号重复"))
        current = [a for a in question.answers if a.status == "current"]
        for answer in question.answers:
            if answer.status not in qf.ANSWER_STATUSES:
                errors.append(("QA_ANSWER_STATUS", f"{qid} r{answer.rev} 状态 {answer.status} 不认识"))
            if not answer.ev:
                errors.append(("QA_ANSWER_EVIDENCE", f"{qid} r{answer.rev} 没有证据（ev=）"))
        if len(current) > 1:
            errors.append(("QA_ANSWER_POINTER", f"{qid} 有 {len(current)} 个当前答案"))
        if current and question.answer_rev != current[0].rev:
            errors.append(("QA_ANSWER_POINTER", f"{qid} 头部 answer= 应指向 r{current[0].rev}"))
        if not current and question.answer_rev is not None:
            errors.append(("QA_ANSWER_POINTER", f"{qid} 头部 answer=r{question.answer_rev} 不是当前答案"))
        for attempt in question.attempts:
            if attempt.question != qid:
                errors.append(("QA_ID_MISMATCH", f"{attempt.id} 写在 {qid} 的工作本里"))
            if attempt.id in seen_attempts:
                errors.append(("QA_ID_DUP", f"尝试 {attempt.id} 重复"))
            seen_attempts.add(attempt.id)
            if attempt.state not in qf.ATTEMPT_STATES:
                errors.append(("QA_STATE", f"{attempt.id} 的状态 {attempt.state} 不认识"))
            if attempt.state == "done" and not (attempt.ev or attempt.no_artifact_reason):
                errors.append(("QA_EVIDENCE", f"{attempt.id} 做完了但没有证据或无产物原因"))
            if attempt.state in ("blocked", "cancelled") and not attempt.reason:
                errors.append(("QA_REASON", f"{attempt.id} 是 {attempt.state}，要写原因"))
            for ref in [*attempt.from_ids, *attempt.supersedes]:
                if ref not in known:
                    errors.append(("QA_REF", f"{attempt.id} 引用了不存在的 {ref}"))
            for ref in (attempt.because, attempt.invalid_by):
                if ref and qf.QA_ID_RE.match(ref) and ref not in known:
                    errors.append(("QA_REF", f"{attempt.id} 引用了不存在的 {ref}"))
        for old, targets in question.aliases:
            for target in targets:
                if target not in known:
                    errors.append(("QA_REF", f"{qid} 的旧编号 {old} 指向不存在的 {target}（写已有编号，或写“历史”）"))
        for ref in (question.review_by,):
            if ref and qf.QA_ID_RE.match(ref) and ref not in known:
                errors.append(("QA_REF", f"{qid} 的 review_by={ref} 不存在"))
    root = proj.root
    if root.focus and root.focus not in proj.questions:
        errors.append(("QA_REF", f"焦点 {root.focus} 不存在"))
    if root.next_id and proj.attempt(root.next_id) is None:
        errors.append(("QA_REF", f"下一步 {root.next_id} 不存在"))
    if root.next_when not in qf.NEXT_WHEN:
        errors.append(("QA_STATE", f"next_when={root.next_when} 只能是 now/after"))
    if root.version is not None and root.version > qf.PLAN_VERSION:
        errors.append(("TOP_VERSION_NEW",
                       f"计划版本 v{root.version} 高于本 skill 的 v{qf.PLAN_VERSION}；先更新 skill，不能降级写入"))
    return errors


# paths, code, file names and plan IDs; plain numbers with units are fine in an answer
_TECH_RE = re.compile(r"(?:[\w.-]+/){2,}|`|[A-Za-z0-9]_[A-Za-z0-9]|\.(?:md|py|json|ya?ml|sh|csv|ipynb|txt|pt|ckpt)\b"
                      r"|\b[PQ]\d+(?:\.[A-Za-z0-9]+)*\b")
_LATIN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]+")


def looks_technical(text: str) -> bool:
    """Paths, code, plan IDs or three and more Latin terms in a sentence meant for people."""
    return bool(_TECH_RE.search(text or "")) or len(_LATIN_RE.findall(text or "")) >= 3


def version_warnings(proj: QaProject) -> list[dict[str, str]]:
    version = proj.root.version
    current = qf.PLAN_VERSION
    if version is None:
        return [{"code": "TOP_VERSION_MISSING",
                 "message": f"计划没有版本号（当前 v{current}）；先检查内容再加版本",
                 "hint": "plan check 看有没有错误；通过后 plan upgrade --apply 标记为当前版本"}]
    if version < current:
        return [{"code": "TOP_VERSION_OLD",
                 "message": f"计划版本 v{version} 落后于当前 v{current}",
                 "hint": "plan upgrade 预览迁移；有迁移器时 plan upgrade --apply"}]
    return []


def warnings(proj: QaProject) -> list[dict[str, str]]:
    out: list[dict[str, str]] = version_warnings(proj)
    long_q = [f"{q.id}({len(q.text)} 字)" for q in proj.ordered() if len(q.text) > QUESTION_CHARS]
    long_a = [f"{q.id}({len(q.current_answer.text)} 字)" for q in proj.ordered()
              if q.current_answer and len(q.current_answer.text) > ANSWER_CHARS]
    if long_q or long_a or len(proj.root.goal) > GOAL_CHARS:
        what = [f"问题 {', '.join(long_q[:5])}" if long_q else "", f"答案 {', '.join(long_a[:5])}" if long_a else "",
                f"目标 {len(proj.root.goal)} 字" if len(proj.root.goal) > GOAL_CHARS else ""]
        out.append({"code": "QA_TEXT_LONG", "message": "给人看的文字偏长：" + "；".join(w for w in what if w),
                    "hint": f"问题 ≤{QUESTION_CHARS} 字、答案 ≤{ANSWER_CHARS} 字、目标 ≤{GOAL_CHARS} 字是建议；"
                            "细节放进工作本的尝试和笔记（plan rename / plan answer 改说法）"})
    technical = [f"{q.id}「{q.text}」" for q in proj.ordered() if looks_technical(q.text)]
    technical += [f"{q.id} 的答案" for q in proj.ordered()
                  if q.current_answer and looks_technical(q.current_answer.text)]
    if looks_technical(proj.root.goal):
        technical.append("目标")
    if technical:
        out.append({"code": "QA_TEXT_TECHNICAL", "message": "给人看的文字里有路径、编号或成串术语：" + "；".join(technical[:4]),
                    "hint": "问题、答案、目标写大白话；路径、参数、实验编号写进工作本"})
    no_done_when = [q.id for q in proj.ordered() if q.state not in ("dropped",)
                    and (not q.done_when or q.done_when.startswith("（待补"))]
    if no_done_when:
        out.append({"code": "QA_NO_DONE_WHEN", "message": f"没写“怎样算答清”：{', '.join(no_done_when[:8])}",
                    "hint": "在工作本的 ## 怎样算答清 写一句验收（直接编辑工作本这一节即可）"})
    focus = proj.questions.get(proj.root.focus)
    if focus is not None and focus.state in ("closed", "dropped"):
        out.append({"code": "QA_FOCUS_CLOSED", "message": f"焦点 {focus.id} 已经{DONE_TEXT[focus.state]}",
                    "hint": "plan focus Q<n> 选下一个要弄清的问题"})
    if render_root(proj) != proj.root_text:
        out.append({"code": "QA_MIRROR_STALE", "message": "根文件的摘要和工作本不一致（被手改过或上次写入没走完）",
                    "hint": "下一次任何 plan 写操作会重建；问题的顺序、目标、焦点以根文件为准"})
    return out


def validate(project: str | Path) -> dict[str, Any]:
    proj = load(project)
    errors = [{"code": c, "message": m} for c, m in hard_errors(proj)]
    warns = warnings(proj)
    return {"schema_version": top_plan.SCHEMA_VERSION, "tool": "plan-validate", "format": "qa",
            "project": str(proj.root_dir), "task_plan": str(proj.plan_path.relative_to(proj.root_dir)),
            "top_version": proj.root.version, "top_version_current": qf.PLAN_VERSION,
            "verdict": "block" if errors else "warn" if warns else "ok",
            "errors": errors, "warnings": warns, "revision": proj.revision,
            "next_hint": "修掉 errors（多半是手改了工作本的结构区）" if errors else
                         "按 warnings 的 hint 改说法" if warns else "没问题"}


# ---------- views ----------

def focus_question(proj: QaProject) -> qf.Question | None:
    return qf.focus_question(proj.root, proj.ordered())


def _attempt_brief(attempt: qf.Attempt) -> dict[str, Any]:
    return {"id": attempt.id, "title": attempt.title, "state": attempt.state, "question": attempt.question,
            "gates": list(attempt.gates)}


def now_view(proj: QaProject) -> dict[str, Any]:
    return qf.compute_now(proj.root, proj.ordered())


def now_lines(proj: QaProject) -> list[str]:
    view = now_view(proj)
    focus, current, upcoming = view["focus"], view["current"], view["next"]
    lines = [f"- 正在弄清：{focus.text}" if focus else "- 正在弄清：没有正在弄的问题"]
    if focus is not None:
        lines.append(f"- 当前判断：{qf.answer_summary(focus) or '还没有答案'}")
    if current is not None:
        lines.append(f"- 正在做：{current.title}")
    if upcoming is not None:
        lines.append(f"- 下一步：{upcoming['title']}" + ("（做完当前这步后）" if upcoming["when"] == "after" else ""))
    else:
        lines.append("- 下一步：待选定")
    if view["needs_you"]:
        lines.append("- 需要你：" + "；".join(n["reason"] or n["title"] for n in view["needs_you"][:3]))
    return lines


def render_root(proj: QaProject) -> str:
    return qf.render_root(proj.root, proj.questions, now_lines(proj))


def _answer_dict(answer: qf.Answer | None) -> dict[str, Any] | None:
    if answer is None:
        return None
    return {"rev": answer.rev, "text": answer.text, "date": answer.date, "ev": list(answer.ev),
            "because": answer.because, "status": answer.status, "reason": answer.reason, "by": answer.by,
            "cond": answer.cond}


def _question_brief(question: qf.Question, focus: qf.Question | None) -> dict[str, Any]:
    current = question.current_answer
    withdrawn = question.withdrawn_answer
    counts = {"total": len(question.attempts), "done": sum(1 for a in question.attempts if a.state == "done"),
              "open": sum(1 for a in question.attempts if not a.closed)}
    return {
        "id": question.id, "text": question.text, "state": question.state, "state_text": qf.STATE_TEXT.get(question.state, question.state),
        "mark": question.mark, "focus": focus is not None and question.id == focus.id,
        "answer": {"rev": current.rev, "text": current.text, "date": current.date} if current else None,
        "withdrawn": {"rev": withdrawn.rev, "text": withdrawn.text, "reason": withdrawn.reason, "by": withdrawn.by}
        if withdrawn else None,
        "revisions": len(question.answers),
        "summary": qf.answer_summary(question),
        "review": {"reason": question.review, "because": question.review_by} if question.review else None,
        "wait": {"reason": question.wait, "you": question.wait_who == "you"} if question.state == "waiting" else None,
        "attempts": counts,
    }


def show(project: str | Path) -> dict[str, Any]:
    proj = load(project)
    view = now_view(proj)
    focus, current, upcoming = view["focus"], view["current"], view["next"]
    errors = [{"code": c, "message": m} for c, m in hard_errors(proj)]
    attempts = proj.all_attempts()
    counts = {s: sum(1 for a in attempts if a.state == s) for s in qf.ATTEMPT_STATES}
    ids = [a["id"] for a in (_attempt_brief(current) if current else None, upcoming) if a and a.get("id")]
    if focus is not None:
        ids.append(focus.id)
    if current is not None:
        hint = f"继续 {current.id}：{current.title}"
    elif upcoming is not None:
        hint = f"下一步 {upcoming['id'] or ''} {upcoming['title']}".replace("  ", " ")
    elif focus is not None:
        hint = f"焦点 {focus.id} 没有待办的尝试：plan add \"…\" 加一步，或 plan answer {focus.id} \"…\" --ev …"
    else:
        hint = "没有焦点问题：plan focus Q<n> 选一个，或 plan ask \"…？\" 加一个问题"
    return {
        "schema_version": top_plan.SCHEMA_VERSION, "tool": "plan-show", "format": "qa",
        "project": str(proj.root_dir), "task_plan": str(proj.plan_path.relative_to(proj.root_dir)),
        "top_version": proj.root.version, "top_version_current": qf.PLAN_VERSION,
        "revision": proj.revision, "goal": proj.root.goal or None,
        "focus": {"id": focus.id, "text": focus.text, "done_when": focus.done_when,
                  "summary": qf.answer_summary(focus)} if focus else None,
        "current": _attempt_brief(current) if current else None,
        "running": [_attempt_brief(a) for a in view["running"]],
        "next": upcoming,
        "needs_you": view["needs_you"],
        "questions": [_question_brief(q, focus) for q in proj.ordered()],
        "counts": counts,
        "notes": top_plan._task_notes(proj.plan_path, ids + ["plan"]),
        "last_fail": top_plan._last_fail(proj.plan_path, ids + ["plan"]),
        "mirror_stale": render_root(proj) != proj.root_text,
        "errors": errors,
        "warnings": [],
        "verdict": "warn" if errors else "ok",
        "next_hint": hint,
    }


def _attempt_dict(attempt: qf.Attempt) -> dict[str, Any]:
    return {"id": attempt.id, "title": attempt.title, "result": attempt.result, "state": attempt.state,
            "gates": list(attempt.gates), "ev": list(attempt.ev), "no_artifact_reason": attempt.no_artifact_reason,
            "from": list(attempt.from_ids), "because": attempt.because, "supersedes": list(attempt.supersedes),
            "superseded_by": attempt.superseded_by, "invalid": attempt.invalid, "invalid_by": attempt.invalid_by,
            "reason": attempt.reason, "who": attempt.who, "usable": attempt.usable}


def question_view(project: str | Path, question_id: str, *, full: bool = False) -> dict[str, Any]:
    proj = load(project)
    question = proj.questions.get(question_id)
    if question is None:
        raise PlanError(f"没有问题 {question_id}（plan 看有哪些）")
    focus = focus_question(proj)
    attempts = question.attempts
    if not full:
        closed = [a for a in attempts if a.closed][-RECENT_DONE:]
        keep = {a.id for a in closed} | {a.id for a in attempts if not a.closed}
        attempts = [a for a in attempts if a.id in keep]
    notes = question.notes
    return {
        "schema_version": top_plan.SCHEMA_VERSION, "tool": "plan-question", "format": "qa",
        "revision": proj.revision, "project": str(proj.root_dir),
        "question": {**_question_brief(question, focus), "why": question.why, "done_when": question.done_when,
                     "answers": [_answer_dict(a) for a in question.answers],
                     "aliases": [{"old": old, "new": targets} for old, targets in question.aliases],
                     "file": str(question.path.relative_to(proj.root_dir)) if question.path else None},
        "attempts": [_attempt_dict(a) for a in attempts],
        "attempts_total": len(question.attempts),
        "attempts_truncated": len(attempts) < len(question.attempts),
        "notes_md": notes[:NOTES_LIMIT],
        "notes_truncated": len(notes) > NOTES_LIMIT,
    }


def resolve_alias(project: str | Path, old_id: str) -> dict[str, Any] | None:
    """Where an old ID (P5.38, P4) went: [(question, new IDs)] or None when unknown."""
    proj = load(project)
    hits = [{"question": q.id, "question_text": q.text, "new": targets}
            for q in proj.ordered() for old, targets in q.aliases if qf.alias_covers(old, old_id)]
    return {"old": old_id, "hits": hits} if hits else None


def list_items(project: str | Path, state_filter: str | None = None) -> dict[str, Any]:
    proj = load(project)
    items = [a for a in proj.all_attempts() if not state_filter or a.state == state_filter]
    return {"schema_version": top_plan.SCHEMA_VERSION, "tool": "plan-list", "format": "qa",
            "project": str(proj.root_dir), "items": [{**_attempt_dict(a), "phase": a.question} for a in items]}


# ---------- writing ----------

def _lock_path(plan_path: Path) -> Path:
    directory = Path(os.environ.get("TOP_LOCK_DIR") or (Path.home() / ".cache" / "top-plan-locks"))
    directory.mkdir(parents=True, exist_ok=True)
    return directory / (hashlib.sha1(str(plan_path.resolve()).encode("utf-8")).hexdigest()[:20] + ".lock")


@contextmanager
def project_lock(plan_path: Path) -> Generator[None, None, None]:
    with _lock_path(plan_path).open("a") as handle:
        deadline = time.monotonic() + LOCK_TIMEOUT_S
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() > deadline:
                    raise PlanConflict("另一个 plan 写入一直没结束，稍后重试") from None
                time.sleep(0.1)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    temp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.",
                                         suffix=".tmp", delete=False) as handle:
            temp = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
        temp = None
    finally:
        if temp is not None and temp.exists():
            temp.unlink()


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _clean(value: str, label: str, *, arrow: bool = False) -> str:
    value = " ".join(str(value or "").split())
    if not value:
        raise PlanError(f"{label}不能为空")
    if qf.META_SEP in value or "<!--" in value or "-->" in value or value.startswith("·") or value.endswith("·") \
            or " ·" in value or "· " in value:
        raise PlanError(f"{label}里不能有 ' · '（带空格的间隔号）或 '<!--' '-->'")
    if arrow and qf.ARROW.strip() in value:
        raise PlanError(f"{label}里不能有 “→”（它用来分开做了什么和结果）")
    return value


def _clean_list(values: list[str] | None, label: str) -> list[str]:
    return [_clean(v, label) for v in values or [] if str(v).strip()]


def _plan_item(attempt: qf.Attempt) -> PlanItem:
    return PlanItem(id=attempt.id, title=attempt.title, checked=attempt.closed, state=attempt.state, line_index=-1,
                    evidence=list(attempt.ev), gates=list(attempt.gates), reason=attempt.reason,
                    no_artifact_reason=attempt.no_artifact_reason, section=attempt.question)


class _Change:
    """What one mutation touched: question work files to rewrite and log lines to append."""

    def __init__(self) -> None:
        self.questions: set[str] = set()
        self.logs: list[tuple[str, Any]] = []     # ("line", body) or ("item", (action, PlanItem))
        self.result: dict[str, Any] = {}


def transact(project: str | Path, action: str, mutate: Callable[[QaProject, _Change], None], *,
             expect: str | None = None) -> dict[str, Any]:
    root_dir, plan_path = top_plan._plan_path(str(project))
    with project_lock(plan_path):
        root_text, files = qf.read_project(plan_path)
        proj = _build(root_dir, plan_path, root_text, files)
        if not qf.is_qa_text(root_text):
            raise PlanError("这不是问答格式的计划")
        if expect and expect != proj.revision:
            raise PlanConflict("计划刚被别处改过：重读后再试")
        lossy = [(c, m) for c, m in proj.parse_errors if c in LOSSY]
        if lossy:
            raise PlanError("计划有读不懂的地方，写入会丢内容，先修：" + "；".join(m for _, m in lossy[:4]))
        before = set(hard_errors(proj))
        if any(code == "TOP_VERSION_NEW" for code, _ in before):
            raise PlanError(f"计划版本高于本 skill 的 v{qf.PLAN_VERSION}；先更新 skill，不能降级写入")
        change = _Change()
        orphans = sorted((q for q in proj.questions if q not in proj.root.order), key=lambda q: int(q[1:]))
        if orphans:   # a work file written just before a crash: attach it at the end
            proj.root.order += orphans
            change.logs.append(("line", f"repair plan · 把漏列的 {','.join(orphans)} 接回问答目录末尾"))
        mutate(proj, change)
        added = [e for e in hard_errors(proj) if e not in before]
        if added:
            raise PlanError("这样改会让计划出错：" + "；".join(m for _, m in added[:4]))
        qdir = qf.questions_dir(plan_path)
        for qid in sorted(change.questions, key=lambda q: int(q[1:])):
            text = qf.render_question(proj.questions[qid])
            if files.get(f"{qid}.md") != text:
                atomic_write(qdir / f"{qid}.md", text)
        new_root = render_root(proj)
        if new_root != root_text:
            atomic_write(plan_path, new_root)
        logs = []
        for kind, payload in change.logs:
            if kind == "item":
                logs.append(top_plan._append_plan_log(plan_path, payload[0], payload[1]))
            else:
                logs.append(top_plan._append_log_line(plan_path, payload))
        revision = qf.revision(*qf.read_project(plan_path))
    result = {"schema_version": top_plan.SCHEMA_VERSION, "tool": f"plan-{action}", "format": "qa",
              "verdict": "ok", "task_plan": str(plan_path), "revision": revision, "log": logs[-1] if logs else None}
    result.update(change.result)
    return result


def _question(proj: QaProject, qid: str) -> qf.Question:
    if not qf.QUESTION_ID_RE.match(qid or ""):
        raise _unknown(proj, qid, f"{qid} 不是问题编号（Q<n>）")
    question = proj.questions.get(qid)
    if question is None:
        raise PlanError(f"没有问题 {qid}（plan 看有哪些）")
    return question


def _attempt(proj: QaProject, aid: str) -> qf.Attempt:
    if not qf.ATTEMPT_ID_RE.match(aid or ""):
        raise _unknown(proj, aid, f"{aid} 不是尝试编号（Q<n>.<k>）")
    attempt = proj.attempt(aid)
    if attempt is None:
        raise PlanError(f"没有 {aid} 这一步（plan {aid.split('.')[0]} 看有哪些）")
    return attempt


def _expand_ids(proj: QaProject, values: list[str] | None) -> list[str]:
    """`Q2.4,Q2.5` or `Q2.4..Q2.6` → explicit existing IDs (ranges stay inside one question)."""
    out: list[str] = []
    for value in values or []:
        for token in qf.split_ids(value):
            if ".." in token:
                start, end = token.split("..", 1)
                a, b = qf.ATTEMPT_ID_RE.match(start), qf.ATTEMPT_ID_RE.match(end)
                if not a or not b or a.group(1) != b.group(1):
                    raise PlanError(f"范围 {token} 要在同一个问题里，例如 Q2.4..Q2.6")
                question = _question(proj, f"Q{a.group(1)}")
                lo, hi = sorted((int(a.group(2)), int(b.group(2))))
                found = [x.id for x in question.attempts if lo <= x.number <= hi]
                if not found:
                    raise PlanError(f"范围 {token} 里没有尝试")
                out += [f for f in found if f not in out]
            else:
                if proj.attempt(token) is None and token not in proj.questions:
                    raise _unknown(proj, token, f"没有 {token}")
                if token not in out:
                    out.append(token)
    return out


def _clear_next_if(proj: QaProject, aid: str) -> None:
    if proj.root.next_id == aid:
        proj.root.next_id, proj.root.next_when = "", "now"


def _move_focus(proj: QaProject, qid: str) -> None:
    """Focus on `qid`; a next step that belonged to the old focus goes with it."""
    if proj.root.focus != qid:
        if not proj.root.next_id.startswith(qid + "."):
            proj.root.next_id = ""
        proj.root.next_text = ""
        if not proj.root.next_id:
            proj.root.next_when = "now"
    proj.root.focus = qid


def _drop_focus_if(proj: QaProject, qid: str) -> None:
    """The focus question is closed or dropped: no focus, and its next step goes too."""
    if proj.root.focus == qid:
        proj.root.focus, proj.root.next_text = "", ""
        if not proj.root.next_id or proj.root.next_id.startswith(qid + "."):
            proj.root.next_id, proj.root.next_when = "", "now"
    elif proj.root.next_id.startswith(qid + "."):
        proj.root.next_id, proj.root.next_when = "", "now"


def _after_index(proj: QaProject, after: str) -> int:
    _question(proj, after)
    if after not in proj.root.order:
        raise PlanError(f"{after} 不在问答目录里（plan check 看一下）")
    return proj.root.order.index(after) + 1


def set_goal(project: str, text: str, *, expect: str | None = None) -> dict[str, Any]:
    text = _clean(text, "目标")

    def mutate(proj: QaProject, change: _Change) -> None:
        proj.root.goal = text
        change.logs.append(("line", f"goal plan {text}"))
    return transact(project, "goal", mutate, expect=expect)


def ask(project: str, text: str, *, done_when: str | None = None, why: str | None = None,
        after: str | None = None, expect: str | None = None) -> dict[str, Any]:
    text = _clean(text, "问题", arrow=True)

    def mutate(proj: QaProject, change: _Change) -> None:
        numbers = [q.number for q in proj.questions.values()] + [int(x[1:]) for x in proj.root.order if x[1:].isdigit()]
        qid = f"Q{max(numbers, default=0) + 1}"
        question = qf.Question(id=qid, text=text, state="todo", created=_today(),
                               why=_clean(why, "为什么问") if why else "",
                               done_when=_clean(done_when, "怎样算答清") if done_when else "")
        question.path = qf.questions_dir(proj.plan_path) / f"{qid}.md"
        proj.questions[qid] = question
        if after:
            proj.root.order.insert(_after_index(proj, after), qid)
        else:
            proj.root.order.append(qid)
        if not proj.root.focus or focus_question(proj) is None:
            proj.root.focus = qid
        change.questions.add(qid)
        change.logs.append(("line", f"ask {qid} {text}"))
        change.result.update(item_id=qid, focus=proj.root.focus)
    return transact(project, "ask", mutate, expect=expect)


def answer(project: str, qid: str, text: str, *, evidence: list[str], because: str | None = None,
           keep_open: bool = False, cond: str | None = None, expect: str | None = None) -> dict[str, Any]:
    text = _clean(text, "答案")
    evidence = _clean_list(evidence, "证据")
    if not evidence:
        raise PlanError("答案要带证据：--ev <尝试编号 / finding:… / 路径 / 提交>")

    def mutate(proj: QaProject, change: _Change) -> None:
        question = _question(proj, qid)
        if question.state == "dropped":
            raise PlanError(f"{qid} 已经放弃了")
        running = [a.id for a in question.attempts if a.state == "in_progress"]
        if running and not keep_open:
            raise PlanError(f"{qid} 还有进行中的 {', '.join(running)}：先 plan done / plan cancel 它，"
                            "或者这是阶段性判断就加 --keep-open")
        for old in question.answers:
            if old.status == "current":
                old.status = "superseded"
        rev = max((a.rev for a in question.answers), default=0) + 1
        question.answers.append(qf.Answer(rev=rev, text=text, date=_today(), ev=evidence,
                                          because=_clean(because, "because") if because else "",
                                          cond=_clean(cond, "适用条件") if cond else ""))
        question.answer_rev = rev
        question.review = question.review_by = ""
        if keep_open:
            question.state = "waiting" if question.state == "waiting" else "active"
        else:
            question.state = "closed"
            question.wait = question.wait_who = ""
            _drop_focus_if(proj, qid)
        open_attempts = [a.id for a in question.attempts if not a.closed]
        change.questions.add(qid)
        change.logs.append(("line", f"answer {qid} r{rev} {text} · ev={','.join(evidence)}"))
        change.result.update(item_id=qid, rev=rev, open_attempts=open_attempts if not keep_open else [],
                             focus_cleared=not keep_open and not proj.root.focus)
    return transact(project, "answer", mutate, expect=expect)


def reopen_question(project: str, qid: str, reason: str, *, because: str | None = None,
                    invalid: list[str] | None = None, expect: str | None = None) -> dict[str, Any]:
    reason = _clean(reason, "原因")

    def mutate(proj: QaProject, change: _Change) -> None:
        question = _question(proj, qid)
        by = _clean(because, "because") if because else ""
        withdrawn = question.current_answer
        if withdrawn is not None:
            withdrawn.status, withdrawn.reason, withdrawn.by = "withdrawn", reason, by
        question.answer_rev = None
        question.state = "active"
        question.wait = question.wait_who = ""
        change.questions.add(qid)
        marked: list[str] = []
        for aid in _expand_ids(proj, invalid):
            attempt = _attempt(proj, aid)
            if attempt.state != "done":
                raise PlanError(f"{aid} 还没做完，不用标作废（plan cancel 它）")
            attempt.invalid, attempt.invalid_by = reason, by or qid
            change.questions.add(attempt.question)
            marked.append(aid)
        # other questions whose current answer cites a withdrawn result or this question
        cited = set(marked) | {qid} | {a.id for a in question.attempts}
        affected = [{"id": q.id, "text": q.text} for q in proj.ordered() if q.id != qid and q.current_answer
                    and (set(q.current_answer.ev) & cited or q.current_answer.because in cited)]
        change.logs.append(("line", f"reopen {qid} {reason}" + (f" · because={by}" if by else "")
                            + (f" · invalid={','.join(marked)}" if marked else "")))
        change.result.update(item_id=qid, withdrawn=withdrawn.rev if withdrawn else None, invalid=marked,
                             affected=affected)
    return transact(project, "reopen", mutate, expect=expect)


def flag(project: str, qid: str, reason: str | None, *, because: str | None = None, clear: bool = False,
         expect: str | None = None) -> dict[str, Any]:
    reason = "" if clear else _clean(reason or "", "原因")

    def mutate(proj: QaProject, change: _Change) -> None:
        question = _question(proj, qid)
        question.review = reason
        question.review_by = "" if clear else (_clean(because, "because") if because else "")
        change.questions.add(qid)
        change.logs.append(("line", f"{'unflag' if clear else 'flag'} {qid} {reason or '已复核'}"))
        change.result.update(item_id=qid)
    return transact(project, "flag", mutate, expect=expect)


def wait(project: str, qid: str, reason: str | None, *, you: bool = False, clear: bool = False,
         expect: str | None = None) -> dict[str, Any]:
    reason = "" if clear else _clean(reason or "", "等什么")

    def mutate(proj: QaProject, change: _Change) -> None:
        question = _question(proj, qid)
        if question.state in ("closed", "dropped") and not clear:
            raise PlanError(f"{qid} 已经{DONE_TEXT[question.state]}，不用等")
        if clear:
            if question.state == "waiting":
                question.state = "active"
            question.wait = question.wait_who = ""
        else:
            question.state, question.wait, question.wait_who = "waiting", reason, "you" if you else ""
        change.questions.add(qid)
        change.logs.append(("line", f"{'unwait' if clear else 'wait'} {qid} {reason or '不再等待'}"))
        change.result.update(item_id=qid)
    return transact(project, "wait", mutate, expect=expect)


def drop(project: str, qid: str, reason: str, *, expect: str | None = None) -> dict[str, Any]:
    reason = _clean(reason, "原因")

    def mutate(proj: QaProject, change: _Change) -> None:
        question = _question(proj, qid)
        question.state = "dropped"
        question.wait = question.wait_who = ""
        cancelled = []
        for attempt in question.attempts:
            if not attempt.closed:
                attempt.state, attempt.reason, attempt.who = "cancelled", f"问题放弃：{reason}", ""
                cancelled.append(attempt.id)
                _clear_next_if(proj, attempt.id)
        _drop_focus_if(proj, qid)
        change.questions.add(qid)
        change.logs.append(("line", f"drop {qid} {reason}"))
        change.result.update(item_id=qid, cancelled=cancelled)
    return transact(project, "drop", mutate, expect=expect)


def rename(project: str, target: str, text: str, *, expect: str | None = None) -> dict[str, Any]:
    def mutate(proj: QaProject, change: _Change) -> None:
        if qf.QUESTION_ID_RE.match(target):
            _question(proj, target).text = _clean(text, "问题", arrow=True)
            change.questions.add(target)
        else:
            attempt = _attempt(proj, target)
            attempt.title = _clean(text, "这一步", arrow=True)
            change.questions.add(attempt.question)
        change.logs.append(("line", f"rename {target} {text}"))
        change.result.update(item_id=target)
    return transact(project, "rename", mutate, expect=expect)


def move(project: str, qid: str, *, after: str | None, expect: str | None = None) -> dict[str, Any]:
    def mutate(proj: QaProject, change: _Change) -> None:
        _question(proj, qid)
        order = [q for q in proj.root.order if q != qid]
        if after:
            if after == qid:
                raise PlanError("不能放在自己后面")
            _question(proj, after)
            if after not in order:
                raise PlanError(f"{after} 不在问答目录里（plan check 看一下）")
            order.insert(order.index(after) + 1, qid)
        else:
            order.insert(0, qid)
        proj.root.order = order
        change.logs.append(("line", f"move {qid} after={after or '最前'}"))
        change.result.update(item_id=qid, order=order)
    return transact(project, "move", mutate, expect=expect)


def add(project: str, title: str, *, to: str | None = None, gates: list[str] | None = None,
        from_ids: list[str] | None = None, because: str | None = None, expect: str | None = None) -> dict[str, Any]:
    title = _clean(title, "这一步", arrow=True)
    gates = _clean_list(gates, "验收")

    def mutate(proj: QaProject, change: _Change) -> None:
        current_focus = focus_question(proj)
        target = to or (current_focus.id if current_focus else "")
        if not target:
            raise PlanError("不知道加到哪个问题：用 --to Q<n>，或先 plan focus Q<n>")
        question = _question(proj, target)
        if question.state == "dropped":
            raise PlanError(f"{target} 已经放弃了：要接着弄就另开一个问题")
        attempt = qf.Attempt(id=f"{target}.{question.next_attempt_number()}", title=title, gates=gates,
                             from_ids=_expand_ids(proj, from_ids),
                             because=_clean(because, "because") if because else "")
        question.attempts.append(attempt)
        change.questions.add(target)
        change.result.update(item_id=attempt.id, question=target)
    return transact(project, "add", mutate, expect=expect)


def start(project: str, aid: str, *, expect: str | None = None) -> dict[str, Any]:
    def mutate(proj: QaProject, change: _Change) -> None:
        attempt = _attempt(proj, aid)
        if attempt.state not in ("pending", "blocked"):
            raise PlanError(f"{aid} 现在是 {attempt.state}，只有待办或卡住的步骤能开始")
        question = proj.questions[attempt.question]
        if question.state == "dropped":
            raise PlanError(f"{question.id} 已经放弃了：要接着弄就另开一个问题")
        # an answered question can take more work (an extra check): it is active again, the answer stays
        attempt.state, attempt.reason, attempt.who = "in_progress", "", ""
        question.state = "active"
        question.wait = question.wait_who = ""
        _move_focus(proj, question.id)
        _clear_next_if(proj, aid)
        change.questions.add(question.id)
        change.logs.append(("item", ("start", _plan_item(attempt))))
        change.result.update(item_id=aid, focus=question.id)
    return transact(project, "start", mutate, expect=expect)


def done(project: str, aid: str, result_text: str, *, evidence: list[str] | None = None,
         no_artifact: str | None = None, supersedes: list[str] | None = None,
         expect: str | None = None) -> dict[str, Any]:
    result_text = _clean(result_text, "结果")
    evidence = _clean_list(evidence, "证据")
    if not evidence and not (no_artifact or "").strip():
        raise PlanError("完成要给证据：--ev \"证据\"；没有产物就 --no-artifact \"原因\"")

    def mutate(proj: QaProject, change: _Change) -> None:
        attempt = _attempt(proj, aid)
        if attempt.state not in ("pending", "in_progress", "blocked"):
            raise PlanError(f"{aid} 已经{'做完' if attempt.state == 'done' else '取消'}了，结果不改写：新加一步 plan add … --from {aid}")
        replaced = _expand_ids(proj, supersedes)
        for old_id in replaced:
            old = _attempt(proj, old_id)
            if old_id == aid or old.state != "done":
                raise PlanError(f"{old_id} 不是做完的旧结果，不能被替代")
            change.questions.add(old.question)
        attempt.state, attempt.result, attempt.ev = "done", result_text, evidence
        attempt.no_artifact_reason = "" if evidence else _clean(no_artifact or "", "无产物原因")
        attempt.reason = attempt.who = ""
        attempt.supersedes = replaced
        _derive_all(proj.questions)
        _clear_next_if(proj, aid)
        change.questions.add(attempt.question)
        change.logs.append(("item", ("complete", _plan_item(attempt))))
        change.result.update(item_id=aid, question=attempt.question, supersedes=replaced)
    return transact(project, "done", mutate, expect=expect)


def block(project: str, aid: str, reason: str, *, you: bool = False, expect: str | None = None) -> dict[str, Any]:
    reason = _clean(reason, "原因")

    def mutate(proj: QaProject, change: _Change) -> None:
        attempt = _attempt(proj, aid)
        if attempt.closed:
            raise PlanError(f"{aid} 已经关了")
        attempt.state, attempt.reason, attempt.who = "blocked", reason, "you" if you else ""
        change.questions.add(attempt.question)
        change.logs.append(("item", ("block", _plan_item(attempt))))
        change.result.update(item_id=aid)
    return transact(project, "block", mutate, expect=expect)


def cancel(project: str, aid: str, reason: str, *, expect: str | None = None) -> dict[str, Any]:
    reason = _clean(reason, "原因")

    def mutate(proj: QaProject, change: _Change) -> None:
        attempt = _attempt(proj, aid)
        if attempt.closed:
            raise PlanError(f"{aid} 已经关了")
        attempt.state, attempt.reason, attempt.who = "cancelled", reason, ""
        _clear_next_if(proj, aid)
        change.questions.add(attempt.question)
        change.logs.append(("item", ("cancel", _plan_item(attempt))))
        change.result.update(item_id=aid)
    return transact(project, "cancel", mutate, expect=expect)


def reopen_attempt(project: str, aid: str, *, expect: str | None = None) -> dict[str, Any]:
    def mutate(proj: QaProject, change: _Change) -> None:
        attempt = _attempt(proj, aid)
        if attempt.state == "done":
            raise PlanError(f"{aid} 做完的结果不改写：要重来就 plan add \"…\" --from {aid}；结果错了就 "
                            f"plan reopen {attempt.question} \"原因\" --invalid {aid}")
        if attempt.state not in ("blocked", "cancelled"):
            raise PlanError(f"{aid} 现在是 {attempt.state}，不用重开")
        attempt.state, attempt.reason, attempt.who = "pending", "", ""
        change.questions.add(attempt.question)
        change.logs.append(("item", ("reopen", _plan_item(attempt))))
        change.result.update(item_id=aid)
    return transact(project, "reopen", mutate, expect=expect)


def focus(project: str, qid: str | None, *, next_step: str | None = None, after: bool = False,
          expect: str | None = None) -> dict[str, Any]:
    def mutate(proj: QaProject, change: _Change) -> None:
        if qid:
            question = _question(proj, qid)
            if question.state == "dropped":
                raise PlanError(f"{qid} 已经放弃了：要接着弄就另开一个问题")
            if question.state == "closed":
                question.state = "active"   # more work on an answered question; the answer stays current
                change.questions.add(qid)
            _move_focus(proj, qid)
        if next_step is not None:
            value = " ".join(next_step.split())
            if not value:
                proj.root.next_id = proj.root.next_text = ""
            elif qf.ATTEMPT_ID_RE.match(value):
                attempt = _attempt(proj, value)
                if attempt.closed:
                    raise PlanError(f"{value} 已经关了，不能当下一步")
                proj.root.next_id, proj.root.next_text = value, ""
            else:
                proj.root.next_id, proj.root.next_text = "", _clean(value, "下一步")
            proj.root.next_when = "after" if after and value else "now"
        change.logs.append(("line", f"focus {proj.root.focus or '-'} · next={proj.root.next_id or proj.root.next_text or '-'}"))
        change.result.update(item_id=proj.root.focus or None, next=proj.root.next_id or proj.root.next_text or None)
    return transact(project, "focus", mutate, expect=expect)


def note(project: str, text: str, *, on: str | None = None, kind: str = "progress") -> dict[str, Any]:
    """One line in today's plan log; `on` is a question or an attempt (default: the current one)."""
    if kind not in top_plan.NOTE_KINDS:
        raise PlanError(f"kind must be one of {', '.join(top_plan.NOTE_KINDS)}")
    text = " ".join(str(text or "").split())
    if not text or qf.META_SEP in text:
        raise PlanError("笔记不能为空，也不能有 ' · '")
    proj = load(project)
    if on:
        if on not in _known_ids(proj):
            raise _unknown(proj, on, f"没有 {on}")
        target = on
    else:
        view = now_view(proj)
        target = (view["current"].id if view["current"] else view["focus"].id if view["focus"] else "plan")
    result: dict[str, Any] = {"schema_version": top_plan.SCHEMA_VERSION, "tool": "plan-note", "format": "qa",
                              "verdict": "ok", "item_id": target, "kind": kind,
                              "log": top_plan._append_log_line(proj.plan_path, f"note:{kind} {target} {text}")}
    if len(text) > top_plan.NOTE_CHARS_BUDGET:
        result.update(verdict="warn", next_hint="下次只写一句话结论+证据路径；长复盘写进 _logs/<date>-<topic>.md 再链接")
    if kind == "fail" and target != "plan":
        count = top_plan._fail_count(proj.plan_path, target)
        result["fail_count"] = count
        result["escalate"] = count >= top_plan.FAIL_ESCALATE_AT
        if result["escalate"]:
            result.update(verdict="warn", next_hint=f"{target} 已失败 {count} 次：停下来找用户，列出试过的三种做法和各自结果")
    return result


def upgrade(project: str, *, apply: bool = False, expect: str | None = None) -> dict[str, Any]:
    """Check and, when safe, advance the plan's `top-version`.

    A missing version is not stamped blindly: the plan must parse without hard errors.
    Older versions need a registered migration; newer ones are never downgraded.
    """
    proj = load(project)
    current = qf.PLAN_VERSION
    version = proj.root.version
    errors = [{"code": c, "message": m} for c, m in hard_errors(proj)]
    base = {"schema_version": top_plan.SCHEMA_VERSION, "tool": "plan-upgrade", "format": "qa",
            "project": str(proj.root_dir), "task_plan": str(proj.plan_path.relative_to(proj.root_dir)),
            "from_version": version, "to_version": current, "errors": errors}
    if version is not None and version > current:
        base.update(verdict="block", action="none",
                    next_hint=f"计划来自更高版本 v{version}；先更新 skill，不能降级")
        return base
    if version == current:
        if errors:
            base.update(verdict="block", action="none",
                        next_hint=f"版本已是最新 v{current}，但计划有错误：先 plan check 修内容")
        else:
            base.update(verdict="ok", action="none", next_hint=f"计划已是最新版本 v{current}")
        return base
    if version is not None:
        base.update(verdict="block", action="migrate",
                    next_hint=f"没有 v{version}→v{current} 的迁移器；先更新 skill 或按迁移文档处理")
        return base
    if errors:
        base.update(verdict="block", action="inspect",
                    next_hint="计划没有版本号且内容有错误：先 plan check 修好，再 plan upgrade --apply")
        return base
    base.update(verdict="warn", action="stamp",
                next_hint=f"内容检查通过；plan upgrade --apply 标记为 v{current}")
    if not apply:
        return base

    def mutate(p: QaProject, change: _Change) -> None:
        if p.root.version is not None:
            raise PlanConflict("计划在检查之后已有版本号：重新运行 plan upgrade")
        current_errors = hard_errors(p)
        if current_errors:
            raise PlanError("计划内容有错误，不能标记版本：" + "；".join(m for _, m in current_errors[:4]))
        p.root.version = current
        change.logs.append(("line", f"upgrade plan · top-version missing → {current}"))
        change.result.update(action="stamp", from_version=None, to_version=current)

    result = transact(project, "upgrade", mutate, expect=expect)
    result.update(verdict="ok", next_hint=f"已标记为当前版本 v{current}")
    result["errors"] = []
    return result


def commit_done(project: str, aid: str) -> dict[str, Any]:
    """`plan done --commit`: the attempt's evidence paths + plan files, `Task: <ID>` trailer."""
    return top_plan._complete_git(str(project), aid, commit=True, merge=False)


# ---------- new project ----------

QA_SKELETON = """# {name} — 计划
<!-- plan-format: qa · top-version={version} -->

## 目标

{goal}

## 现在

<!-- plan 命令自动生成，不要手改 -->

## 问答

<!-- 问题的顺序由这里决定；摘要由 plan 命令从 _questions/ 生成，不要手改 -->
"""


def init(project: str, goal: str) -> dict[str, Any]:
    """Start an empty question-and-answer plan (only when there is no plan with content yet)."""
    root_dir, plan_path = top_plan._plan_path(str(project))
    if plan_path.is_file() and plan_path.read_text(encoding="utf-8", errors="replace").strip():
        raise PlanError(f"已经有计划了：{plan_path}（旧计划要改写成问答格式用 plan rewrite 草稿.md --to qa）")
    goal = _clean(goal, "目标")
    with project_lock(plan_path):
        atomic_write(plan_path, QA_SKELETON.format(name=root_dir.name, goal=goal, version=qf.PLAN_VERSION))
        proj = load(root_dir)
        atomic_write(plan_path, render_root(proj))
    return {"schema_version": top_plan.SCHEMA_VERSION, "tool": "plan-init", "format": "qa", "verdict": "ok",
            "task_plan": str(plan_path), "next_hint": "plan ask \"第一个要弄清的问题？\" --done-when \"怎样算答清\""}


def known_id(value: str) -> bool:
    return bool(re.fullmatch(r"Q\d+(?:\.\d+)?", value or ""))
