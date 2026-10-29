#!/usr/bin/env python3
"""Question-and-answer plan format (`plan-format: qa`): parse and render, no side effects.

A project is a list of questions. The root plan `_task_plan.md` owns the goal, the
logical order of the questions, the focus and the next step; the per-question summary
in it is a mirror rebuilt on every write. Each question has a work file
`_questions/Q<n>.md` that owns its wording, why/done-when, state, answer revisions
(append-only) and attempts (append-only; a sealed result is never rewritten).

This module only depends on the standard library so the card website and the git
hooks can load it by file path. Spec and writing rules: references/qa-plan.md.

The root header carries `top-version=<n>` when known. `PLAN_VERSION` is the current
structure version; upgrades only move forward and require an explicit `plan upgrade`.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

QA_MARK_RE = re.compile(r"^<!--\s*plan-format:\s*qa\b(.*?)-->\s*$")
PLAN_VERSION = 1  # bump only when the plan structure needs a migration; plans never downgrade
QUESTION_ID_RE = re.compile(r"^Q(\d+)$")
ATTEMPT_ID_RE = re.compile(r"^Q(\d+)\.(\d+)$")
QA_ID_RE = re.compile(r"^Q\d+(?:\.\d+)?$")
QUESTIONS_DIR = "_questions"
QUESTION_STATES = ("todo", "active", "waiting", "closed", "dropped")
ATTEMPT_STATES = ("pending", "in_progress", "blocked", "done", "cancelled")
ANSWER_STATUSES = ("current", "superseded", "withdrawn")
NEXT_WHEN = ("now", "after")
ARROW = " → "
META_SEP = " · "
NOW_NOTE = "<!-- plan 命令自动生成，不要手改 -->"
ORDER_NOTE = "<!-- 问题的顺序由这里决定；摘要由 plan 命令从 _questions/ 生成，不要手改 -->"
ANSWERS_NOTE = "<!-- plan 命令维护；只追加 -->"
ATTEMPTS_NOTE = "<!-- plan 命令维护；做完的结果不改写 -->"
ALIASES_NOTE = "<!-- 迁移生成：旧 ID → 新 ID；“历史”表示没有新对应 -->"
HISTORY_TARGET = "历史"
MARKS = {"dropped": "✕", "waiting": "⏸", "withdrawn": "↺", "closed": "✔", "active": "▶", "todo": "○"}
STATE_TEXT = {"todo": "未开始", "active": "在弄", "waiting": "等待", "closed": "已答清", "dropped": "不弄了"}

_ATTEMPT_LINE_RE = re.compile(r"^\s*[-*]\s+\[([ xX])\]\s+(Q\d+\.\d+)\s+(.*?)\s*(?:<!--(.*)-->)?\s*$")
_ANSWER_LINE_RE = re.compile(r"^\s*[-*]\s+r(\d+)\s+(.*?)\s*(?:<!--(.*)-->)?\s*$")
_ALIAS_LINE_RE = re.compile(r"^\s*[-*]\s+(\S+)\s+→\s+(.+?)\s*$")
_ROOT_QUESTION_RE = re.compile(r"^###\s+(.*?)\s*<!--(.*)-->\s*$")
_WORK_HEADER_RE = re.compile(r"^#\s+(Q\d+)\s+(.*?)\s*$")
_COMMENT_ONLY_RE = re.compile(r"^\s*<!--.*-->\s*$")
_TRAILING_MARK_RE = re.compile(r"\s*[✔▶⏸↺✕○⚠]+\s*$")

WORK_SECTIONS = ("为什么问", "怎样算答清", "答案", "尝试", "旧编号")
NOTES_SECTION = "笔记"
ROOT_SECTIONS = ("目标", "现在", "问答")


@dataclass
class Answer:
    rev: int
    text: str
    date: str = ""
    ev: list[str] = field(default_factory=list)
    because: str = ""
    status: str = "current"
    reason: str = ""          # why it was withdrawn
    by: str = ""              # what withdrew it (a step, question or finding)
    cond: str = ""            # optional: under which conditions the answer holds
    unknown: list[str] = field(default_factory=list)


@dataclass
class Attempt:
    id: str
    title: str
    result: str = ""
    state: str = "pending"
    gates: list[str] = field(default_factory=list)
    ev: list[str] = field(default_factory=list)
    no_artifact_reason: str = ""
    from_ids: list[str] = field(default_factory=list)
    because: str = ""
    supersedes: list[str] = field(default_factory=list)
    invalid: str = ""
    invalid_by: str = ""
    reason: str = ""          # blocked / cancelled: why
    who: str = ""             # "you" when blocked on the user
    superseded_by: str = ""   # derived, never written
    unknown: list[str] = field(default_factory=list)

    @property
    def question(self) -> str:
        return self.id.split(".", 1)[0]

    @property
    def number(self) -> int:
        return int(self.id.split(".", 1)[1])

    @property
    def closed(self) -> bool:
        return self.state in ("done", "cancelled")

    @property
    def usable(self) -> bool:
        """A done result that still counts: not marked invalid, not replaced."""
        return self.state == "done" and not self.invalid and not self.superseded_by


@dataclass
class Question:
    id: str
    text: str
    state: str = "todo"
    answer_rev: int | None = None
    review: str = ""
    review_by: str = ""
    wait: str = ""
    wait_who: str = ""
    created: str = ""
    why: str = ""
    done_when: str = ""
    answers: list[Answer] = field(default_factory=list)
    attempts: list[Attempt] = field(default_factory=list)
    aliases: list[tuple[str, list[str]]] = field(default_factory=list)
    notes: str = ""
    path: Path | None = None
    errors: list[tuple[str, str]] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)

    @property
    def number(self) -> int:
        return int(self.id[1:])

    @property
    def current_answer(self) -> Answer | None:
        if self.answer_rev is None:
            return None
        return next((a for a in self.answers if a.rev == self.answer_rev and a.status == "current"), None)

    @property
    def withdrawn_answer(self) -> Answer | None:
        """The latest withdrawn answer, when there is no current one (shown as ↺)."""
        if self.current_answer is not None:
            return None
        withdrawn = [a for a in self.answers if a.status == "withdrawn"]
        return max(withdrawn, key=lambda a: a.rev) if withdrawn else None

    @property
    def mark(self) -> str:
        if self.state == "dropped":
            return MARKS["dropped"]
        if self.state == "waiting":
            return MARKS["waiting"]
        if self.withdrawn_answer is not None:
            return MARKS["withdrawn"]
        if self.state == "closed":
            return MARKS["closed"]
        if self.state == "active":
            return MARKS["active"]
        return MARKS["todo"]

    def attempt(self, attempt_id: str) -> Attempt | None:
        return next((a for a in self.attempts if a.id == attempt_id), None)

    def next_attempt_number(self) -> int:
        used = [a.number for a in self.attempts]
        for _, targets in self.aliases:
            for target in targets:
                match = ATTEMPT_ID_RE.match(target)
                if match and f"Q{match.group(1)}" == self.id:
                    used.append(int(match.group(2)))
        return max(used, default=0) + 1


@dataclass
class QaRoot:
    title: str
    version: int | None = None
    goal: str = ""
    focus: str = ""
    next_id: str = ""
    next_text: str = ""
    next_when: str = "now"
    order: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)      # other `## ` sections, verbatim
    errors: list[tuple[str, str]] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)


# ---------- metadata ----------

def parse_meta(text: str) -> tuple[list[tuple[str, str]], list[str]]:
    """`k=v · k=v` → ([(k, v)], unknown segments). Values never contain ' · '."""
    pairs: list[tuple[str, str]] = []
    unknown: list[str] = []
    for segment in (text or "").split(META_SEP):
        segment = segment.strip()
        if not segment:
            continue
        if "=" not in segment:
            unknown.append(segment)
            continue
        key, value = segment.split("=", 1)
        pairs.append((key.strip().lower(), value.strip()))
    return pairs, unknown


def render_meta(pairs: list[tuple[str, str]]) -> str:
    kept = [f"{k}={v}" for k, v in pairs if v not in (None, "")]
    return f"<!-- {META_SEP.join(kept)} -->" if kept else ""


def split_ids(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,，、\s]+", value or "") if part.strip()]


def alias_covers(alias: str, old_id: str) -> bool:
    """`P5.38` matches itself; `P5.*` matches P5 and everything under it."""
    if alias.endswith(".*"):
        return old_id == alias[:-2] or old_id.startswith(alias[:-1])
    return alias == old_id


def is_qa_text(text: str) -> bool:
    for line in text.splitlines()[:6]:
        if QA_MARK_RE.match(line.strip()):
            return True
    return False


def one_line(text: str) -> str:
    return " ".join(str(text or "").split())


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------- sections ----------

def _sections(lines: list[str], start: int, end: int) -> dict[str, list[str]]:
    """`## name` → body lines (without the heading), for lines[start:end]."""
    out: dict[str, list[str]] = {}
    name = None
    for line in lines[start:end]:
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match and not line.startswith("###"):
            name = match.group(1)
            out.setdefault(name, [])
            continue
        if name is not None:
            out[name].append(line)
    return out


WHY_PLACEHOLDER = "（待补：这个问题和目标的关系）"
DONE_WHEN_PLACEHOLDER = "（待补：一句话的验收）"
PLACEHOLDERS = (WHY_PLACEHOLDER, DONE_WHEN_PLACEHOLDER)


def _prose(body: list[str]) -> str:
    kept = [line.rstrip() for line in body if not _COMMENT_ONLY_RE.match(line)]
    while kept and not kept[0].strip():
        kept.pop(0)
    while kept and not kept[-1].strip():
        kept.pop()
    text = "\n".join(kept)
    return "" if text.strip() in PLACEHOLDERS else text   # the untouched template placeholder is not content


# ---------- work file ----------

def parse_attempt_line(line: str) -> Attempt | None:
    match = _ATTEMPT_LINE_RE.match(line)
    if not match:
        return None
    checked, attempt_id, body, meta = match.group(1).lower() == "x", match.group(2), match.group(3), match.group(4)
    title, result = (body.split(ARROW, 1) + [""])[:2] if ARROW in body else (body, "")
    pairs, unknown = parse_meta(meta or "")
    attempt = Attempt(id=attempt_id, title=title.strip(), result=result.strip(), unknown=unknown)
    state = ""
    for key, value in pairs:
        if key == "state":
            state = value
        elif key == "gate":
            attempt.gates.append(value)
        elif key == "ev":
            attempt.ev.append(value)
        elif key == "no_artifact_reason":
            attempt.no_artifact_reason = value
        elif key == "from":
            attempt.from_ids += split_ids(value)
        elif key == "because":
            attempt.because = value
        elif key == "supersedes":
            attempt.supersedes += split_ids(value)
        elif key == "invalid":
            attempt.invalid = value
        elif key == "invalid_by":
            attempt.invalid_by = value
        elif key == "reason":
            attempt.reason = value
        elif key == "who":
            attempt.who = value
        else:
            attempt.unknown.append(f"{key}={value}")
    attempt.state = state or ("done" if checked else "pending")
    return attempt


def render_attempt(attempt: Attempt) -> str:
    checked = "x" if attempt.closed else " "
    body = attempt.title + (f"{ARROW}{attempt.result}" if attempt.result else "")
    pairs: list[tuple[str, str]] = []
    if attempt.state not in ("pending", "done"):
        pairs.append(("state", attempt.state))
    pairs += [("gate", g) for g in attempt.gates]
    pairs += [("ev", e) for e in attempt.ev]
    pairs.append(("from", ",".join(attempt.from_ids)))
    pairs.append(("because", attempt.because))
    pairs.append(("supersedes", ",".join(attempt.supersedes)))
    pairs.append(("invalid", attempt.invalid))
    pairs.append(("invalid_by", attempt.invalid_by))
    pairs.append(("who", attempt.who))
    pairs.append(("reason", attempt.reason))
    pairs.append(("no_artifact_reason", attempt.no_artifact_reason))
    meta = render_meta(pairs)
    return f"- [{checked}] {attempt.id} {body}" + (f" {meta}" if meta else "")


def parse_answer_line(line: str) -> Answer | None:
    match = _ANSWER_LINE_RE.match(line)
    if not match:
        return None
    pairs, unknown = parse_meta(match.group(3) or "")
    answer = Answer(rev=int(match.group(1)), text=match.group(2).strip(), unknown=unknown)
    for key, value in pairs:
        if key == "ev":
            answer.ev.append(value)
        elif key in ("date", "because", "status", "reason", "by", "cond"):
            setattr(answer, key, value)
        else:
            answer.unknown.append(f"{key}={value}")
    return answer


def render_answer(answer: Answer) -> str:
    pairs = [("date", answer.date), *[("ev", e) for e in answer.ev], ("cond", answer.cond),
             ("because", answer.because), ("status", answer.status), ("reason", answer.reason), ("by", answer.by)]
    return f"- r{answer.rev} {answer.text} {render_meta(pairs)}".rstrip()


def parse_question_text(text: str, path: Path | None = None) -> Question:
    lines = text.splitlines()
    question = Question(id="", text="", path=path)
    header = next((i for i, line in enumerate(lines) if line.startswith("# ")), None)
    match = _WORK_HEADER_RE.match(lines[header]) if header is not None else None
    if match is None:
        question.errors.append(("QA_WORK_HEADER", f"{path or '工作本'}：第一行要是 `# Q<n> 问题`"))
        return question
    assert header is not None
    question.id, question.text = match.group(1), _TRAILING_MARK_RE.sub("", match.group(2)).strip()
    notes_at = next((i for i, line in enumerate(lines) if re.match(rf"^##\s+{NOTES_SECTION}\s*$", line)), len(lines))
    meta_line = next((line for line in lines[header + 1:notes_at] if line.strip()), "")
    meta_match = re.match(r"^\s*<!--(.*)-->\s*$", meta_line)
    if meta_match:
        pairs, question.unknown = parse_meta(meta_match.group(1))
        for key, value in pairs:
            if key == "id":
                if value != question.id:
                    question.errors.append(("QA_ID_MISMATCH", f"{question.id}：头部注释写的是 id={value}"))
            elif key == "state":
                question.state = value
            elif key == "answer":
                rev = value[1:] if value.startswith("r") else value
                question.answer_rev = int(rev) if rev.isdigit() else None
                if value and not rev.isdigit():
                    question.errors.append(("QA_ANSWER_POINTER", f"{question.id}：answer={value} 不是 r<n>"))
            elif key in ("review", "review_by", "wait", "wait_who", "created"):
                setattr(question, key, value)
            else:
                question.unknown.append(f"{key}={value}")
    known = "|".join(re.escape(name) for name in WORK_SECTIONS)
    for line in lines[notes_at + 1:]:
        if re.match(rf"^##\s+({known})\s*$", line):
            question.errors.append(("QA_SECTION", f"{question.id}：`## {NOTES_SECTION}` 必须是最后一节，"
                                                  f"它后面又出现了 `{line.strip()}`（挪到笔记前面）"))
    for line in lines[header + 1:notes_at]:
        if line.startswith("## "):
            break
        if line.strip() and not _COMMENT_ONLY_RE.match(line):
            question.errors.append(("QA_UNKNOWN", f"{question.id}：标题和第一节之间有文字，写入会丢（挪进 ## {NOTES_SECTION}）："
                                                  f"{line.strip()[:40]}"))
            break
    sections = _sections(lines, header + 1, notes_at)
    question.why = _prose(sections.get("为什么问", []))
    question.done_when = _prose(sections.get("怎样算答清", []))
    for line in sections.get("答案", []):
        if _COMMENT_ONLY_RE.match(line) or not line.strip():
            continue
        answer = parse_answer_line(line)
        if answer is None:
            question.errors.append(("QA_LINE", f"{question.id} 答案节读不懂：{line.strip()[:60]}"))
        else:
            question.answers.append(answer)
    for line in sections.get("尝试", []):
        if _COMMENT_ONLY_RE.match(line) or not line.strip():
            continue
        attempt = parse_attempt_line(line)
        if attempt is None:
            question.errors.append(("QA_LINE", f"{question.id} 尝试节读不懂：{line.strip()[:60]}"))
        else:
            question.attempts.append(attempt)
    for line in sections.get("旧编号", []):
        if _COMMENT_ONLY_RE.match(line) or not line.strip():
            continue
        alias = _ALIAS_LINE_RE.match(line)
        if alias is None:
            question.errors.append(("QA_LINE", f"{question.id} 旧编号节读不懂：{line.strip()[:60]}"))
        else:
            targets = split_ids(alias.group(2))
            question.aliases.append((alias.group(1), [t for t in targets if t != HISTORY_TARGET] or []))
    for name in sections:
        if name not in WORK_SECTIONS:
            question.errors.append(("QA_SECTION", f"{question.id}：不认识的一节 `## {name}`（自由内容写进 ## {NOTES_SECTION}）"))
    if notes_at < len(lines):
        question.notes = "\n".join(lines[notes_at + 1:]).strip("\n")
    stray = list(question.unknown) + [f"{a.id} {u}" for a in question.attempts for u in a.unknown]
    stray += [f"r{a.rev} {u}" for a in question.answers for u in a.unknown]
    if stray:
        question.errors.append(("QA_UNKNOWN", f"{question.id}：不认识的元数据，写入会丢（说明写进 ## {NOTES_SECTION}）："
                                              + "；".join(stray[:4])))
    _derive_superseded(question.attempts)
    return question


def _derive_superseded(attempts: list[Attempt]) -> None:
    by_id = {a.id: a for a in attempts}
    for attempt in attempts:
        if attempt.state == "done":
            for old in attempt.supersedes:
                if old in by_id:
                    by_id[old].superseded_by = attempt.id


def render_question(question: Question) -> str:
    pairs = [("id", question.id), ("state", question.state),
             ("answer", f"r{question.answer_rev}" if question.answer_rev is not None else ""),
             ("review", question.review), ("review_by", question.review_by),
             ("wait", question.wait), ("wait_who", question.wait_who), ("created", question.created)]
    out = [f"# {question.id} {question.text}", render_meta(pairs), "",
           "## 为什么问", "", question.why or WHY_PLACEHOLDER, "",
           "## 怎样算答清", "", question.done_when or DONE_WHEN_PLACEHOLDER, "",
           "## 答案", "", ANSWERS_NOTE]
    out += [render_answer(a) for a in question.answers]
    out += ["", "## 尝试", "", ATTEMPTS_NOTE]
    out += [render_attempt(a) for a in question.attempts]
    if question.aliases:
        out += ["", "## 旧编号", "", ALIASES_NOTE]
        out += [f"- {old} → {'、'.join(targets) if targets else HISTORY_TARGET}" for old, targets in question.aliases]
    out += ["", f"## {NOTES_SECTION}", ""]
    if question.notes.strip():
        out.append(question.notes.strip("\n"))
    return "\n".join(out).rstrip() + "\n"


# ---------- root ----------

def parse_root_text(text: str) -> QaRoot:
    lines = text.splitlines()
    title_line = next((line for line in lines if line.startswith("# ")), "# 计划")
    root = QaRoot(title=title_line[2:].strip())
    marker = next((QA_MARK_RE.match(line.strip()) for line in lines[:6] if QA_MARK_RE.match(line.strip())), None)
    if marker is None:
        root.errors.append(("QA_FORMAT_MARK", "根文件前几行没有 `<!-- plan-format: qa … -->`"))
        return root
    pairs, root.unknown = parse_meta(marker.group(1))
    for key, value in pairs:
        if key == "top-version":
            try:
                root.version = int(value)
                if root.version < 0:
                    raise ValueError
            except ValueError:
                root.errors.append(("QA_VERSION", f"根文件 top-version={value!r} 不是非负整数"))
        elif key == "focus":
            root.focus = value
        elif key == "next":
            root.next_id = value
        elif key == "next_text":
            root.next_text = value
        elif key == "next_when":
            root.next_when = value
        else:
            root.unknown.append(f"{key}={value}")
    if root.unknown:
        root.errors.append(("QA_UNKNOWN", "根文件格式标记里有不认识的内容，写入会丢：" + "；".join(root.unknown[:4])))
    section_starts = [i for i, line in enumerate(lines) if re.match(r"^##\s+\S", line) and not line.startswith("###")]
    first = section_starts[0] if section_starts else len(lines)
    stray = [line for line in lines[:first] if line.strip() and not line.startswith("# ")
             and not _COMMENT_ONLY_RE.match(line)]
    if stray:
        root.errors.append(("QA_UNKNOWN", f"根文件标题和 `## 目标` 之间有文字，写入会丢（挪进目标或某个问题的笔记）：{stray[0].strip()[:40]}"))
    for index, start in enumerate(section_starts):
        end = section_starts[index + 1] if index + 1 < len(section_starts) else len(lines)
        name = lines[start][3:].strip()
        body = lines[start + 1:end]
        if name == "目标":
            root.goal = _prose(body)
        elif name == "问答":
            for line in body:
                if not line.startswith("###"):
                    continue
                match = _ROOT_QUESTION_RE.match(line)
                pairs, _ = parse_meta(match.group(2)) if match else ([], [])
                qid = dict(pairs).get("id", "")
                if not QUESTION_ID_RE.match(qid):
                    root.errors.append(("QA_ROOT_HEADING", f"问答节这一行缺 `<!-- id=Q<n> -->`：{line.strip()[:60]}"))
                    continue
                if qid in root.order:
                    root.errors.append(("QA_ID_DUP", f"问答节里 {qid} 出现两次"))
                    continue
                root.order.append(qid)
        elif name != "现在":
            root.extra += lines[start:end]
    return root


def root_meta(root: QaRoot) -> str:
    pairs = [("top-version", str(root.version) if root.version is not None else ""),
             ("focus", root.focus), ("next", root.next_id), ("next_text", root.next_text),
             ("next_when", root.next_when if (root.next_id or root.next_text) else "")]
    kept = [f"{k}={v}" for k, v in pairs if v]
    return f"<!-- plan-format: qa{(META_SEP + META_SEP.join(kept)) if kept else ''} -->"


def answer_summary(question: Question) -> str:
    """The one line under a question in the root mirror and the card (no IDs)."""
    current = question.current_answer
    parts: list[str] = []
    if question.state == "waiting" and question.wait:
        parts.append(f"等待：{question.wait}")
    if current is not None:
        revised = sum(1 for a in question.answers if a.status in ("superseded", "withdrawn"))
        parts.append(current.text + (f"（改过 {revised} 次）" if revised else ""))
    elif question.withdrawn_answer is not None:
        parts.append(f"旧答已撤回：{question.withdrawn_answer.reason or '原因未写'}；正在复核")
    if question.review:
        parts.append(f"⚠ 要重新确认：{question.review}")
    return " · ".join(parts)


def render_root(root: QaRoot, questions: dict[str, Question], now_lines: list[str]) -> str:
    out = [f"# {root.title}", root_meta(root), "", "## 目标", "", root.goal or "（还没写：plan goal \"…\"）", "",
           "## 现在", "", NOW_NOTE, *now_lines, "", "## 问答", "", ORDER_NOTE]
    for qid in root.order:
        question = questions.get(qid)
        if question is None:
            out += ["", f"### （缺工作本） <!-- id={qid} -->"]
            continue
        out += ["", f"### {question.text} {question.mark} <!-- id={qid} -->"]
        summary = answer_summary(question)
        if summary:
            out.append(f"答：{summary}")
    if root.extra:
        out += ["", *root.extra]
    return "\n".join(out).rstrip() + "\n"


# ---------- what is happening now (shared by the CLI, hooks and the card website) ----------

def focus_question(root: QaRoot, ordered: list[Question]) -> Question | None:
    """The explicit focus while it is open; else the first question with a step in progress."""
    focus = next((q for q in ordered if q.id == root.focus), None)
    if focus is not None and focus.state not in ("closed", "dropped"):
        return focus
    return next((q for q in ordered if q.state not in ("closed", "dropped")
                 and any(a.state == "in_progress" for a in q.attempts)), None)


def compute_now(root: QaRoot, ordered: list[Question]) -> dict:
    """focus / current / running / next / needs_you, without guessing across questions."""
    focus = focus_question(root, ordered)
    attempts = [a for q in ordered for a in q.attempts]
    current = next((a for a in focus.attempts if a.state == "in_progress"), None) if focus else None
    running = [a for a in attempts if a.state == "in_progress" and a is not current]
    brief = lambda a: {"id": a.id, "title": a.title, "state": a.state, "question": a.question,  # noqa: E731
                       "gates": list(a.gates)}
    upcoming = None
    target = next((a for a in attempts if a.id == root.next_id), None) if root.next_id else None
    if target is not None and not target.closed and target.state != "in_progress":
        upcoming = {**brief(target), "when": root.next_when, "source": "explicit"}
    elif root.next_text:
        upcoming = {"id": None, "title": root.next_text, "when": root.next_when, "source": "explicit"}
    elif focus is not None:
        candidate = next((a for a in focus.attempts if a.state == "pending"), None)
        if candidate is not None:
            upcoming = {**brief(candidate), "when": "after" if current else "now", "source": "candidate"}
    needs_you = [{"id": q.id, "question": q.id, "title": q.text, "reason": q.wait}
                 for q in ordered if q.state == "waiting" and q.wait_who == "you"]
    needs_you += [{"id": a.id, "question": a.question, "title": a.title, "reason": a.reason}
                  for a in attempts if a.state == "blocked" and a.who == "you"]
    return {"focus": focus, "current": current, "running": running, "next": upcoming, "needs_you": needs_you}


def load_summary(plan_path: Path) -> dict:
    """Cheap, stdlib-only digest for list views (cards): no CLI, no git.

    {"focus": {id, text} | None, "current": {id, title} | None, "needs_you": int,
     "answered": int, "questions": int, "revision": str}"""
    root_text, files = read_project(plan_path)
    root = parse_root_text(root_text)
    by_id = {}
    for name, text in files.items():
        question = parse_question_text(text)
        if question.id:
            by_id[question.id] = question
    ordered = [by_id[qid] for qid in root.order if qid in by_id]
    now = compute_now(root, ordered)
    focus, current = now["focus"], now["current"] or (now["running"][0] if now["running"] else None)
    return {"focus": {"id": focus.id, "text": focus.text} if focus else None,
            "current": {"id": current.id, "title": current.title} if current else None,
            "needs_you": len(now["needs_you"]),
            "answered": sum(1 for q in ordered if q.state == "closed" and q.current_answer),
            "questions": len(ordered), "revision": revision(root_text, files)}


# ---------- loading from disk ----------

def questions_dir(plan_path: Path) -> Path:
    return plan_path.parent / QUESTIONS_DIR


def work_files(plan_path: Path) -> list[Path]:
    directory = questions_dir(plan_path)
    if not directory.is_dir():
        return []
    files = [p for p in directory.glob("Q*.md") if QUESTION_ID_RE.match(p.stem)]
    return sorted(files, key=lambda p: int(p.stem[1:]))


def revision(root_text: str, files: dict[str, str]) -> str:
    digest = hashlib.sha256(root_text.encode("utf-8"))
    for name in sorted(files):
        digest.update(b"\0" + name.encode("utf-8") + b"\0" + files[name].encode("utf-8"))
    return digest.hexdigest()


def read_project(plan_path: Path) -> tuple[str, dict[str, str]]:
    """(root text, {work file name: text}) read once; the basis of a consistent view."""
    root_text = plan_path.read_text(encoding="utf-8", errors="replace")
    files = {p.name: p.read_text(encoding="utf-8", errors="replace") for p in work_files(plan_path)}
    return root_text, files


def attempt_tuples(plan_path: Path) -> list[tuple[str, str, str, list[str], list[str], str, str]]:
    """(id, title, state, gates, ev, reason, no_artifact_reason) of every attempt, file order.

    For read-only consumers that only know the legacy task model (git hooks, cards)."""
    out = []
    for path in work_files(plan_path):
        question = parse_question_text(path.read_text(encoding="utf-8", errors="replace"), path)
        for a in question.attempts:
            out.append((a.id, a.title, a.state, list(a.gates), list(a.ev), a.reason, a.no_artifact_reason))
    return out
