#!/usr/bin/env python3
"""TOP hooks shared by Claude Code and Codex (SessionStart / Stop / UserPromptSubmit / PreCompact).

- SessionStart: print a short read-only hint (plan position, last task note,
  version state) and record a per-session snapshot outside the project. It no
  longer counts commits "not recorded in the plan": short or unrelated work does
  not belong in the plan (2026-10-16, question-and-answer plans). After a compaction (`source=compact`) it prints
  the recovery card instead: that is the one place both hosts feed hook output
  back to the model once the context was compacted.
- PreCompact: print the same recovery card (goal, current task + gate, next step,
  last failure, plan path; <=800 chars). Claude Code only writes PreCompact stdout
  to its debug log and Codex ignores plain PreCompact stdout, so this is a
  diagnostic copy; the model-visible card comes from SessionStart(compact).
- Stop: only when a step is in progress and this session changed project files or
  made commits while the plan, its question work files and its log stayed untouched,
  emit a non-blocking reminder (JSON `systemMessage`) to note that step, and queue it
  for the next prompt. No step in progress: no reminder (never "explain why not"). Never blocks, never edits the plan. With the
  opt-in completion gate (`git config top.stopGate true`, idea from
  planning-with-files' gate-stop) and an in-progress task that declared a gate,
  the wording gets firmer — still a reminder, never a block.
- UserPromptSubmit: deliver a queued reminder once, then one compact line with the
  current task, the next step, a failure logged in the last 24 hours and the last
  note (skipped right after SessionStart, which just showed the full hint;
  `TOP_INJECT=off` disables the line). Only stable fields (no clock readings).

Everything is read-only for the project (state lives in ~/.cache/top-hooks), the
plan is only described via `sixone-cli.py plan show`, a plan conflict is reported
instead of resolved, and every error path exits 0 so no session is ever blocked.
Plain-text output must not start with `{` or `[` (Codex parses that as JSON).
"""

from __future__ import annotations

import hashlib
import json
import re
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

PLAN_REL = Path("_wiki-methodology/_top/_task_plan.md")
LOG_REL = Path("_wiki-methodology/_top/_logs")
QUESTIONS_REL = Path("_wiki-methodology/_top/_questions")
QA_MARK_RE = re.compile(r"^<!--\s*plan-format:\s*qa\b")
SCRIPTS = Path(__file__).resolve().parent
CLI = SCRIPTS / "sixone-cli.py"
BRIEF = SCRIPTS / "top-brief.py"
HYGIENE = SCRIPTS / "top-hygiene.py"
STATE = Path(os.environ.get("TOP_HOOK_STATE", Path.home() / ".cache" / "top-hooks"))
MAX_CHARS = 900
TURN_CHARS = 200
CARD_CHARS = 800
FAIL_WINDOW_HOURS = 24
TURN_SUFFIX = "（只读，以用户当前请求为准）"
WORKTREE_LIMIT = 6
LEGACY_ONLY = {"PLAN_ACTIVE_WORK_MISSING"}  # old-format plan, not a conflict
PLAN_BYTES_BUDGET = 30_000  # same as top_plan.PLAN_BYTES_BUDGET (plan show only reports size above it)
WORKBOOK_BYTES_BUDGET = 16_000  # a question workbook above this gets its old notes condensed
UPGRADE_NOTE = "旧格式，开工时按 share-top「升级旧计划」迁移成问答格式"
TASK_LINE_PREFIX = ("- [ ] P", "- [x] P", "- [X] P", "* [ ] P", "* [x] P", "* [X] P")


# ---------- shared helpers ----------

def read_payload() -> dict:
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
        data = json.loads(raw) if raw.strip() else {}
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}


def find_project(start: Path) -> Path | None:
    home = Path.home().resolve()
    for d in [start, *start.parents]:
        if (d / PLAN_REL).is_file():
            return d
        if d == home or d == d.parent:
            return None
    return None


def git(root: Path, *args: str, timeout: float = 3) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                             text=True, timeout=timeout)
    except (subprocess.SubprocessError, OSError):
        return None
    return out.stdout if out.returncode == 0 else None


def is_git(root: Path) -> bool:
    top = git(root, "rev-parse", "--show-toplevel", timeout=2)
    return bool(top) and Path(top.strip()).resolve() == root.resolve()


def dirty_paths(root: Path) -> list[str] | None:
    out = git(root, "status", "--porcelain", "-z", "--untracked-files=normal")
    if out is None:
        return None
    paths, entries, i = [], out.split("\0"), 0
    while i < len(entries):
        entry = entries[i]
        if len(entry) > 3:
            paths.append(entry[3:])
            if entry[0] in "RC":  # rename/copy carries the source path next
                i += 1
        i += 1
    return paths


def plan_sha(root: Path) -> str:
    """Plan + question work files + today's plan log: a `plan note` counts as recording progress."""
    digest = hashlib.sha256()
    try:
        digest.update((root / PLAN_REL).read_bytes())
    except OSError:
        return "unreadable"
    for work in sorted((root / QUESTIONS_REL).glob("Q*.md")) if (root / QUESTIONS_REL).is_dir() else []:
        try:
            digest.update(work.name.encode() + work.read_bytes())
        except OSError:
            pass
    try:
        digest.update((root / LOG_REL / f"{time.strftime('%Y-%m-%d')}-plan.md").read_bytes())
    except OSError:
        pass
    return digest.hexdigest()


def state_file(session_id: str) -> Path:
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_") or "unknown"
    return STATE / f"{safe}.json"


def load_state(session_id: str) -> dict:
    try:
        return json.loads(state_file(session_id).read_text())
    except (OSError, ValueError):
        return {}


def save_state(session_id: str, data: dict) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    os.chmod(STATE, 0o700)
    state_file(session_id).write_text(json.dumps(data, ensure_ascii=False))


def prune_state(max_age_days: int = 7) -> None:
    cutoff = time.time() - max_age_days * 86400
    for f in STATE.glob("*.json") if STATE.is_dir() else []:
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass


# ---------- SessionStart ----------

def clip(text: str, limit: int = 80) -> str:
    text = " ".join(str(text).split()).rstrip("。；;，, ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def is_qa(root: Path) -> bool:
    try:
        with (root / PLAN_REL).open(encoding="utf-8", errors="ignore") as handle:
            return any(QA_MARK_RE.match(handle.readline().strip()) for _ in range(6))
    except OSError:
        return False


def is_lightweight(root: Path) -> bool:
    """No structured task lines at all: lightweight mode, no maintenance demands."""
    if is_qa(root):
        return not any((root / QUESTIONS_REL).glob("Q*.md")) if (root / QUESTIONS_REL).is_dir() else True
    try:
        text = (root / PLAN_REL).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return not any(line.lstrip().startswith(TASK_LINE_PREFIX) for line in text.splitlines())


def size_note(data: dict) -> str | None:
    """`plan show` reports plan_bytes only when the plan is over budget."""
    size = data.get("plan_bytes")
    if not isinstance(size, int) or size <= PLAN_BYTES_BUDGET:
        return None
    return f"计划过大（{size // 1024}KB），可运行 plan compact 预览瘦身"


def legacy_stamp(root: Path) -> str | None:
    try:
        out = subprocess.run([sys.executable, str(BRIEF), str(root)],
                             capture_output=True, text=True, timeout=4).stdout
    except (subprocess.SubprocessError, OSError):
        return None
    for line in out.splitlines():
        if line.startswith("stamp:"):
            return "轻量模式，" + clip(line[len("stamp:"):].strip().lstrip("#").strip())
    return None


def plan_show(root: Path, *, fast: bool, timeout: float = 4) -> dict | str:
    """`plan show` JSON, or a one-line reason why it could not be read."""
    args = [sys.executable, str(CLI), "plan", "show", str(root)] + (["--fast"] if fast else [])
    try:
        out = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        data = json.loads(out.stdout)
    except (subprocess.SubprocessError, ValueError, OSError) as exc:
        return f"计划读取失败（{type(exc).__name__}），需人工核对"
    if not isinstance(data, dict):
        return "计划读取失败（输出格式异常），需人工核对"
    codes = [e.get("code", "?") if isinstance(e, dict) else str(e) for e in data.get("errors") or []]
    if codes and set(codes) <= LEGACY_ONLY:
        return legacy_stamp(root) or "轻量模式（计划没有结构化任务）"
    if codes or data.get("verdict") not in (None, "ok"):
        return f"计划存在冲突，需核对（{', '.join(codes) or data.get('verdict')}）；未自动选择当前任务"
    return data


def task_label(data: dict) -> str | None:
    task = data.get("current") or data.get("next")
    if not task:
        return None
    label = "进行中" if data.get("current") else "下一步"
    return clip(f"{label} {task.get('id', '?')} {task.get('title', '')}".strip())


def last_note(data: dict, limit: int = 80) -> str | None:
    notes = data.get("notes") or []
    if not notes:
        return None
    day, hhmm, kind, _id, *text = notes[-1].split(" ", 4) + [""]
    label = {"fail": "上次失败", "learn": "心得"}.get(kind, "上次进展")
    return f"{label}（{day} {hhmm}）：{clip(' '.join(text).strip(), limit)}"


def phase_label(data: dict, limit: int = 60) -> str | None:
    """Outline plans: `第 k/n 阶段「名称」` (+ its one-sentence summary when `limit`)."""
    phase = data.get("phase")
    if not isinstance(phase, dict):
        return "全部阶段已完成" if data.get("phase_count") else None
    text = f"第 {phase.get('index', '?')}/{data.get('phase_count', '?')} 阶段「{clip(phase.get('title', ''), 24)}」"
    summary = (phase.get("summary") or "").strip()
    return text + (f"：{clip(summary, limit)}" if summary and limit else "")


def step_labels(data: dict, limit: int = 50) -> list[str]:
    parts = []
    current, upcoming = data.get("current"), data.get("next")
    if current:
        parts.append(clip(f"正在做 {current.get('id', '?')} {current.get('title', '')}", limit))
    if upcoming:
        parts.append(clip(f"下一步 {upcoming.get('id', '?')} {upcoming.get('title', '')}", limit))
    return parts


def blocker_label(data: dict, limit: int = 60) -> str | None:
    blockers = [b for b in data.get("blockers") or [] if isinstance(b, dict)]
    if not blockers:
        return None
    first = blockers[0]
    more = f"（另 {len(blockers) - 1} 项）" if len(blockers) > 1 else ""
    return clip(f"卡点 {first.get('id', '?')} {first.get('reason') or first.get('title') or ''}", limit) + more


def describe_outline(data: dict) -> str:
    """SessionStart line of an outline plan: goal → phase (+ summary) → step → next → blocker."""
    goal = (data.get("goal") or "").strip()
    parts = [f"目标：{clip(goal, 60)}"] if goal and "<" not in goal else []
    for extra in (phase_label(data), *step_labels(data), blocker_label(data), recent_fail(data)):
        if extra:
            parts.append(extra)
    return "；".join(parts)


def qa_parts(data: dict, limit: int = 50) -> list[str]:
    """Question-and-answer plan, most important first: focus question → current judgement →
    doing / next → needs you → a failure logged in the last day."""
    parts = []
    focus = data.get("focus")
    if focus:
        parts.append(clip(f"正在弄清 {focus.get('id', '?')}「{focus.get('text', '')}」", limit))
        parts.append(clip(f"当前判断：{focus.get('summary') or '还没有答案'}", limit))
    elif data.get("questions"):
        parts.append("没有焦点问题")
    current, upcoming = data.get("current"), data.get("next")
    if current:
        parts.append(clip(f"正在做 {current.get('id', '?')} {current.get('title', '')}", limit))
    if upcoming:
        parts.append(clip(f"下一步 {upcoming.get('id') or ''} {upcoming.get('title', '')}".replace("  ", " "), limit))
    needs = [n for n in data.get("needs_you") or [] if isinstance(n, dict)]
    if needs:
        parts.append(clip(f"需要你：{needs[0].get('reason') or needs[0].get('title', '')}", limit)
                     + (f"（另 {len(needs) - 1} 项）" if len(needs) > 1 else ""))
    fail = recent_fail(data, limit=40)
    if fail:
        parts.append(fail)
    return parts


def fit(prefix: str, parts: list[str], room: int, sep: str = "｜") -> str:
    """Join parts in priority order while they fit; later (less important) parts are dropped whole."""
    body = prefix
    for part in parts:   # a part that does not fit is skipped; a shorter later one may still fit
        candidate = body + (sep if body != prefix else "") + part
        if len(candidate) <= room:
            body = candidate
    return body


def workbook_note(root: Path) -> str | None:
    """Question workbooks over budget, largest first: their old notes should become summaries."""
    big = []
    for path in (root / QUESTIONS_REL).glob("Q*.md"):
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > WORKBOOK_BYTES_BUDGET:
            big.append((size, path.stem))
    if not big:
        return None
    big.sort(reverse=True)
    names = "、".join(f"{name} {size // 1024}KB" for size, name in big[:3])
    more = f" 等 {len(big)} 个" if len(big) > 3 else ""
    return f"工作本过大（{names}{more}），按 share-top「精简工作本」把旧笔记换成摘要"


def version_note(data: dict) -> str | None:
    """Read-only nudge when a QA plan is missing or behind the skill's structure version."""
    if data.get("format") != "qa":
        return None
    version, current = data.get("top_version"), data.get("top_version_current")
    if not isinstance(current, int):
        return None
    if version is None:
        return f"计划未标版本（当前 v{current}），先 plan upgrade 检查"
    if isinstance(version, int) and version < current:
        return f"计划 v{version} 落后于 v{current}，先 plan upgrade"
    if isinstance(version, int) and version > current:
        return f"计划 v{version} 高于本 skill v{current}，先更新 skill"
    return None


def describe_plan(root: Path) -> str:
    data = plan_show(root, fast=False)
    if isinstance(data, str):
        return data
    if data.get("format") == "qa":
        goal = (data.get("goal") or "").strip()
        questions = data.get("questions") or []
        answered = sum(1 for q in questions if isinstance(q, dict) and q.get("state") == "closed")
        parts = ([f"目标：{clip(goal, 60)}"] if goal and "<" not in goal else []) + [f"问答 {answered}/{len(questions)} 已答清"]
        bloat = workbook_note(root)
        version = version_note(data)
        return "；".join(parts + qa_parts(data, 60) + ([bloat] if bloat else []) + ([version] if version else []))
    if data.get("format") == "outline":
        parts = [describe_outline(data), UPGRADE_NOTE]
        task_git = data.get("task_git") or {}
        if task_git.get("branch"):
            where = f"在 {Path(task_git['checkout']).name}" if task_git.get("checkout") else "无 worktree"
            state = "已合并" if task_git.get("merged") else f"领先主线 {task_git.get('ahead') or 0} 提交未合并"
            parts.append(f"任务分支 {task_git['branch']}（{where}，{state}）")
        return "；".join(part for part in parts if part)
    if not any((data.get("counts") or {}).values()):
        goal = (data.get("goal") or "").strip()
        return "轻量模式（计划没有结构化任务）" + (f"，目标：{clip(goal)}" if goal and "<" not in goal else "")
    phase = data.get("phase_id") or "?"
    goal = (data.get("goal") or "").strip()
    parts = [f"阶段 {phase}" + (f"：{clip(goal)}" if goal else "")]
    for extra in (task_label(data), last_note(data)):
        if extra:
            parts.append(extra)
    learning = (data.get("latest_learning") or "").strip()
    if learning and learning.lower() != "none" and not (last_note(data) or "").startswith("心得"):
        parts.append(f"心得：{clip(learning, 60)}")
    blocker = data.get("blocker")
    if blocker and blocker != "none":
        parts.append(f"卡点：{clip(blocker)}")
    task_git = data.get("task_git") or {}
    if task_git.get("branch"):
        where = f"在 {Path(task_git['checkout']).name}" if task_git.get("checkout") else "无 worktree"
        state = "已合并" if task_git.get("merged") else f"领先主线 {task_git.get('ahead') or 0} 提交未合并"
        parts.append(f"任务分支 {task_git['branch']}（{where}，{state}）")
    size = size_note(data)
    if size:
        parts.append(size)
    parts.append(UPGRADE_NOTE)
    return "；".join(parts)


def recent_fail(data: dict, limit: int = 50, hours: float | None = FAIL_WINDOW_HOURS) -> str | None:
    """`plan show`'s last_fail (current/next task or plan), only when logged within `hours`."""
    fail = data.get("last_fail")
    if not isinstance(fail, dict) or not fail.get("text"):
        return None
    try:
        when = datetime.strptime(f"{fail.get('date')} {fail.get('time')}", "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return None
    if hours is not None and datetime.now() - when > timedelta(hours=hours):
        return None
    return f"上次失败（{when:%m-%d %H:%M}）：{clip(fail['text'], limit)}"


def turn_line(root: Path) -> str | None:
    """Compact per-prompt reminder of where the plan stands (read-only, one line, <=TURN_CHARS)."""
    data = plan_show(root, fast=True, timeout=3)
    if isinstance(data, str):
        return f"【TOP 当前】{root.name}：{data}（只读）" if "冲突" in data else None
    if data.get("format") == "qa":
        parts = qa_parts(data, 44)
        if not parts:
            return None
        return fit(f"【TOP 当前】{root.name}：", parts, TURN_CHARS - len(TURN_SUFFIX)) + TURN_SUFFIX
    if data.get("format") == "outline":
        # the core only: which phase, which step, what next, what is stuck (no stray notes)
        parts = [p for p in (phase_label(data, limit=0), *step_labels(data, 44), blocker_label(data, 44),
                             recent_fail(data, 44)) if p]
        if not parts:
            return None
        body = f"【TOP 当前】{root.name}：" + "｜".join(parts)
        room = TURN_CHARS - len(TURN_SUFFIX)
        return (body if len(body) <= room else body[: room - 1] + "…") + TURN_SUFFIX
    label = task_label(data)
    if not label:
        return None
    parts = [label]
    upcoming = data.get("next")
    if data.get("current") and upcoming:
        parts.append(clip(f"下一步 {upcoming.get('id', '?')} {upcoming.get('title', '')}", 50))
    fail = recent_fail(data)
    if fail:
        parts.append(fail)
    note = last_note(data, limit=50)
    if note and not (fail and note.startswith("上次失败")):  # the latest note is that same failure
        parts.append(note)
    body = f"【TOP 当前】{root.name}：" + "｜".join(parts)
    room = TURN_CHARS - len(TURN_SUFFIX)
    if len(body) > room:
        body = body[: room - 1] + "…"
    return body + TURN_SUFFIX


def recovery_card(root: Path) -> str | None:
    """Short card to pick the work up after a context compaction (<=CARD_CHARS)."""
    data = plan_show(root, fast=True, timeout=4)
    if isinstance(data, str):
        return f"【TOP 恢复卡】{root.name}：{data}（只读）"
    if data.get("format") == "qa":
        return qa_recovery_card(root, data)
    if not any((data.get("counts") or {}).values()):
        return None  # lightweight plan: the regular start hint says so
    lines = [f"【TOP 恢复卡】{root.name}（上下文压缩后从这里接上；只读，以用户当前请求为准）"]
    goal = (data.get("goal") or "").strip()
    if goal:
        lines.append(f"目标：{clip(goal, 120)}")
    if data.get("format") == "outline":
        label = phase_label(data, limit=100)
        if label:
            lines.append(f"阶段：{label}")
    current, upcoming = data.get("current"), data.get("next")
    for label, task in (("当前", current), ("下一步", upcoming)):
        if task:
            gates = "；".join(task.get("gates") or [])
            lines.append(clip(f"{label}：{task.get('id', '?')} {task.get('title', '')}"
                              + (f"｜验收：{gates}" if gates else ""), 160))
    if not current and not upcoming:
        lines.append("当前：没有进行中或依赖已就绪的任务（看 plan next 的 waiting/blocked）")
    fail = recent_fail(data, limit=100, hours=None)
    if fail:
        lines.append(fail)
    learning = (data.get("latest_learning") or "").strip()
    if learning and learning.lower() != "none":
        lines.append(f"心得：{clip(learning, 100)}")
    blocker = (data.get("blocker") or "").strip()
    if blocker and blocker.lower() != "none":
        lines.append(f"卡点：{clip(blocker, 80)}")
    outline_blocker = blocker_label(data, 80) if data.get("format") == "outline" else None
    if outline_blocker:
        lines.append(outline_blocker.replace("卡点 ", "卡点：", 1))
    tail = f"计划：{root / str(data.get('task_plan') or PLAN_REL)}；接上前先 `plan` 和 `plan 当前`（在项目目录里）"
    head = "\n".join(lines)
    room = CARD_CHARS - len(tail) - 1
    if len(head) > room:
        head = head[: max(0, room - 1)] + "…"
    return (head + "\n" + tail)[:CARD_CHARS]


def qa_recovery_card(root: Path, data: dict) -> str | None:
    if not data.get("questions"):
        return None
    lines = [f"【TOP 恢复卡】{root.name}（上下文压缩后从这里接上；只读，以用户当前请求为准）"]
    goal = (data.get("goal") or "").strip()
    if goal:
        lines.append(f"目标：{clip(goal, 120)}")
    focus = data.get("focus")
    if focus:
        lines.append(clip(f"正在弄清：{focus.get('id', '?')} {focus.get('text', '')}｜怎样算答清："
                          f"{focus.get('done_when') or '未知'}", 160))
        lines.append(clip(f"当前判断：{focus.get('summary') or '还没有答案'}", 140))
    else:
        lines.append("正在弄清：没有焦点问题（plan 看目录，plan focus Q<n> 选一个）")
    current, upcoming = data.get("current"), data.get("next")
    if current:
        gates = "；".join(current.get("gates") or [])
        lines.append(clip(f"正在做：{current.get('id', '?')} {current.get('title', '')}" + (f"｜验收：{gates}" if gates else ""), 160))
    if upcoming:
        when = "（做完当前这步后）" if upcoming.get("when") == "after" else ""
        lines.append(clip(f"下一步：{upcoming.get('id') or ''} {upcoming.get('title', '')}{when}".replace("  ", " "), 120))
    else:
        lines.append("下一步：待选定")
    fail = recent_fail(data, limit=100, hours=None)
    if fail:
        lines.append(fail)
    for need in (data.get("needs_you") or [])[:2]:
        lines.append(clip(f"需要你：{need.get('reason') or need.get('title', '')}", 100))
    entry = f"plan {focus['id']}" if focus else "plan"
    tail = f"接上前先在项目目录跑 `{entry}`（问题的工作本：答案、尝试、笔记）"
    head = "\n".join(lines)
    room = CARD_CHARS - len(tail) - 1
    if len(head) > room:
        head = head[: max(0, room - 1)] + "…"
    return (head + "\n" + tail)[:CARD_CHARS]


def describe_version(root: Path) -> str | None:
    if not is_git(root):
        return None
    branch = (git(root, "rev-parse", "--abbrev-ref", "HEAD", timeout=2) or "?").strip()
    dirty = dirty_paths(root)
    worktrees = git(root, "worktree", "list", "--porcelain", timeout=3)
    stashes = git(root, "stash", "list", timeout=2)
    n_wt = max(0, sum(1 for line in (worktrees or "").splitlines() if line.startswith("worktree ")) - 1)
    n_stash = len((stashes or "").splitlines())
    parts = [f"分支 {branch}", "未提交数统计超时" if dirty is None else f"未提交 {len(dirty)} 个文件"]
    if n_wt:
        parts.append(f"额外 worktree {n_wt} 个" + (f"（超过上限 {WORKTREE_LIMIT}）" if n_wt > WORKTREE_LIMIT else ""))
    if n_stash:
        parts.append(f"stash {n_stash} 个")
    text = "版本：" + "，".join(parts)
    if n_wt > WORKTREE_LIMIT or n_stash:
        text += f"；清理先看清单 `python3 {HYGIENE} {root}`"
    return text


def on_session_start(payload: dict, root: Path) -> None:
    session = str(payload.get("session_id") or "")
    if session:
        state = load_state(session)
        if state.get("root") != str(root):
            # New session (or a new project): start the closeout window. A resume/compact of
            # the same session keeps its window and any queued reminder.
            state = {"root": str(root), "started_at": time.time(), "head": head(root),
                     "plan_sha": plan_sha(root), "reminded": ""}
        state["hint_fresh"] = True  # the next prompt needs no extra TOP line
        save_state(session, state)
    prune_state()
    if str(payload.get("source") or "") == "compact":
        card = recovery_card(root)
        if card:
            print(card)
            return
    version = describe_version(root)
    text = (f"【TOP 主线】{root.name}：{describe_plan(root)}。"
            + (f"{version}。" if version else "")
            + "这只是只读提示：以用户当前请求为准，不代表要恢复旧任务；"
            "需要时用 `plan` 看（`plan 当前` 看本阶段，`plan help` 一屏速查），计划只经 plan 命令改。")
    print(text[:MAX_CHARS])


# ---------- Stop / UserPromptSubmit ----------

def head(root: Path) -> str:
    return (git(root, "rev-parse", "HEAD", timeout=2) or "").strip()


def work_since(root: Path, started_at: float, start_head: str) -> tuple[list[str], int]:
    changed = []
    for rel in dirty_paths(root) or []:
        if rel.startswith(str(PLAN_REL)) or rel.startswith(str(LOG_REL)):
            continue
        try:
            if (root / rel).stat().st_mtime > started_at:
                changed.append(rel)
        except OSError:
            continue
    commits = git(root, "rev-list", "--count", f"{start_head}..HEAD", timeout=2) if start_head else None
    return changed, int(commits.strip()) if commits and commits.strip().isdigit() else 0


def on_stop(payload: dict, root: Path) -> None:
    session = str(payload.get("session_id") or "")
    if not session or not is_git(root) or is_lightweight(root):
        return
    state = load_state(session)
    if state.get("root") != str(root):  # session predates the hook: baseline now, remind later
        save_state(session, {"root": str(root), "started_at": time.time(), "head": head(root),
                             "plan_sha": plan_sha(root), "reminded": ""})
        return
    current_plan = plan_sha(root)
    if current_plan != state.get("plan_sha"):  # plan was updated: reset the window
        state.update(plan_sha=current_plan, started_at=time.time(), head=head(root),
                     reminded="", pending="")
        save_state(session, state)
        return
    changed, commits = work_since(root, float(state.get("started_at", time.time())),
                                  str(state.get("head") or ""))
    if not changed and not commits:
        return
    signature = hashlib.sha256(json.dumps([sorted(changed), commits]).encode()).hexdigest()
    if signature == state.get("reminded"):
        return
    dirty = dirty_paths(root)
    active = active_task(root)
    if active is None:
        # nothing in progress: unrelated or short work needs no plan record (no reminder)
        state.update(reminded=signature)
        save_state(session, state)
        return
    gated = gated_task(root)
    if gated and is_qa(root):
        gid = gated.get("id", "<ID>")
        msg = (f"【TOP 收尾提醒·完成门】{root.name}：进行中的 {gid}「{clip(gated.get('title', ''), 40)}」"
               f"声明了验收：{clip('；'.join(gated.get('gates') or []), 80)}。本次会话改了 {len(changed)} 个文件"
               + (f"、提交 {commits} 次" if commits else "")
               + f"，还没记它。验收通过就 `plan done {gid} \"结果\" --ev <验收结果> --commit`；没通过或没跑完就 "
               f"`plan note \"卡在哪\" --on {gid} --fail`。（完成门由 git config top.stopGate 开启；只提醒，不阻止结束。）")[:MAX_CHARS]
    elif gated:
        msg = (f"【TOP 收尾提醒·完成门】{root.name}：进行中任务 {gated.get('id', '?')}「{clip(gated.get('title', ''), 40)}」"
               f"声明了验收：{clip('；'.join(gated.get('gates') or []), 80)}。本次会话改了 {len(changed)} 个文件"
               + (f"、提交 {commits} 次" if commits else "")
               + "，却还没有 plan complete 或 plan note。结束前二选一：验收通过就 "
               f"`plan complete {gated.get('id', '<ID>')} --evidence <验收结果> --commit`；没通过或没跑完就 "
               f"`plan note --id {gated.get('id', '<ID>')} --kind progress|fail` 记下卡在哪。"
               + (f"当前未提交 {len(dirty)} 个文件。" if dirty else "")
               + "（完成门由 git config top.stopGate 开启；只提醒，不阻止结束。）")[:MAX_CHARS]
    else:
        aid = active.get("id", "<ID>")
        msg = (f"【TOP 收尾提醒】{root.name}：本次会话改了 {len(changed)} 个文件"
               + (f"、提交 {commits} 次" if commits else "")
               + f"，进行中的 {aid}「{clip(active.get('title', ''), 30)}」还没记进展。"
               f"推进了它就 `plan note \"一句话\" --on {aid}`，做完就 `plan done {aid} …`；"
               "这次的改动跟它无关就不用管，也不用解释。"
               + (f"当前未提交 {len(dirty)} 个文件。" if dirty else ""))
    state.update(reminded=signature, pending=msg)
    save_state(session, state)
    print(json.dumps({"systemMessage": msg}, ensure_ascii=False))


def active_task(root: Path) -> dict | None:
    """The step in progress (attempt for question-and-answer plans), else None."""
    data = plan_show(root, fast=True, timeout=4)
    if not isinstance(data, dict):
        return None
    current = data.get("current") or next(iter(data.get("running") or []), None)  # qa: a run elsewhere counts
    return current if isinstance(current, dict) and current.get("id") else None


def stop_gate_on(root: Path) -> bool:
    """Opt-in completion gate: `git config top.stopGate true` (repo, global or system)."""
    return (git(root, "config", "--type=bool", "--get", "top.stopGate", timeout=2) or "").strip() == "true"


def gated_task(root: Path) -> dict | None:
    """With the gate on: the in-progress task, if it declared a gate (else None)."""
    if not stop_gate_on(root):
        return None
    data = plan_show(root, fast=True, timeout=4)
    current = data.get("current") if isinstance(data, dict) else None
    return current if isinstance(current, dict) and current.get("gates") else None


def on_pre_compact(root: Path) -> None:
    card = recovery_card(root)
    if card:
        print(card)


def on_prompt(payload: dict) -> None:
    session = str(payload.get("session_id") or "")
    state = load_state(session) if session else {}
    lines = []
    if state.get("pending"):
        lines.append(state["pending"][:MAX_CHARS])
        state["pending"] = ""
    fresh = state.pop("hint_fresh", False)
    if session and (lines or fresh):
        save_state(session, state)
    if not fresh and os.environ.get("TOP_INJECT", "on").lower() != "off":
        root = find_project(Path(payload.get("cwd") or os.getcwd()).resolve())
        line = turn_line(root) if root else None
        if line:
            lines.append(line)
    if lines:
        print("\n".join(lines))


def main() -> int:
    payload = read_payload()
    event = str(payload.get("hook_event_name") or (sys.argv[1] if len(sys.argv) > 1 else "SessionStart"))
    if event in ("UserPromptSubmit", "user_prompt_submit"):
        on_prompt(payload)
        return 0
    root = find_project(Path(payload.get("cwd") or os.getcwd()).resolve())
    if root is None:
        return 0
    if event in ("Stop", "stop"):
        on_stop(payload, root)
    elif event in ("PreCompact", "pre_compact"):
        on_pre_compact(root)
    else:
        on_session_start(payload, root)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # never break a session
        sys.exit(0)
