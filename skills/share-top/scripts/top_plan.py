#!/usr/bin/env python3
"""Pure TOP plan control helpers used by sixone-cli.py.

The Markdown file remains the source of truth. This module only parses,
validates, and performs compare-and-swap mutations on that one file.
"""

from __future__ import annotations

import copy
import difflib
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from top_common import (
    PLAN_HEAD_LIMIT,
    PlanConflict,
    PlanError,
    PlanItem,
    PlanPhase,
    PLAN_STATES,
    STAMP_TOKEN_RE,
    TASK_ID_RE,
    TASK_LINE_RE,
    atomic_replace_plan,
    blocked_items,
    current_phase,
    derive_next_item,
    done_criteria_line,
    insert_plan_item,
    is_current_line,
    outline_now_stale,
    parse_plan,
    parse_plan_text,
    plan_invariant_errors,
    project_root,
    phase_state,
    phase_steps,
    PHASE_DROP_PREFIX,
    render_phase_heading,
    render_plan_item,
    strip_phase_marks,
    render_plan_with_mirrors,
    _replace_coordinate,
    _section_bounds,
    GOAL_HEADING_RE,
    qa_format,
    read_text,
)
import top_git
import top_track


SCHEMA_VERSION = "sixone-plan/v1"
LOGGED_ACTIONS = {"start", "complete", "block", "cancel", "reopen"}
PLAN_LOG_SUFFIX = "-plan.md"
ARCHIVE_NAME = "plan-archive.md"
GIT_TIMEOUT = 5
NOTE_KINDS = ("progress", "fail", "learn")
NOTE_SCAN_DAYS = 14
SIMILAR_TITLE_RATIO = 0.6
FAIL_ESCALATE_AT = 3   # third `note --kind fail` on one task → escalate to the user
INSERT_LETTERS = "abcdefghijklmnopqrstuvwxyz"
_INSERTED_SEGMENT_RE = re.compile(r"^(.*\d)([a-z])$")

# Size budgets: the plan is a recovery card, not a diary. Over budget = warning only.
PLAN_BYTES_BUDGET = 30_000
TASK_LINE_BYTES_BUDGET = 500
SCOPE_BYTES_BUDGET = 300
NOTE_CHARS_BUDGET = 300
# Readability budgets of outline plans (warnings): planning-with-files keeps 3–7 phases.
OUTLINE_PHASES_MAX = 7
STEPS_PER_PHASE_MAX = 10
STEP_TITLE_CHARS = 40
PHASE_TITLE_CHARS = 24
SUMMARY_CHARS = 160
BLOCK_REASON_CHARS = 30


def _main_worktree_root(root: Path) -> Path:
    """Plan commands run inside a task worktree act on the main worktree's plan (never branched)."""
    top = top_git.toplevel(root)
    main = top_git.main_worktree(root) if top else None
    if not top or not main or top.resolve() == main.resolve():
        return root
    mapped = main / root.resolve().relative_to(top.resolve())
    return mapped if mapped.is_dir() else root


def _plan_path(project: str) -> tuple[Path, Path]:
    root = _main_worktree_root(project_root(Path(project)))
    candidates = [
        root / "_wiki-methodology" / "_top" / "_task_plan.md",
        root / "wiki-methodology" / "top" / "task_plan.md",
    ]
    for path in candidates:
        if path.is_file():
            return root, path
    return root, candidates[0]


def _item_dict(item: PlanItem) -> dict[str, Any]:
    result = {
        "id": item.id,
        "title": item.title,
        "state": item.state,
        "deps": item.deps,
        "scopes": item.scopes,
        "gates": item.gates,
        "evidence": item.evidence,
        "reason": item.reason or None,
        "no_artifact_reason": item.no_artifact_reason or None,
    }
    if item.section:
        result["phase"] = item.section
    return result


def _section_lines(state, heading: str, limit: int) -> list[str]:
    """Non-empty, non-comment body lines of `## <heading>` (outline plans), last `limit`."""
    start, end = _section_bounds(state.lines, re.compile(rf"^##\s+{re.escape(heading)}\s*$"))
    if start is None:
        return []
    body = [line.strip() for line in state.lines[start + 1:end]
            if line.strip() and not line.strip().startswith("<!--")]
    return body[-limit:]


def _phase_dicts(state) -> list[dict[str, Any]]:
    current = current_phase(state)
    archived = _archived_by_phase(state.path)
    out = []
    for index, phase in enumerate(state.phases, 1):
        steps = phase_steps(phase, state.items)
        counted = [step for step in steps if step.state != "cancelled"]
        out.append({
            "id": phase.id,
            "index": index,
            "title": phase.title,
            "state": phase_state(phase, state.items),
            "summary": phase.summary or None,
            "done": sum(1 for step in counted if step.state == "done"),
            "total": len(counted),
            "current": current is not None and phase.id == current.id,
        })
        if not steps and archived.get(phase.id):   # folded by `plan archive`: still readable
            out[-1]["archived_steps"] = archived[phase.id]
    return out


def _outline_fields(state) -> dict[str, Any]:
    """What a person (and the per-turn hint) needs first: goal, where we are, what is next,
    what is stuck — the planning-with-files "smart injection" set."""
    phases = _phase_dicts(state)
    current = next((phase for phase in phases if phase["current"]), None)
    return {
        "format": "outline",
        "phases": phases,
        "phase": current,
        "phase_count": len(phases),
        "phases_done": sum(1 for phase in phases if phase["state"] in ("done", "cancelled")),
        "blockers": [{"id": item.id, "title": item.title, "reason": item.reason or None}
                     for item in blocked_items(state.items)],
        "questions": _section_lines(state, "关键问题", 5),
        "decisions": _section_lines(state, "决定", 3),
        "now_stale": outline_now_stale(state),
        "details": DETAILS_NAME if (state.path.parent / DETAILS_NAME).is_file() else None,
    }


def _error_dicts(state) -> list[dict[str, str]]:
    return [{"code": code, "message": message} for code, message in plan_invariant_errors(state)]


def _log_dir(plan_path: Path) -> Path:
    top = plan_path.parent
    return top / ("_logs" if top.name == "_top" else "logs")


def _plan_log_path(plan_path: Path, day: datetime) -> Path:
    return _log_dir(plan_path) / f"{day.strftime('%Y-%m-%d')}{PLAN_LOG_SUFFIX}"


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True, text=True, timeout=GIT_TIMEOUT, env=env,
    )


def _git_stamp(cwd: Path) -> str:
    """Read-only `<branch>@<short HEAD>(+N dirty)`; `none` outside git; `unknown(...)` on failure."""
    try:
        inside = _git(cwd, "rev-parse", "--is-inside-work-tree")
        if inside.returncode != 0:
            if "not a git repository" in inside.stderr.lower():
                return "none"
            return f"unknown(rev-parse exit {inside.returncode})"
        branch = _git(cwd, "rev-parse", "--abbrev-ref", "HEAD")
        head = _git(cwd, "rev-parse", "--short", "HEAD")
        status = _git(cwd, "status", "--porcelain")
    except FileNotFoundError:
        return "unknown(git not found)"
    except subprocess.TimeoutExpired:
        return "unknown(git timeout)"
    if status.returncode != 0:
        return f"unknown(status exit {status.returncode})"
    branch_name = branch.stdout.strip() if branch.returncode == 0 else "unborn"
    short = head.stdout.strip() if head.returncode == 0 else "no-commit"
    dirty = sum(1 for line in status.stdout.splitlines() if line.strip())
    return f"{branch_name}@{short}(+{dirty} dirty)"


def _one_line(value: str) -> str:
    return " ".join(value.split())


def _log_evidence(item: PlanItem, action: str) -> str:
    if action == "complete":
        if item.evidence:
            return ",".join(item.evidence)
        return f"no_artifact:{item.no_artifact_reason}"
    if action in {"block", "cancel"}:
        return item.reason
    return "-"


def _append_plan_log(plan_path: Path, action: str, item: PlanItem, extra: str = "") -> dict[str, Any]:
    """Append one timeline line after the plan write; failures warn instead of rolling back."""
    return _append_log_line(plan_path, f"{action} {item.id} {item.title} · ev={_log_evidence(item, action)}{extra}")


def _stamp_log_commit(log: dict[str, Any] | None, sha: str) -> bool:
    """After the commit exists, add `· commit=<sha>` to the log line that the commit carried.

    The log file then differs from the committed copy until the next plan commit;
    writing the SHA into the same commit would be a self-reference.
    """
    if not log or not log.get("file") or not sha:
        return False
    path = Path(log["file"])
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    for index in range(len(lines) - 1, -1, -1):
        if lines[index] == log["line"]:
            lines[index] = f"{log['line']} · commit={sha}"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            log["line"] = lines[index]
            return True
    return False


def _append_log_line(plan_path: Path, body: str) -> dict[str, Any]:
    now = datetime.now()
    log_path = _plan_log_path(plan_path, now)
    line = _one_line(f"- {now.strftime('%H:%M')} {body} · git={_git_stamp(plan_path.parent)}")
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with log_path.open("x", encoding="utf-8") as handle:
                handle.write(f"# {now.strftime('%Y-%m-%d')} log\n\n")
        except FileExistsError:
            pass
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError as exc:
        print(f"[warn] plan 已写入, 但日志追加失败: {log_path}: {exc}", file=sys.stderr)
        return {"file": None, "line": line, "error": str(exc)}
    return {"file": str(log_path), "line": line}


def _recent_log(plan_path: Path, limit: int = 3) -> list[str]:
    today = datetime.now()
    lines: list[str] = []
    for day in (today - timedelta(days=1), today):
        log_path = _plan_log_path(plan_path, day)
        if log_path.is_file():
            lines.extend(
                line for line in log_path.read_text(encoding="utf-8").splitlines()
                if line.startswith("- ")
            )
    return lines[-limit:]


def _note_rows(plan_path: Path, ids: list[str],
               days: int | None = NOTE_SCAN_DAYS) -> list[tuple[str, str, str, str, str]]:
    """(date, HH:MM, kind, id, text) of `plan note` lines for these tasks, oldest first.

    Scans the last `days` daily plan logs (all of them when `days` is None)."""
    if not ids:
        return []
    found = []
    logs = sorted(_log_dir(plan_path).glob(f"????-??-??{PLAN_LOG_SUFFIX}"))
    logs = logs if days is None else logs[-days:]
    for log_path in logs:
        day = log_path.name[:10]
        for line in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            parts = line[2:].split(" ", 3) if line.startswith("- ") else []
            if len(parts) == 4 and parts[1].startswith("note:") and parts[2] in ids:
                text = parts[3].rsplit(" · git=", 1)[0]
                found.append((day, parts[0], parts[1][5:], parts[2], text))
    return found


def _task_notes(plan_path: Path, ids: list[str], limit: int = 3) -> list[str]:
    """Latest `plan note` lines for these tasks, across the last NOTE_SCAN_DAYS daily logs."""
    rows = _note_rows(plan_path, ids)
    return [f"{day[5:]} {hhmm} {kind} {item_id} {text}" for day, hhmm, kind, item_id, text in rows][-limit:]


def _last_fail(plan_path: Path, ids: list[str]) -> dict[str, str] | None:
    """Most recent `note:fail` of these tasks in the note window (stable fields only, no seconds)."""
    fails = [row for row in _note_rows(plan_path, ids) if row[2] == "fail"]
    if not fails:
        return None
    day, hhmm, _, item_id, text = fails[-1]
    return {"date": day, "time": hhmm, "id": item_id, "text": text}


def _fail_count(plan_path: Path, item_id: str) -> int:
    """All `note:fail` lines ever logged for one task (every daily plan log, not just the window)."""
    return sum(1 for row in _note_rows(plan_path, [item_id], days=None) if row[2] == "fail")


def _unrecorded(root: Path, plan_path: Path) -> dict[str, Any] | None:
    """Commits and edits made since the plan was last updated (cross-session catch-up).

    Git decides: the plan's last commit is the baseline; when the plan or its log has
    uncommitted edits, commits older than those edits count as seen. A commit carrying
    a `Task:` (or `Handoff:`) trailer is linked to the plan through Git and is reported
    as `task_commits`, not as unrecorded. Dirty files still need mtimes: Git does not
    know when a working-tree edit happened.
    """
    top = top_git.toplevel(root)
    if top is None:
        return None
    log_dir = _log_dir(plan_path)
    try:
        tracked = [str(plan_path.resolve().relative_to(top.resolve())),
                   str(log_dir.resolve().relative_to(top.resolve()))]
    except ValueError:
        return None
    stamps = [plan_path.stat().st_mtime, *(p.stat().st_mtime for p in log_dir.glob(f"*{PLAN_LOG_SUFFIX}"))]
    since = max(stamps)
    last = top_git.last_commit_touching(top, tracked)
    commits = task_commits = None
    if last:
        entries = top_git.log_trailers(top, rev=f"{last}..HEAD", limit=500)
        if entries is not None:
            plan_dirty = bool(top_git.changed_paths(top, tracked, untracked="normal"))
            # same-second commits count as unrecorded: better a spare reminder than a missed one
            fresh = [e for e in entries if not plan_dirty or e["time"] >= int(since)]
            linked = [e for e in fresh if e["task"] or e["handoff"]]
            commits, task_commits = len(fresh) - len(linked), len(linked)
    files = []
    for rel_path in top_git.dirty_paths(top, untracked="normal"):
        if any(rel_path == t or rel_path.startswith(t.rstrip("/") + "/") for t in tracked):
            continue
        try:
            if (top / rel_path).stat().st_mtime > since:
                files.append(rel_path)
        except OSError:
            continue
    return {"commits": commits, "task_commits": task_commits, "files": len(files), "sample": files[:3]}


def _fmt_time(epoch: int) -> str:
    return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M")


def _activity(root: Path, plan_path: Path, ids: list[str], limit: int = 5) -> list[str]:
    """Latest activity, newest first: commits of the current/next task and the latest
    commits of any task (both by `Task:` trailer, from Git), plus plan notes."""
    main = top_git.main_worktree(root)
    rows: list[tuple[str, str]] = []
    if main is not None:
        seen: set[str] = set()
        patterns = ["^Task: " + re.escape(item_id) + "$" for item_id in ids] + ["^Task: "]
        for pattern in patterns:
            for entry in top_git.log_trailers(main, grep=pattern, limit=limit) or []:
                if not entry["task"] or entry["commit"] in seen:
                    continue
                seen.add(entry["commit"])
                stamp = _fmt_time(entry["time"])
                tasks = ",".join(entry["task"])
                subject = entry["subject"] if entry["subject"].startswith(tasks + " ") else f"{tasks} {entry['subject']}"
                rows.append((stamp, f"{stamp} commit {entry['commit']} {subject}"))
    for day, hhmm, kind, item_id, text in _note_rows(plan_path, ids + ["plan"])[-limit:]:
        stamp = f"{day} {hhmm}"
        rows.append((stamp, f"{stamp} note:{kind} {item_id} {text}"))
    rows.sort(key=lambda row: row[0], reverse=True)
    return [text for _, text in rows[:limit]]


def _last_handoff(root: Path) -> dict[str, Any] | None:
    main = top_git.main_worktree(root)
    if main is None:
        return None
    for entry in top_git.log_trailers(main, grep="^Handoff: ", limit=3) or []:
        if entry["handoff"]:
            return {"commit": entry["commit"], "time": _fmt_time(entry["time"]),
                    "path": entry["handoff"][0], "subject": entry["subject"]}
    return None


def _task_git(root: Path, item: PlanItem | None) -> dict[str, Any] | None:
    if item is None:
        return None
    main = top_git.main_worktree(root)
    branch = top_git.task_branch(item.id)
    if main is None or not top_git.branch_exists(main, branch):
        return None
    checkout = top_git.task_checkout(main, item.id)
    counts = top_git.ahead_behind(main, "HEAD", branch)
    return {
        "branch": branch,
        "checkout": str(checkout) if checkout else None,
        "ahead": counts[0] if counts else None,
        "merged": top_git.is_merged(main, branch),
    }


QA_REFUSAL = "这是问答格式的计划，只能用问答命令改：plan ask / answer / add / start / done …（plan help）"


def _writable_path(project: str) -> tuple[Path, Path]:
    """_plan_path for the legacy/outline writers: a question-and-answer plan is refused
    before anything is read or written (no log line, no archive, no half-done side effect)."""
    root, path = _plan_path(project)
    if _qa(path) is not None:
        raise PlanError(QA_REFUSAL)
    return root, path


def _qa(path: Path):
    """top_qa when the plan at `path` is a question-and-answer plan, else None."""
    if not path.is_file() or not qa_format().is_qa_text(read_text(path)[:2000]):
        return None
    import top_qa  # noqa: PLC0415 - top_qa imports this module
    return top_qa


def show(project: str, *, fast: bool = False) -> dict[str, Any]:
    root, path = _plan_path(project)
    if not path.is_file():
        return {"error": f"task plan not found: {path}"}
    qa = _qa(path)
    if qa is not None:
        return qa.show(project)
    state = parse_plan(path)
    errors = _error_dicts(state)
    current = next((item for item in state.items if item.state == "in_progress"), None)
    next_item = derive_next_item(state)
    counts = {
        name: sum(1 for item in state.items if item.state == name)
        for name in ("pending", "in_progress", "blocked", "done", "cancelled")
    }
    focus = current or next_item
    gate_text = f"（验收：{'；'.join(focus.gates)}）" if focus and focus.gates else ""
    if state.outline:
        phase = current_phase(state)
        if phase is not None:
            gate_text += f"｜第 {state.phases.index(phase) + 1}/{len(state.phases)} 阶段 {phase.title}"
    plan_bytes = len(state.text.encode("utf-8"))
    result = {
        "schema_version": SCHEMA_VERSION,
        "tool": "plan-show",
        "project": str(root),
        "task_plan": str(path.relative_to(root)),
        "phase_id": state.phase_id or None,
        "goal": state.coordinate.get("goal") or None,
        "current": _item_dict(current) if current else None,
        "next": _item_dict(next_item) if next_item else None,
        "latest_learning": state.coordinate.get("latest_learning") or None,
        "blocker": state.coordinate.get("blocker") or None,
        "counts": counts,
        "recent_log": _recent_log(path),
        "notes": _task_notes(path, [item.id for item in (current, next_item) if item] + ["plan"]),
        "last_fail": _last_fail(path, [item.id for item in (current, next_item) if item] + ["plan"]),
        "unrecorded": None if fast else _unrecorded(root, path),
        "task_git": None if fast else _task_git(root, current or next_item),
        "activity": None if fast else _activity(root, path, [item.id for item in (current, next_item) if item]),
        "last_handoff": None if fast else _last_handoff(root),
        "errors": errors,
        "verdict": "warn" if errors else "ok",
        "next_hint": (
            f"继续 {current.id}: {current.title}{gate_text}" if current
            else f"启动 {next_item.id}: {next_item.title}{gate_text}" if next_item
            else "无 dependency-ready pending task; 检查 blocked/done criteria"
        ),
    }
    if state.outline:
        result.update(_outline_fields(state))
    else:
        result["format"] = "legacy"
        if state.items:
            result["migrate_hint"] = ("旧格式计划（Active Work 清单）：主线难读。按 share-top 的 "
                                      "references/qa-plan.md 改写成问答格式，再用 plan rewrite 草稿.md --to qa 替换")
    original = path.parent / BEFORE_COMPACT_LINK
    if original.is_symlink() and original.exists():
        result["before_compact"] = str(original.relative_to(root))
    if plan_bytes > PLAN_BYTES_BUDGET:
        result["plan_bytes"] = plan_bytes
        result["compact_hint"] = (f"计划 {plan_bytes // 1024}KB 超过 {PLAN_BYTES_BUDGET // 1000}KB 预算："
                                  f"plan compact {root} 预览，确认后加 --apply")
    return result


def list_items(project: str, state_filter: str | None = None) -> dict[str, Any]:
    root, path = _plan_path(project)
    if not path.is_file():
        return {"error": f"task plan not found: {path}"}
    qa = _qa(path)
    if qa is not None:
        return qa.list_items(project, state_filter)
    state = parse_plan(path)
    items = state.items
    if state_filter:
        items = [item for item in items if item.state == state_filter]
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": "plan-list",
        "project": str(root),
        "state_filter": state_filter,
        "items": [_item_dict(item) for item in items],
        "count": len(items),
    }


def is_lightweight(state) -> bool:
    """A plan without structured tasks (no Active Work, or no task lines) runs in lightweight mode."""
    return state.active_start is None or not state.items


def _long_notes(plan_path: Path) -> list[str]:
    hits = []
    logs = sorted(_log_dir(plan_path).glob(f"????-??-??{PLAN_LOG_SUFFIX}"))[-NOTE_SCAN_DAYS:]
    for log_path in logs:
        for line in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            parts = line[2:].split(" ", 3) if line.startswith("- ") else []
            if len(parts) == 4 and parts[1].startswith("note:"):
                text = parts[3].rsplit(" · git=", 1)[0]
                if len(text) > NOTE_CHARS_BUDGET:
                    hits.append(f"{log_path.name} {parts[0]} {parts[2]} ({len(text)} 字)")
    return hits


def budget_warnings(root: Path, path: Path, state) -> list[dict[str, str]]:
    """Size budgets (warnings, never blocking) with the command that fixes each one."""
    warnings: list[dict[str, str]] = []
    plan_bytes = len(state.text.encode("utf-8"))
    if plan_bytes > PLAN_BYTES_BUDGET:
        closed = sum(1 for item in state.items if item.closed)
        hint = f"plan compact {root}（预览）→ 加 --apply 把按日期的流水段移到 _logs/"
        if closed > 10:
            hint += f"；已关闭任务 {closed} 个可再 plan archive {root}"
        warnings.append({"code": "PLAN_OVER_BUDGET",
                         "message": f"计划 {plan_bytes // 1024}KB > {PLAN_BYTES_BUDGET // 1000}KB", "hint": hint})
    long_lines = [(item, len(state.lines[item.line_index].encode("utf-8"))) for item in state.items
                  if len(state.lines[item.line_index].encode("utf-8")) > TASK_LINE_BYTES_BUDGET]
    if long_lines:
        sample = ", ".join(f"{item.id}({size}B)" for item, size in sorted(long_lines, key=lambda x: -x[1])[:5])
        warnings.append({"code": "PLAN_TASK_LINE_LONG",
                         "message": f"{len(long_lines)} 个任务行 > {TASK_LINE_BYTES_BUDGET}B: {sample}",
                         "hint": "任务行只放标题+dep/scope/gate/ev 引用；细节写进 _logs/ 或证据文件，"
                                 "用 plan edit <ID> --remove-scope/--add-scope 收短"})
    long_scopes = [item.id for item in state.items
                   if len(" ".join(item.scopes).encode("utf-8")) > SCOPE_BYTES_BUDGET]
    if long_scopes:
        warnings.append({"code": "PLAN_SCOPE_LONG",
                         "message": f"{len(long_scopes)} 个任务 scope 合计 > {SCOPE_BYTES_BUDGET}B: "
                                    + ", ".join(long_scopes[:5]),
                         "hint": "scope 写 path:/symbol:/registry: 引用而不是说明文字；"
                                 "plan edit <ID> --remove-scope '<旧>' --add-scope '<短引用>'"})
    if state.outline:
        warnings.extend(readability_warnings(state))
    learning = state.coordinate.get("latest_learning") or ""
    long_notes = _long_notes(path)
    if len(learning) > NOTE_CHARS_BUDGET:
        long_notes.insert(0, f"Latest learning ({len(learning)} 字)")
    if long_notes:
        warnings.append({"code": "PLAN_NOTE_LONG",
                         "message": f"{len(long_notes)} 条笔记 > {NOTE_CHARS_BUDGET} 字: " + "; ".join(long_notes[:3]),
                         "hint": "plan note 只写一句话结论+证据路径；长复盘写进 _logs/<date>-<topic>.md 再在 note 里链接"})
    return warnings


def readability_warnings(state) -> list[dict[str, str]]:
    """Outline plans are read by people first: a short table of contents in plain words,
    each phase with a sentence that links it to the previous and the next one."""
    warnings: list[dict[str, str]] = []
    live = [phase for phase in state.phases if phase_steps(phase, state.items)
            or phase_state(phase, state.items) not in ("done", "cancelled")]
    if len(state.phases) > OUTLINE_PHASES_MAX:
        warnings.append({"code": "PLAN_PHASES_MANY",
                         "message": f"{len(state.phases)} 个阶段 > {OUTLINE_PHASES_MAX}（其中未收起 {len(live)} 个）",
                         "hint": "把做完的相邻阶段合并成一个（plan migrate 重写目录），或开新计划承接新目标"})
    long_titles = [f"{item.id}({len(item.title)} 字)" for item in state.items
                   if not item.closed and len(item.title) > STEP_TITLE_CHARS]
    long_titles += [f"{phase.id}({len(phase.title)} 字)" for phase in state.phases
                    if len(phase.title) > PHASE_TITLE_CHARS]
    if long_titles:
        warnings.append({"code": "PLAN_TITLE_LONG",
                         "message": f"标题太长：{', '.join(long_titles[:6])}",
                         "hint": f"步骤标题 ≤{STEP_TITLE_CHARS} 字、阶段标题 ≤{PHASE_TITLE_CHARS} 字，写成一句人话；"
                                 "细节、数字和术语放进 findings 或日志，用 plan edit / plan phase edit 改"})
    technical = [f"{item.id}「{item.title}」" for item in state.items if _looks_technical(item.title)]
    technical += [f"{phase.id}「{phase.title}」" for phase in state.phases if _looks_technical(phase.title)]
    if technical:
        warnings.append({"code": "PLAN_TITLE_TECHNICAL",
                         "message": f"标题里有技术细节（路径、编号、小数/百分比、成串英文术语）：{'；'.join(technical[:4])}",
                         "hint": "标题写逻辑层的一句人话：这一步要回答什么、得到什么；术语和数字放阶段小结或 _plan_details.md"})
    archived = _archived_by_phase(state.path)
    bare = [phase.id for phase in state.phases
            if not phase_steps(phase, state.items) and not archived.get(phase.id)]
    if bare:
        warnings.append({"code": "PLAN_PHASE_NO_STEPS",
                         "message": f"阶段下没有步骤，卡片上点不开：{', '.join(bare[:6])}",
                         "hint": "每个阶段都列步骤：做完的阶段保留 3–5 条关键步骤（做了什么、结果怎样），"
                                 "没开始的阶段至少写出第一步；plan add --parent <阶段ID>"})
    current = current_phase(state)
    missing = [phase.id for phase in state.phases if not phase.summary
               and (phase_state(phase, state.items) in ("done", "cancelled") or phase is current)]
    if missing:
        warnings.append({"code": "PLAN_PHASE_NO_SUMMARY",
                         "message": f"阶段缺一句小结：{', '.join(missing[:6])}",
                         "hint": "plan phase edit <项目> <P> --summary '<为什么做/得到了什么、对下一阶段意味着什么>'"})
    long_summaries = [phase.id for phase in state.phases if len(phase.summary) > SUMMARY_CHARS]
    if long_summaries:
        warnings.append({"code": "PLAN_SUMMARY_LONG",
                         "message": f"阶段小结 > {SUMMARY_CHARS} 字：{', '.join(long_summaries[:6])}",
                         "hint": "小结只写一两句承上启下的话；过程和数字进日志或 findings"})
    crowded = [f"{phase.id}({len(phase_steps(phase, state.items))} 步)" for phase in state.phases
               if len(phase_steps(phase, state.items)) > STEPS_PER_PHASE_MAX]
    if crowded:
        warnings.append({"code": "PLAN_STEPS_MANY",
                         "message": f"阶段里步骤太多：{', '.join(crowded[:6])}",
                         "hint": "一个阶段 3–8 步；做完的阶段用 plan archive 收起，太大的阶段拆成两个"})
    misused = [item.id for item in state.items if not item.closed and item.no_artifact_reason]
    if misused:
        warnings.append({"code": "PLAN_META_MISUSED",
                         "message": f"未完成的步骤带着 no_artifact_reason：{', '.join(misused[:6])}",
                         "hint": "no_artifact_reason 只用于“完成了但没有产物”；说明写进 plan note。"
                                 "去掉它：把计划复制成草稿、删掉这一段，再 plan migrate 草稿 --apply"})
    long_reasons = [item.id for item in state.items if item.state == "blocked" and len(item.reason) > BLOCK_REASON_CHARS]
    if long_reasons:
        warnings.append({"code": "PLAN_REASON_LONG",
                         "message": f"卡住的原因超过 {BLOCK_REASON_CHARS} 字：{', '.join(long_reasons[:6])}",
                         "hint": "卡点原因写一句短话（等谁、等什么）；路径和细节写进 plan note。"
                                 "改法：plan reopen <ID> 后 plan block <ID> --reason '<短原因>'"})
    if outline_now_stale(state):
        warnings.append({"code": "PLAN_NOW_STALE",
                         "message": "## 现在 与步骤状态不一致（被手改过或缺失）",
                         "hint": "下一次 plan 写操作会自动重写；别手改这一段"})
    return warnings


# paths (a/b/c, x.md), identifiers (snake_case, `code`), decimals, percentages, task IDs;
# a single "/" as in "物性/岩相" is ordinary Chinese punctuation, not a path
_PATHISH_RE = re.compile(r"(?:[\w.-]+/){2,}|`|[A-Za-z0-9]_[A-Za-z0-9]|\.(?:md|py|json|ya?ml|sh|csv|ipynb|txt)\b"
                         r"|\d+\.\d+|\d+(?:\.\d+)?\s*%|\bP\d+(?:\.[A-Za-z0-9]+)+\b")
_LATIN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9]+")


def _looks_technical(title: str) -> bool:
    """Heuristic for "not a plain sentence": paths, IDs, decimals/percentages, or three and more
    Latin terms in one title. A warning only; project names in Latin letters are fine alone."""
    return bool(_PATHISH_RE.search(title)) or len(_LATIN_WORD_RE.findall(title)) >= 3


def _archived_by_phase(plan_path: Path) -> dict[str, list[dict[str, str]]]:
    """Steps that `plan archive` moved out of an outline plan, grouped by their phase ID."""
    out: dict[str, list[dict[str, str]]] = {}
    for item_id, (title, state_name) in _archived_steps(plan_path).items():
        phase = item_id.split(".", 1)[0]
        out.setdefault(phase, []).append({"id": item_id, "title": title, "state": state_name})
    return out


def validate(project: str) -> dict[str, Any]:
    root, path = _plan_path(project)
    if not path.is_file():
        return {"error": f"task plan not found: {path}"}
    qa = _qa(path)
    if qa is not None:
        return qa.validate(project)
    state = parse_plan(path)
    errors = _error_dicts(state)
    warnings = [] if is_lightweight(state) else budget_warnings(root, path, state)
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": "plan-validate",
        "project": str(root),
        "verdict": "block" if errors else "warn" if warnings else "ok",
        "errors": errors,
        "warnings": warnings,
        "next_hint": ("按 errors 修复 Active Work/Current Coordinate 后重跑" if errors
                      else warnings[0]["hint"] if warnings else "plan invariants valid"),
    }


def inspect(project: str, item_id: str) -> dict[str, Any]:
    root, path = _plan_path(project)
    if not path.is_file():
        return {"error": f"task plan not found: {path}"}
    state = parse_plan(path)
    item = state.by_id().get(item_id)
    if item is None:
        return {"error": f"unknown task id: {item_id}"}
    children = [child.id for child in state.items if child.id.startswith(item.id + ".")]
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": "plan-inspect",
        "project": str(root),
        "item": _item_dict(item),
        "children": children,
        "plan_errors": _error_dicts(state),
        "next_hint": "scope=symbol/path 可交给 affected --task 做 CodeGraph/owner 影响分析",
    }


def _require_clean_state(state) -> None:
    errors = plan_invariant_errors(state)
    if errors:
        summary = "; ".join(f"{code}: {message}" for code, message in errors[:5])
        raise PlanError(f"plan invariants invalid before mutation: {summary}")


def _has_comment_marker(value: str) -> bool:
    return "<!--" in value or "-->" in value


def _clean_title(title: str) -> str:
    title = title.strip()
    if not title or "\n" in title or "\r" in title or " · " in title or _has_comment_marker(title):
        raise PlanError("title must be one non-empty line without the metadata delimiter ' · ' or '<!--'/'-->'")
    return title


def _clean_metadata_values(values: list[str], label: str) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        value = value.strip()
        if not value or "\n" in value or "\r" in value or " · " in value or _has_comment_marker(value):
            raise PlanError(f"{label} values must be non-empty single lines without ' · ' or '<!--'/'-->'")
        if value not in cleaned:
            cleaned.append(value)
    return cleaned


def _write_mutation(
    state, new_text: str, action: str, item_id: str,
    log_item: PlanItem | None = None, log_extra: str = "",
) -> dict[str, Any]:
    parsed = parse_plan_text(state.path, new_text)
    errors = plan_invariant_errors(parsed)
    if errors:
        summary = "; ".join(f"{code}: {message}" for code, message in errors[:8])
        raise PlanError(f"mutation would violate plan invariants: {summary}")
    atomic_replace_plan(state.path, state.sha256, new_text)
    result = {
        "schema_version": SCHEMA_VERSION,
        "tool": f"plan-{action}",
        "verdict": "ok",
        "item_id": item_id,
        "task_plan": str(state.path),
    }
    if action in LOGGED_ACTIONS:
        result["log"] = _append_plan_log(state.path, action, log_item, log_extra) if log_item else None
    result["next_hint"] = show(str(state.path.parent.parent.parent)).get("next_hint")
    return result


def add(
    project: str,
    *,
    title: str,
    item_id: str | None = None,
    parent: str | None = None,
    deps: list[str] | None = None,
    scopes: list[str] | None = None,
    gates: list[str] | None = None,
    depends_on: list[str] | None = None,
) -> dict[str, Any]:
    """`depends_on` takes comma lists (`A,B`) and is written back as one `depends_on=A,B` segment;
    `deps` keeps the classic repeated `dep=` form. Gates are free-text acceptance criteria or commands."""
    _, path = _writable_path(project)
    state = parse_plan(path)
    _require_clean_state(state)
    by_id = state.by_id()
    alias = [dep.strip() for group in depends_on or [] for dep in group.split(",") if dep.strip()]
    dep_style = "depends_on" if alias and not deps else "dep"
    deps = _clean_metadata_values([*(deps or []), *alias], "dep")
    scopes = _clean_metadata_values(list(scopes or []), "scope")
    gates = _clean_metadata_values(list(gates or []), "gate")
    if bool(item_id) == bool(parent):
        raise PlanError("pass exactly one of --id or --parent")
    phase_ids = {phase.id for phase in state.phases}
    parent_is_phase = bool(parent) and parent in phase_ids
    if state.outline and parent and parent in by_id:
        raise PlanError(f"目录格式只有 阶段 → 步骤 两层：不能挂在步骤 {parent} 下面；"
                        f"要补内容就在它后面插一步（plan insert {parent} …），或加到阶段里")
    if parent:
        if parent not in by_id and not parent_is_phase:
            hint = "（目录格式：阶段用 plan phase add 新建）" if state.outline else ""
            raise PlanError(f"unknown parent id: {parent}{hint}")
        used = set(by_id) | _archived_ids(path)
        index = 1
        while f"{parent}.{index}" in used:
            index += 1
        item_id = f"{parent}.{index}"
    assert item_id is not None
    if not TASK_ID_RE.fullmatch(item_id):
        raise PlanError(f"invalid task id: {item_id}")
    if state.outline:
        if not any(item_id.startswith(pid + ".") for pid in phase_ids):
            raise PlanError(f"{item_id} 不在任何阶段下：先 plan phase add 建阶段，或用 --parent <阶段ID>")
    elif state.phase_id and not item_id.startswith(state.phase_id + "."):
        raise PlanError(f"task id must be under current phase {state.phase_id}")
    if item_id in by_id:
        raise PlanError(f"duplicate task id: {item_id}")
    for dep in deps or []:
        if dep not in by_id:
            raise PlanError(f"unknown dependency: {dep}")
    item = PlanItem(
        id=item_id,
        title=_clean_title(title),
        checked=False,
        state="pending",
        line_index=-1,
        deps=deps,
        scopes=scopes,
        gates=gates,
        dep_style=dep_style,
    )
    similar = _similar_open_tasks(state, item)
    if state.outline and item_id.count(".") > 1:
        raise PlanError(f"目录格式只有 阶段 → 步骤 两层：{item_id} 太深；在同阶段下另起一步即可")
    if parent and not parent_is_phase:   # right after the parent's subtree: the markdown reads as an outline
        new_text = _render_with_inserts(state, list(state.items), _subtree_end(state.items, parent), [item])
    else:
        new_text = insert_plan_item(state, item)
    result = _write_mutation(state, new_text, "add", item_id)
    if similar:
        result["warnings"] = similar
        result["next_hint"] = "可能与已有开放任务重复：确认后用 plan cancel 合并，或改标题/scope 区分"
    return result


def _similar_open_tasks(state, new: PlanItem) -> list[str]:
    """Open tasks sharing a scope or with a near-identical title (duplicates across sessions)."""
    def norm(text: str) -> str:
        return "".join(ch for ch in text.lower() if ch.isalnum())

    hits = []
    for other in state.items:
        if other.closed:
            continue
        shared = sorted(set(other.scopes) & set(new.scopes))
        ratio = difflib.SequenceMatcher(None, norm(other.title), norm(new.title)).ratio()
        if shared:
            hits.append(f"{other.id} {other.title}（同 scope {', '.join(shared)}）")
        elif ratio >= SIMILAR_TITLE_RATIO:
            hits.append(f"{other.id} {other.title}（标题相近 {ratio:.2f}）")
    return hits


def _mutate_item(project: str, item_id: str, action: str, *, log: bool = True, **kwargs) -> dict[str, Any]:
    _, path = _writable_path(project)
    state = parse_plan(path)
    _require_clean_state(state)
    items = copy.deepcopy(state.items)
    by_id = {item.id: item for item in items}
    item = by_id.get(item_id)
    if item is None:
        raise PlanError(f"unknown task id: {item_id}")
    open_children = [child.id for child in items if child.id.startswith(item.id + ".") and not child.closed]
    if action == "edit":
        if item.closed:
            raise PlanError(f"closed task cannot be edited: {item_id}; reopen it first")
        changed = False
        title = kwargs.get("title")
        if title is not None:
            new_title = _clean_title(title)
            changed = changed or new_title != item.title
            item.title = new_title
        fields = (
            ("deps", "add_deps", "remove_deps"),
            ("scopes", "add_scopes", "remove_scopes"),
            ("gates", "add_gates", "remove_gates"),
        )
        for attr, add_key, remove_key in fields:
            additions = _clean_metadata_values(list(kwargs.get(add_key) or []), attr)
            removals = _clean_metadata_values(list(kwargs.get(remove_key) or []), attr)
            overlap = sorted(set(additions) & set(removals))
            if overlap:
                raise PlanError(f"cannot add and remove the same {attr}: {', '.join(overlap)}")
            current = list(getattr(item, attr))
            missing = [value for value in removals if value not in current]
            if missing:
                raise PlanError(f"cannot remove missing {attr}: {', '.join(missing)}")
            updated = [value for value in current if value not in removals]
            updated.extend(value for value in additions if value not in updated)
            changed = changed or updated != current
            setattr(item, attr, updated)
        if item_id in item.deps:
            raise PlanError("task cannot depend on itself")
        missing_deps = [dep for dep in item.deps if dep not in by_id]
        if missing_deps:
            raise PlanError(f"unknown dependencies: {', '.join(missing_deps)}")
        if not changed:
            raise PlanError("edit requested no effective change")
    elif action == "start":
        active = [other.id for other in items if other.state == "in_progress" and other.id != item_id]
        if active:
            raise PlanError(f"another task is already in_progress: {active[0]}")
        if item.state != "pending":
            raise PlanError(f"only pending task can start: {item_id} is {item.state}")
        missing = [dep for dep in item.deps if not by_id[dep].closed]
        if missing:
            raise PlanError(f"dependencies are not closed: {', '.join(missing)}")
        item.state = "in_progress"
        item.checked = False
    elif action == "complete":
        if item.state not in {"pending", "in_progress"}:
            raise PlanError(f"only pending/in_progress task can complete: {item_id} is {item.state}")
        if open_children:
            raise PlanError(f"open children prevent completion: {', '.join(open_children)}")
        evidence = [_plan_value(value, "--evidence") for value in kwargs.get("evidence") or []]
        no_reason = _plan_value(kwargs.get("no_artifact_reason") or "", "--no-artifact-reason", allow_empty=True, terminal=True)
        if not evidence and not no_reason:
            raise PlanError("complete requires --evidence or --no-artifact-reason")
        item.state = "done"
        item.checked = True
        item.evidence.extend(value for value in evidence if value not in item.evidence)
        item.no_artifact_reason = no_reason
        item.reason = ""
    elif action == "block":
        if item.closed:
            raise PlanError(f"closed task cannot be blocked: {item_id}")
        reason = _plan_value(kwargs.get("reason") or "", "--reason", allow_empty=True, terminal=True)
        if not reason:
            raise PlanError("block requires a reason")
        item.state = "blocked"
        item.checked = False
        item.reason = reason
    elif action == "reopen":
        if item.state not in {"done", "cancelled", "blocked"}:
            raise PlanError(f"only done/cancelled/blocked task can reopen: {item_id} is {item.state}")
        item.state = "pending"
        item.checked = False
        item.reason = ""
        item.no_artifact_reason = ""
    elif action == "cancel":
        if item.closed:
            raise PlanError(f"task is already closed: {item_id}")
        if open_children:
            raise PlanError(f"open children prevent cancellation: {', '.join(open_children)}")
        reason = _plan_value(kwargs.get("reason") or "", "--reason", allow_empty=True, terminal=True)
        if not reason:
            raise PlanError("cancel requires a reason")
        item.state = "cancelled"
        item.checked = True
        item.reason = reason
    else:
        raise PlanError(f"unknown action: {action}")
    new_text = render_plan_with_mirrors(state, items)
    return _write_mutation(state, new_text, action, item_id, log_item=item if log else None,
                           log_extra=kwargs.get("log_extra") or "")


def start(project: str, item_id: str, *, worktree: bool = False) -> dict[str, Any]:
    result = _mutate_item(project, item_id, "start")
    if worktree:
        root, _ = _plan_path(project)
        main = top_git.main_worktree(root)
        git_result = top_git.start_task_worktree(main, item_id) if main else {"error": "not a git repository"}
        result["git"] = git_result
        if "error" in git_result:
            result["verdict"] = "warn"
        else:
            result["next_hint"] = (f"在 {git_result['checkout']} 里改代码；计划仍只在主 worktree，"
                                   f"用 CLI 更新。完成后 plan complete {item_id} --commit --merge")
    return result


def edit(
    project: str,
    item_id: str,
    *,
    title: str | None = None,
    add_deps: list[str] | None = None,
    remove_deps: list[str] | None = None,
    add_scopes: list[str] | None = None,
    remove_scopes: list[str] | None = None,
    add_gates: list[str] | None = None,
    remove_gates: list[str] | None = None,
) -> dict[str, Any]:
    return _mutate_item(
        project, item_id, "edit", title=title,
        add_deps=add_deps, remove_deps=remove_deps,
        add_scopes=add_scopes, remove_scopes=remove_scopes,
        add_gates=add_gates, remove_gates=remove_gates,
    )


def _plan_value(value: str, label: str, *, allow_empty: bool = False, terminal: bool = False) -> str:
    """A metadata value written into a plan line: one line; ' · ' only in terminal keys
    (reason/no_artifact_reason consume the rest of the line when parsed)."""
    value = value.strip()
    if ("\n" in value or "\r" in value or (not terminal and " · " in value)
            or _has_comment_marker(value) or (not value and not allow_empty)):
        rule = "one line" if terminal else "one line without the metadata delimiter ' · '"
        raise PlanError(f"{label} must be {rule}")
    return value


def _decision_refs(project: str, decisions: list[str]) -> list[Path]:
    """Existing decision files named by `--decision` (project-relative or absolute)."""
    root, _ = _plan_path(project)
    paths = []
    for value in decisions:
        value = value.strip()
        if not value or "\n" in value or " · " in value:
            raise PlanError("--decision must be one file path")
        path = Path(value) if Path(value).is_absolute() else root / value
        if not path.is_file():
            raise PlanError(f"decision file not found: {value}")
        paths.append(path.resolve())
    return paths


def complete(
    project: str, item_id: str, evidence: list[str], no_artifact_reason: str | None,
    *, log: bool = True, commit: bool = False, merge: bool = False,
    decisions: list[str] | None = None,
) -> dict[str, Any]:
    decision_paths = _decision_refs(project, list(decisions or []))
    root, _ = _writable_path(project)
    extra = ("" if not decision_paths else
             " · dec=" + ",".join(_rel_or_abs(path, root) for path in decision_paths))
    result = _mutate_item(
        project, item_id, "complete", log=log, evidence=evidence,
        no_artifact_reason=no_artifact_reason, log_extra=extra,
    )
    reminder = _gate_reminder(project, item_id)
    if reminder:
        result["gate_reminder"] = reminder
        result["next_hint"] = reminder
    if commit or merge:
        result["git"] = _complete_git(project, item_id, commit=commit, merge=merge,
                                      decisions=decision_paths)
        if _git_failed(result["git"]):
            result["verdict"] = "warn"
            result["next_hint"] = "计划已完成，但 Git 步骤失败：按 git.* 的 error 处理后手动提交/合并"
        else:
            shas = [c["commit"] for c in result["git"].get("commits", []) if c.get("commit")]
            if shas and _stamp_log_commit(result.get("log"), shas[0]):
                result["git"]["log_commit_stamped"] = shas[0]
    return result


def _rel_or_abs(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def _gate_reminder(project: str, item_id: str) -> str | None:
    """Non-blocking: a task that declared gates should cite their verification result as evidence."""
    _, path = _plan_path(project)
    item = parse_plan(path).by_id().get(item_id)
    if item is None or not item.gates:
        return None
    cited = " ".join([*item.evidence, item.no_artifact_reason])
    missing = [gate for gate in item.gates if gate not in cited]
    if not missing:
        return None
    return (f"{item_id} 声明了验收 gate：{'；'.join(missing)}。证据里若还没有它的验证结果，"
            f"用 plan note {project} \"gate 结果: <命令输出摘要或报告路径>\" --id {item_id} 补一条")


def _task_pathspecs(root: Path, top: Path, item: PlanItem) -> list[str]:
    """Repo-relative paths named by the task's scope/gate/evidence (`path:`/`test:` or bare paths).

    Evidence may also cite an existing file without a slash or by absolute path inside
    the repository. Ignored files never reach `git add` (status does not list them).
    """
    specs = []
    evidence = set(item.evidence)
    for value in [*item.scopes, *item.gates, *item.evidence]:
        cited = value in evidence
        kind, _, rest = value.partition(":")
        if rest and kind in {"path", "test"}:
            value = rest
        elif value.startswith("/") and cited:
            pass
        elif rest or ("/" not in value and not (cited and (root / value.strip()).is_file())):
            continue
        value = value.split("::", 1)[0].strip()
        if not value or any(ch.isspace() for ch in value):  # free-text gate / command, not a path
            continue
        if ".." in Path(value).parts or (value.startswith("/") and not cited):
            continue
        try:
            specs.append(str((root / value).resolve().relative_to(top.resolve())))
        except ValueError:
            continue
    return list(dict.fromkeys(specs))


def _plan_files(top: Path, plan_path: Path) -> list[str]:
    """Plan file + the TOP directory (`_top/` or `top/`: findings, decisions, logs, plans, goals…).

    A plan living elsewhere only brings its log directory, so the repository root is
    never swept in. Ignored files never show up (status does not list them).
    """
    scope = plan_path.parent if plan_path.parent.name in ("_top", "top") else _log_dir(plan_path)
    return [str(plan_path.resolve().relative_to(top.resolve())),
            str(scope.resolve().relative_to(top.resolve()))]


def _plan_changed(repo: Path, plan_files: list[str]) -> list[str]:
    """Changed paths under the plan pathspecs, minus ignore-class files (credentials, caches, temp, large)."""
    paths = top_git.changed_paths(repo, plan_files)
    try:
        classes = top_track.classify_paths(repo, paths)
    except top_track.TrackError:   # bad top.trackLargeMB: still drop credentials/caches (reported by track)
        classes = top_track.classify_paths(repo, paths, top_track.LARGE_MB_DEFAULT * top_track.MB)
    return [path for path, action, _ in classes if action != "ignore"]


def _git_failed(git_result: dict[str, Any]) -> bool:
    parts = [git_result, *git_result.get("commits", []), git_result.get("merge") or {}]
    return any(isinstance(part, dict) and "error" in part for part in parts)


def _complete_git(project: str, item_id: str, *, commit: bool, merge: bool,
                  decisions: list[Path] | None = None) -> dict[str, Any]:
    """Commit the task's own files (+ plan/log) and optionally merge its task branch.

    Main-line task: one commit with code + plan + log. Worktree task: code commit on
    `task/<ID>`, merge into the main branch (with --merge), then the plan/log commit
    on the main branch so the plan is never branched.
    """
    root, path = _plan_path(project)
    main = top_git.main_worktree(root)
    if main is None:
        return {"error": "not a git repository"}
    item = parse_plan(path).by_id()[item_id]
    subject = f"{item_id} {item.title}"
    checkout = (top_git.task_checkout(main, item_id)
                or top_git.toplevel(Path(project).resolve()) or main)
    try:
        specs = _task_pathspecs(root, main, item)
        plan_files = _plan_files(main, path)
        decision_refs = [str(p.relative_to(main.resolve())) for p in decisions or []]
    except ValueError:
        return {"error": "plan or decision file is outside the git repository"}
    trailers = [("Decision", ref) for ref in decision_refs]
    plan_files += [ref for ref in decision_refs if ref not in plan_files]
    out: dict[str, Any] = {"checkout": str(checkout), "commits": []}
    code_paths = top_git.changed_paths(checkout, specs) if commit else []
    if not specs and commit:
        out["warning"] = "任务没有 path:/test: scope 或证据路径，只提交计划与日志"
    if checkout != main:
        if commit:
            out["commits"].append(top_git.commit_paths(checkout, code_paths, item_id, subject, trailers))
        if merge:
            out["merge"] = top_git.merge_task(main, item_id, item.title)
            if "error" not in out["merge"] and "skipped" not in out["merge"]:
                _append_log_line(path, f"merge {item_id} {item.title} · ev={out['merge'].get('merge')} "
                                       f"{out['merge']['branch']}→{out['merge']['into']}")
        plan_paths = _plan_changed(main, plan_files)
        out["commits"].append(top_git.commit_paths(main, plan_paths, item_id, f"{subject} [plan]", trailers))
    else:
        if merge:
            out["merge"] = {"skipped": "任务没有独立 worktree 分支，已在主线上"}
        paths = code_paths + [p for p in _plan_changed(main, plan_files) if p not in code_paths]
        out["commits"].append(top_git.commit_paths(main, paths, item_id, subject, trailers))
    committed = {p for c in out["commits"] for p in c.get("paths", [])}
    leftover = [p for p in top_git.dirty_paths(checkout) if p not in committed]
    if leftover:
        out["uncommitted_outside_scope"] = _leftover_summary(checkout, leftover)
        if out["uncommitted_outside_scope"].get("authored_sample"):
            repo = shlex.quote(str(checkout))
            out["track_hint"] = (f"范围外还有 {out['uncommitted_outside_scope']['by_class']['commit']} 份写出来的文件没提交："
                                 f"跑 sixone-cli.py track {repo} 分拣后补进任务 scope 或单独提交（这里不自动提交）")
    return out


def _leftover_summary(checkout: Path, leftover: list[str]) -> dict[str, Any]:
    """count/sample of dirty files left out of the commit, plus their track classes."""
    summary: dict[str, Any] = {"count": len(leftover), "sample": leftover[:5]}
    try:
        classes = top_track.classify_paths(checkout, leftover)
    except top_track.TrackError as exc:
        summary["by_class_error"] = str(exc)
        return summary
    by_class = {"commit": 0, "ignore": 0, "review": 0}
    for _, action, _ in classes:
        by_class[action] += 1
    summary["by_class"] = by_class
    summary["authored_sample"] = [path for path, action, _ in classes if action == "commit"][:5]
    return summary


def merge(project: str, item_id: str) -> dict[str, Any]:
    """Merge `task/<ID>` into the main worktree's branch and commit the log line."""
    root, path = _plan_path(project)
    item = parse_plan(path).by_id().get(item_id)
    if item is None:
        raise PlanError(f"unknown task id: {item_id}")
    main = top_git.main_worktree(root)
    if main is None:
        raise PlanError("not a git repository")
    merged = top_git.merge_task(main, item_id, item.title)
    result = {"schema_version": SCHEMA_VERSION, "tool": "plan-merge", "item_id": item_id, "git": merged,
              "verdict": "warn" if "error" in merged else "ok"}
    if "error" in merged or "skipped" in merged:
        result["next_hint"] = merged.get("error") or merged.get("skipped")
        return result
    _append_log_line(path, f"merge {item_id} {item.title} · ev={merged.get('merge')} {merged['branch']}→{merged['into']}")
    result["log_commit"] = top_git.commit_paths(
        main, _plan_changed(main, _plan_files(main, path)), item_id, f"{item_id} merged [plan]")
    if not item.closed:
        result["next_hint"] = f"已合并；任务仍是 {item.state}，完成后用 plan complete {item_id}"
    return result


def handoff(project: str, doc: str, *, commit: bool = True) -> dict[str, Any]:
    """Log a handoff document and commit it with the plan log under a `Handoff:` trailer.

    The document stays a snapshot; the plan remains the only live state. `plan show`
    finds the latest handoff through Git (`last_handoff`).
    """
    root, path = _plan_path(project)
    if not path.is_file():
        raise PlanError(f"task plan not found: {path}")
    doc_path = (Path(doc) if Path(doc).is_absolute() else root / doc).resolve()
    if not doc_path.is_file():
        raise PlanError(f"handoff document not found: {doc}")
    doc_rel = _rel_or_abs(doc_path, root)
    if " · " in doc_rel or any(ch in doc_rel for ch in "\r\n"):
        raise PlanError("handoff path must be one line without ' · '")
    state = parse_plan(path)
    current = next((item for item in state.items if item.state == "in_progress"), None)
    item_id = current.id if current else None
    result: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "tool": "plan-handoff", "verdict": "ok",
                              "item_id": item_id, "handoff": doc_rel}
    result["log"] = _append_log_line(path, f"handoff {item_id or 'plan'} {doc_rel} · ev={doc_rel}")
    if commit:
        main = top_git.main_worktree(root)
        if main is None:
            result.update(verdict="warn", next_hint="不是 git 仓库：交接已记入日志，未提交")
            return result
        try:
            repo_ref = str(doc_path.relative_to(main.resolve()))
            files = [repo_ref, *_plan_files(main, path)]
        except ValueError:
            raise PlanError("handoff document and plan must be inside the main worktree")
        changed = _plan_changed(main, files)
        result["git"] = top_git.commit_paths(main, changed, item_id, f"handoff: {doc_path.stem}",
                                             [("Handoff", repo_ref)])
        if "error" in result["git"]:
            result["verdict"] = "warn"
        elif result["git"].get("commit"):
            _stamp_log_commit(result["log"], result["git"]["commit"])
    result["next_hint"] = "接手者用 plan show 看 last_handoff，再读该交接文件核对现场"
    return result


def milestone(project: str, phase: str, *, allow_open: bool = False) -> dict[str, Any]:
    """Annotated tag `top/<phase>` at HEAD whose message lists the phase's closed tasks."""
    root, path = _writable_path(project)
    if not path.is_file():
        raise PlanError(f"task plan not found: {path}")
    if not re.fullmatch(r"P\d+(?:\.[A-Za-z0-9]+)*", phase):
        raise PlanError(f"invalid phase id: {phase}")
    main = top_git.main_worktree(root)
    if main is None:
        raise PlanError("not a git repository")
    state = parse_plan(path)
    members = [item for item in state.items if item.id.startswith(phase + ".")]
    archive_file = _log_dir(path) / ARCHIVE_NAME
    archived = []
    if archive_file.is_file():  # tasks moved out by `plan archive` still belong to the phase
        task_lines = [line for line in archive_file.read_text(encoding="utf-8", errors="ignore").splitlines()
                      if line.lstrip().startswith(("- [", "* ["))]
        parsed = parse_plan_text(path, "## Active Work\n\n" + "\n".join(task_lines) + "\n").items
        known = {m.id for m in members}
        archived = [item for item in parsed if item.id.startswith(phase + ".") and item.id not in known]
    everything = archived + members
    if not everything:
        raise PlanError(f"no tasks under phase {phase}")
    still_open = [item.id for item in everything if not item.closed]
    if still_open and not allow_open:
        raise PlanError(f"phase {phase} still has open tasks: {', '.join(still_open[:8])}; "
                        "finish/cancel them or pass --allow-open")

    def line(item: PlanItem) -> str:
        ev = ",".join(item.evidence) or (f"no_artifact:{item.no_artifact_reason}" if item.no_artifact_reason else "")
        why = item.reason if item.state == "cancelled" else ev
        return f"- {item.id} {item.title}" + (f" ({why})" if why else "")

    groups = [("Done", [i for i in everything if i.state == "done"]),
              ("Cancelled", [i for i in everything if i.state == "cancelled"]),
              ("Still open", [i for i in everything if not i.closed])]
    goal = state.coordinate.get("goal") or ""
    body = [f"TOP milestone {phase}" + (f": {goal}" if goal else ""), ""]
    for label, items in groups:
        if items:
            body += [f"{label} ({len(items)}):", *(line(i)[:300] for i in items), ""]
    dirty = len(top_git.dirty_paths(main, untracked="normal"))
    tag = top_git.create_tag(main, f"top/{phase}", "\n".join(body).rstrip() + "\n")
    result: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "tool": "plan-milestone", "phase": phase,
                              "git": tag, "done": len(groups[0][1]), "cancelled": len(groups[1][1]),
                              "open": still_open, "verdict": "warn" if "error" in tag else "ok"}
    if "error" in tag:
        result["next_hint"] = tag["error"]
        return result
    result["log"] = _append_log_line(path, f"milestone {phase} tag=top/{phase}@{tag['commit']}"
                                           f" done={len(groups[0][1])} cancelled={len(groups[1][1])}")
    result["next_hint"] = (f"已打 tag top/{phase}（指向 {tag['commit']}）；`git show top/{phase}` 看阶段摘要"
                           + (f"；注意工作区还有 {dirty} 个未提交改动不在 tag 里" if dirty else ""))
    return result


def note(project: str, text: str, *, item_id: str | None = None, kind: str = "progress") -> dict[str, Any]:
    """One-line mid-task note (progress / fail / learn) in today's plan log.

    `learn` also becomes the Current Coordinate's Latest learning. Notes of the
    current/next task are shown by plan show and the session hints.
    """
    root, path = _plan_path(project)
    if not path.is_file():
        raise PlanError(f"task plan not found: {path}")
    qa = _qa(path)
    if qa is not None:
        return qa.note(project, text, on=item_id, kind=kind)
    if kind not in NOTE_KINDS:
        raise PlanError(f"kind must be one of {', '.join(NOTE_KINDS)}")
    text = _one_line(text)
    if not text or " · " in text:
        raise PlanError("note must be non-empty and must not contain ' · '")
    state = parse_plan(path)
    if item_id is None:
        current = next((item for item in state.items if item.state == "in_progress"), None)
        item_id = current.id if current else "plan"
    elif item_id not in state.by_id():
        raise PlanError(f"unknown task id: {item_id}")
    result: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "tool": "plan-note", "verdict": "ok",
                              "item_id": item_id, "kind": kind}
    if kind == "learn" and not state.outline:   # outline plans keep learnings in the log only
        lines = list(state.lines)
        _replace_coordinate(lines, "latest_learning", text)
        atomic_replace_plan(path, state.sha256, "\n".join(lines).rstrip() + "\n")
        result["latest_learning"] = text
    result["log"] = _append_log_line(path, f"note:{kind} {item_id} {text}")
    if len(text) > NOTE_CHARS_BUDGET:
        result["verdict"] = "warn"
        result["warnings"] = [f"笔记 {len(text)} 字 > {NOTE_CHARS_BUDGET} 字预算（已写入）"]
        result["next_hint"] = "下次只写一句话结论+证据路径；长复盘写进 _logs/<date>-<topic>.md 再在 note 里链接"
    if kind == "fail" and item_id != "plan":
        # 3-strike protocol (absorbed from planning-with-files): the third failure of one task
        # means stop and ask the user, listing the three approaches tried and their results.
        count = _fail_count(path, item_id)
        result["fail_count"] = count
        if count >= FAIL_ESCALATE_AT:
            result["verdict"] = "warn"
            result["escalate"] = True
            result["next_hint"] = f"同一任务已失败 {count} 次：停下来找用户，列出试过的三种做法和各自结果"
        else:
            result["escalate"] = False
    return result


def next_tasks(project: str) -> dict[str, Any]:
    """Pending tasks whose dependencies are all closed (done/cancelled), in plan order."""
    root, path = _plan_path(project)
    if not path.is_file():
        return {"error": f"task plan not found: {path}"}
    state = parse_plan(path)
    by_id = state.by_id()
    current = next((item for item in state.items if item.state == "in_progress"), None)
    ready, waiting = [], []
    for item in state.items:
        if item.state != "pending":
            continue
        open_deps = [dep for dep in item.deps if dep not in by_id or not by_id[dep].closed]
        if open_deps:
            waiting.append({"id": item.id, "title": item.title, "waiting_on": open_deps})
        else:
            ready.append({"id": item.id, "title": item.title, "gates": item.gates})
    blocked = [item.id for item in state.items if item.state == "blocked"]
    if current:
        hint = f"已有进行中任务 {current.id}；完成或 block 后再 plan start 下一个"
    elif ready:
        hint = f"plan start {root} {ready[0]['id']}"
    else:
        hint = "没有依赖已就绪的待办；看 waiting/blocked 或 plan add"
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": "plan-next",
        "project": str(root),
        "lightweight": is_lightweight(state),
        "current": _item_dict(current) if current else None,
        "ready": ready,
        "waiting": waiting,
        "blocked": blocked,
        "errors": _error_dicts(state),
        "verdict": "ok",
        "next_hint": hint,
    }


def archive(project: str, *, keep: int = 5) -> dict[str, Any]:
    """Move closed task groups out of Active Work into `_logs/plan-archive.md`.

    Keeps the `keep` most recent closed groups, anything an open task depends on,
    and any group that still has an open descendant.
    """
    root, path = _writable_path(project)
    state = parse_plan(path)
    _require_clean_state(state)
    if state.outline:
        return _archive_outline(path, state, keep)
    items = state.items
    roots = [item for item in items if not any(item.id.startswith(o.id + ".") for o in items if o is not item)]
    groups = {r.id: [i for i in items if i.id == r.id or i.id.startswith(r.id + ".")] for r in roots}
    closed = [rid for rid, members in groups.items() if all(m.closed for m in members)]
    candidates = closed[:-keep] if keep > 0 else closed
    changed = True
    while changed:
        changed = False
        archived_ids = {m.id for rid in candidates for m in groups[rid]}
        needed = {dep for item in items if item.id not in archived_ids for dep in item.deps}
        for rid in list(candidates):
            if any(m.id in needed for m in groups[rid]):
                candidates.remove(rid)
                changed = True
    if not candidates:
        return {"schema_version": SCHEMA_VERSION, "tool": "plan-archive", "verdict": "ok", "archived": 0,
                "next_hint": "没有可归档的已关闭任务"}
    drop = {m.line_index for rid in candidates for m in groups[rid]}
    moved = [state.lines[i] for i in sorted(drop)]
    new_text = "\n".join(line for i, line in enumerate(state.lines) if i not in drop).rstrip() + "\n"
    archive_path = _log_dir(path) / ARCHIVE_NAME
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    header = "" if archive_path.is_file() else "# Active Work 归档（plan archive 移出的已关闭任务）\n"
    with archive_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{header}\n## {datetime.now():%Y-%m-%d %H:%M} 归档 {len(moved)} 项\n\n" + "\n".join(moved) + "\n")
    result = _write_mutation(state, new_text, "archive", ",".join(candidates))
    result["archived"] = len(moved)
    result["archive_file"] = str(archive_path)
    _append_log_line(path, f"archive plan {len(moved)} 项已关闭任务移入 {ARCHIVE_NAME}")
    return result


def _archive_outline(path: Path, state, keep: int) -> dict[str, Any]:
    """Outline plans: fold closed phases. Their step lines move to `_logs/plan-archive.md`; the
    heading (with its ✅/✕) and the one-sentence summary stay, so the table of contents keeps
    every phase. The `keep` most recent closed phases keep their steps."""
    items = state.items
    closed = [phase for phase in state.phases
              if phase_steps(phase, items) and phase_state(phase, items) in ("done", "cancelled")]
    candidates = closed[:-keep] if keep > 0 else list(closed)
    members = {phase.id: {step.id for step in phase_steps(phase, items)} for phase in candidates}
    changed = True
    while changed:
        changed = False
        archived = set().union(*(members[phase.id] for phase in candidates))
        needed = {dep for item in items if item.id not in archived for dep in item.deps}
        for phase in list(candidates):
            if members[phase.id] & needed:
                candidates.remove(phase)
                changed = True
    if not candidates:
        return {"schema_version": SCHEMA_VERSION, "tool": "plan-archive", "verdict": "ok", "archived": 0,
                "next_hint": "没有可收起的已完成阶段"}
    lines = list(state.lines)
    drop: set[int] = set()
    for phase in candidates:
        lines[phase.line_index] = render_phase_heading(phase, phase_state(phase, items))
        drop.update(step.line_index for step in phase_steps(phase, items))
    moved = [state.lines[index] for index in sorted(drop)]
    kept: list[str] = []
    for index, line in enumerate(lines):
        if index in drop or (not line.strip() and kept and not kept[-1].strip()):
            continue
        kept.append(line)
    parsed = parse_plan_text(path, "\n".join(kept).rstrip() + "\n")
    new_text = render_plan_with_mirrors(parsed, parsed.items)
    archive_path = _log_dir(path) / ARCHIVE_NAME
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    header = "" if archive_path.is_file() else "# Active Work 归档（plan archive 移出的已关闭任务）\n"
    titles = "、".join(f"{phase.id} {phase.title}" for phase in candidates)
    with archive_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{header}\n## {datetime.now():%Y-%m-%d %H:%M} 收起阶段 {titles}（{len(moved)} 步）\n\n"
                     + "\n".join(line.strip() for line in moved) + "\n")
    result = _write_mutation(state, new_text, "archive", ",".join(phase.id for phase in candidates))
    result["archived"] = len(moved)
    result["archived_phases"] = [phase.id for phase in candidates]
    result["archive_file"] = str(archive_path)
    _append_log_line(path, f"archive plan 收起阶段 {titles}：{len(moved)} 步移入 {ARCHIVE_NAME}")
    return result


def block(project: str, item_id: str, reason: str, *, log: bool = True) -> dict[str, Any]:
    return _mutate_item(project, item_id, "block", log=log, reason=reason)


def reopen(project: str, item_id: str, *, log: bool = True) -> dict[str, Any]:
    return _mutate_item(project, item_id, "reopen", log=log)


def cancel(project: str, item_id: str, reason: str, *, log: bool = True) -> dict[str, Any]:
    return _mutate_item(project, item_id, "cancel", log=log, reason=reason)


# ---------- changing the plan: insert a step, switch route (replan) ----------

def _archived_ids(plan_path: Path) -> set[str]:
    """IDs moved to `_logs/plan-archive.md`: still referenced by `Task:` trailers, never reused."""
    archive_path = _log_dir(plan_path) / ARCHIVE_NAME
    if not archive_path.is_file():
        return set()
    ids = set()
    for line in archive_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = TASK_LINE_RE.match(line)
        if match:
            ids.add(match.group(2))
    return ids


def _inserted_id(after_id: str, used: set[str]) -> str:
    """ID for a sibling inserted after `after_id`, without renumbering anything.

    `<AFTER_ID>` + the first free lowercase letter: `P1.2` → `P1.2a`, then `P1.2b`…; an ID that
    already ends in digit+letter keeps its stem (`P1.2a` → `P1.2b`). Same parent prefix, so the
    card tree and `--parent` hierarchy see a sibling; the letter never promises order — the line
    order in Active Work does.
    """
    head, _, last = after_id.rpartition(".")
    match = _INSERTED_SEGMENT_RE.match(last)
    stem = f"{head}.{match.group(1)}" if match else after_id
    for letter in INSERT_LETTERS:
        candidate = stem + letter
        if candidate not in used and not any(other.startswith(candidate + ".") for other in used):
            return candidate
    raise PlanError(f"no free inserted id left after {after_id} ({stem}a…{stem}z all used)")


def _subtree_end(items: list[PlanItem], item_id: str) -> int:
    """Line index of the last line of `item_id` and its descendants."""
    return max(item.line_index for item in items
               if item.id == item_id or item.id.startswith(item_id + "."))


def _rewire(items: list[PlanItem], old_id: str, new_id: str) -> list[str]:
    """Pending/blocked tasks depending on `old_id` now depend on `new_id` (in place).

    A task already in progress started on the old dependency and is left alone."""
    rewired = []
    for item in items:
        if item.id == new_id or item.state not in {"pending", "blocked"} or old_id not in item.deps:
            continue
        item.deps = [new_id if dep == old_id else dep for dep in item.deps]
        item.deps = list(dict.fromkeys(item.deps))
        rewired.append(item.id)
    return rewired


def _render_with_inserts(state, items: list[PlanItem], after_line: int, new_items: list[PlanItem]) -> str:
    lines = list(state.lines)
    for item in items:
        lines[item.line_index] = render_plan_item(item, outline=state.outline)
    lines[after_line + 1:after_line + 1] = [render_plan_item(item, outline=state.outline) for item in new_items]
    parsed = parse_plan_text(state.path, "\n".join(lines).rstrip() + "\n")
    return render_plan_with_mirrors(parsed, parsed.items)


def _next_label(project: str) -> str:
    shown = show(project, fast=True)
    current, nxt = shown.get("current"), shown.get("next")
    focus = f"进行中 {current['id']}" if current else ""
    upcoming = f"下一步 {nxt['id']} {nxt['title']}" if nxt else "没有依赖已就绪的待办"
    return "；".join(part for part in (focus, upcoming) if part)


def insert(
    project: str, after_id: str, *, title: str, gates: list[str] | None = None,
    reason: str | None = None, rewire: bool = False, log: bool = True,
) -> dict[str, Any]:
    """Insert a sibling task right after `after_id` and its subtree (PWF-style "phase 2.5").

    `rewire`: the new task depends on `after_id`, and pending/blocked tasks that depended on
    `after_id` now depend on the new task. `reason` goes to the log and the change summary,
    not into the plan line.
    """
    _, path = _writable_path(project)
    state = parse_plan(path)
    _require_clean_state(state)
    items = copy.deepcopy(state.items)
    by_id = {item.id: item for item in items}
    after = by_id.get(after_id)
    if after is None:
        raise PlanError(f"unknown task id: {after_id}")
    reason = _plan_value(reason or "", "--reason", allow_empty=True, terminal=True)
    new = PlanItem(
        id=_inserted_id(after_id, set(by_id) | _archived_ids(path)),
        title=_clean_title(title), checked=False, state="pending", line_index=-1,
        deps=[after_id] if rewire else [],
        gates=_clean_metadata_values(list(gates or []), "gate"),
    )
    rewired = _rewire(items, after_id, new.id) if rewire else []
    new_text = _render_with_inserts(state, items, _subtree_end(state.items, after_id), [new])
    result = _write_mutation(state, new_text, "insert", new.id)
    result.update(inserted=[_item_dict(new)], after=after_id, rewired=rewired)
    if log:
        extra = f" · rewire={','.join(rewired)}" if rewired else ""
        result["log"] = _append_log_line(
            path, f"insert {new.id} {new.title} · after={after_id} · ev={reason or '-'}{extra}")
    gate_text = f"，验收：{'；'.join(new.gates)}" if new.gates else ""
    impact = (f"{'、'.join(rewired)} 原依赖 {after_id}，现改为依赖 {new.id}（{new.id} 依赖 {after_id}）"
              if rewired else
              "没有任务改依赖" + (f"（{new.id} 依赖 {after_id}）" if rewire else f"，{new.id} 按计划顺序排在 {after_id} 之后"))
    result["change_summary"] = [
        f"改了什么：在 {after_id}「{after.title}」之后插入 {new.id}「{new.title}」{gate_text}",
        f"为什么：{reason}" if reason else "为什么：未填写（下次用 --reason 写一句原因）",
        f"影响哪些后续任务：{impact}；{_next_label(project)}",
    ]
    return result


def replan(
    project: str, item_id: str, *, reason: str, replace_with: list[str],
    gates: list[str] | None = None, log: bool = True,
) -> dict[str, Any]:
    """Switch route: cancel `item_id` ("换路线：<reason>") and put replacements where it was.

    Replacements get `<ID>a`, `<ID>b`… and are chained (the first inherits the old task's
    dependencies, each next one depends on the previous); the last one carries the old gates
    (or `gates` when given), since the acceptance criterion outlives the route. Pending/blocked
    tasks that depended on `item_id` move to the last replacement. Also records a
    `note --kind fail` on `item_id`, which counts toward its 3-strike escalation.
    """
    _, path = _writable_path(project)
    state = parse_plan(path)
    _require_clean_state(state)
    items = copy.deepcopy(state.items)
    by_id = {item.id: item for item in items}
    old = by_id.get(item_id)
    if old is None:
        raise PlanError(f"unknown task id: {item_id}")
    if old.closed:
        raise PlanError(f"task is already closed: {item_id}; add follow-up work with plan insert")
    open_children = [child.id for child in items if child.id.startswith(item_id + ".") and not child.closed]
    if open_children:
        raise PlanError(f"open children prevent replan: {', '.join(open_children)}; "
                        "replan or cancel them first")
    reason = _plan_value(reason or "", "--reason", terminal=True)
    titles = [_clean_title(title) for title in replace_with or []]
    if not titles:
        raise PlanError("replan requires at least one --replace-with")
    old_title = old.title
    old.state, old.checked, old.reason = "cancelled", True, f"换路线：{reason}"
    used = set(by_id) | _archived_ids(path)
    new_items: list[PlanItem] = []
    deps, anchor = list(old.deps), item_id
    for title in titles:
        new_id = _inserted_id(anchor, used)
        used.add(new_id)
        new_items.append(PlanItem(id=new_id, title=title, checked=False, state="pending",
                                  line_index=-1, deps=deps, dep_style=old.dep_style))
        deps, anchor = [new_id], new_id
    last = new_items[-1]
    last.gates = _clean_metadata_values(list(gates), "gate") if gates else list(old.gates)
    rewired = _rewire(items, item_id, last.id)
    new_text = _render_with_inserts(state, items, _subtree_end(state.items, item_id), new_items)
    result = _write_mutation(state, new_text, "replan", item_id)
    new_ids = [item.id for item in new_items]
    result.update(cancelled=item_id, inserted=[_item_dict(item) for item in new_items], rewired=rewired)
    if log:
        result["log"] = _append_log_line(
            path, f"replan {item_id} {old_title} · ev={old.reason} · to={','.join(new_ids)}")
    fail = note(project, f"换路线：{reason}".replace(" · ", "；"), item_id=item_id, kind="fail")
    result["note"] = {key: fail.get(key) for key in ("log", "fail_count", "escalate")}
    chain = " → ".join(f"{item.id}「{item.title}」" for item in new_items)
    impact = (f"{'、'.join(rewired)} 原依赖 {item_id}，现改为依赖 {last.id}" if rewired
              else f"没有开放任务依赖 {item_id}")
    result["change_summary"] = [
        f"改了什么：{item_id}「{old_title}」标为取消（换路线），改由 {chain} 依次接替"
        + (f"，验收：{'；'.join(last.gates)}" if last.gates else ""),
        f"为什么：{reason}",
        f"影响哪些后续任务：{impact}；{_next_label(project)}",
    ]
    if fail.get("escalate"):
        result["escalate"] = True
        result["verdict"] = "warn"
        result["next_hint"] = fail["next_hint"]
    return result


# ---------- outline plans: goal, phases, migration ----------

MIGRATE_LINK = "_task_plan.before-migrate.md"
# Technical details of the phases (numbers, experiment IDs, paths, evidence, old-ID mapping) live in
# one companion article next to the plan, one `## P<n> …` section per phase; the plan stays readable.
DETAILS_NAME = "_plan_details.md"


def _outline_state(project: str):
    root, path = _writable_path(project)
    if not path.is_file():
        raise PlanError(f"task plan not found: {path}")
    state = parse_plan(path)
    if state.format == "qa":
        raise PlanError("这是问答格式的计划，没有阶段：用 plan ask / answer / add / done …（plan help）")
    if not state.outline:
        raise PlanError("这是旧格式计划（Active Work 清单），没有阶段目录：先按 references/plan-writing.md "
                        "改写，再用 plan migrate 替换")
    _require_clean_state(state)
    return root, path, state


def _prose(value: str, label: str) -> str:
    """Goal / phase summary: one line of plain text that cannot open a heading or a step."""
    value = _plan_value(value, label, allow_empty=True, terminal=True)
    if re.match(r"^(#|[-*+]\s+\[[ xX]\])", value):
        raise PlanError(f"{label} 不能以 # 或勾选框开头（会被当成标题/步骤，打乱目录）")
    return value


def _phase_title(title: str) -> str:
    cleaned = strip_phase_marks(_clean_title(title))
    if not cleaned:
        raise PlanError("阶段名不能只有状态记号")
    return cleaned


def _phase_number(value: str) -> int:
    match = re.match(r"^P(\d+)", value)
    return int(match.group(1)) if match else 0


def _write_outline(state, lines: list[str], action: str, target: str, log_body: str) -> dict[str, Any]:
    parsed = parse_plan_text(state.path, "\n".join(lines).rstrip() + "\n")
    result = _write_mutation(state, render_plan_with_mirrors(parsed, parsed.items), action, target)
    result["log"] = _append_log_line(state.path, log_body)
    return result


def _summary_span(state, phase: PlanPhase) -> tuple[int, int]:
    """Lines between a phase heading and its first step (or the phase end)."""
    first_step = min((item.line_index for item in state.items if item.section == phase.id), default=phase.end)
    return phase.line_index + 1, first_step


def phase_add(project: str, *, title: str, summary: str | None = None,
              after: str | None = None) -> dict[str, Any]:
    """New `### P<n>` phase (n = one above every phase/step number in the plan), at the end of the
    table of contents or right after phase `after`. Steps go in with `plan add --parent P<n>`."""
    _, _, state = _outline_state(project)
    title = _phase_title(title)
    summary = _prose(summary or "", "--summary")
    # headings stay after `plan archive`, so current phases + steps cover every number in use;
    # step IDs of older (pre-migration) archives are skipped by `plan add` itself
    used = [phase.id for phase in state.phases] + [item.id for item in state.items]
    phase_id = f"P{max([_phase_number(value) for value in used] + [0]) + 1}"
    lines = list(state.lines)
    if after:
        anchor = next((phase for phase in state.phases if phase.id == after), None)
        if anchor is None:
            raise PlanError(f"unknown phase id: {after}")
        at = anchor.end
    else:
        at = state.active_end if state.active_end is not None else len(lines)
    while at > (state.active_start or 0) + 1 and not lines[at - 1].strip():
        at -= 1
    block = ["", f"### {phase_id} {title} ⏳"] + (["", summary] if summary else []) + [""]
    lines[at:at] = block
    result = _write_outline(state, lines, "phase-add", phase_id, f"phase-add {phase_id} {title}")
    result["phase_id"] = phase_id
    result["next_hint"] = f"用 plan add {state.path.parents[2]} --parent {phase_id} --title '<一步，一句人话>' 加步骤"
    return result


def phase_edit(project: str, phase_id: str, *, title: str | None = None,
               summary: str | None = None) -> dict[str, Any]:
    """Rename a phase or rewrite its one-sentence summary (why this phase / what it gave the next)."""
    _, _, state = _outline_state(project)
    phase = next((p for p in state.phases if p.id == phase_id), None)
    if phase is None:
        raise PlanError(f"unknown phase id: {phase_id}")
    if title is None and summary is None:
        raise PlanError("phase edit 需要 --title 或 --summary")
    lines = list(state.lines)
    if summary is not None:
        text = _prose(summary, "--summary")
        start, end = _summary_span(state, phase)
        lines[start:end] = ["", text, ""] if text else [""]
    if title is not None:
        phase.title = _phase_title(title)
        lines[phase.line_index] = render_phase_heading(phase, phase_state(phase, state.items))
    changed = "、".join(part for part, value in (("标题", title), ("小结", summary)) if value is not None)
    return _write_outline(state, lines, "phase-edit", phase_id, f"phase-edit {phase_id} {phase.title} · 改{changed}")


def phase_cancel(project: str, phase_id: str, *, reason: str) -> dict[str, Any]:
    """Drop a whole route: every open step of the phase is cancelled with "阶段放弃：<reason>"."""
    _, _, state = _outline_state(project)
    phase = next((p for p in state.phases if p.id == phase_id), None)
    if phase is None:
        raise PlanError(f"unknown phase id: {phase_id}")
    reason = _plan_value(reason or "", "--reason", terminal=True)
    items = copy.deepcopy(state.items)
    dropped = []
    for item in items:
        if item.id.startswith(phase_id + ".") and not item.closed:
            item.state, item.checked, item.reason = "cancelled", True, f"{PHASE_DROP_PREFIX}{reason}"
            item.no_artifact_reason = ""
            dropped.append(item.id)
    if not dropped and phase_steps(phase, state.items):
        raise PlanError(f"{phase_id} 没有未关闭的步骤")
    if not phase_steps(phase, state.items):
        phase.mark = "✕"
    waiting = [item.id for item in items if not item.closed and any(dep in dropped for dep in item.deps)]
    new_text = render_plan_with_mirrors(state, items)
    result = _write_mutation(state, new_text, "phase-cancel", phase_id)
    result["cancelled"] = dropped
    result["log"] = _append_log_line(state.path, f"phase-cancel {phase_id} {phase.title} · ev={reason}"
                                     + (f" · steps={','.join(dropped)}" if dropped else ""))
    if waiting:
        result["verdict"] = "warn"
        result["next_hint"] = f"{'、'.join(waiting)} 还依赖被放弃的步骤：用 plan edit --remove-dep 改依赖或一并取消"
    return result


def set_goal(project: str, text: str) -> dict[str, Any]:
    """Rewrite `## 目标`: one or two plain sentences on what "done" looks like."""
    _, _, state = _outline_state(project)
    text = _prose(text, "goal")
    if not text:
        raise PlanError("goal 不能为空")
    lines = list(state.lines)
    start, end = _section_bounds(lines, GOAL_HEADING_RE)
    if start is None:
        at = next((i + 1 for i, line in enumerate(lines) if line.startswith("# ")), 0)
        lines[at:at] = ["", "## 目标", "", text]
    else:
        lines[start + 1:end] = ["", text, ""]
    return _write_outline(state, lines, "goal", "plan", f"goal plan {text}")


def migrate(project: str, source: str, *, apply: bool = False, accept_dropped: bool = False) -> dict[str, Any]:
    """Replace the plan with an outline draft written by the AI (old format → 目录格式, or a
    rewrite of an outline plan). Preview by default. The draft must parse cleanly; open tasks of
    the old plan that the draft no longer lists are reported and need --accept-dropped. The old
    text is kept in `_logs/plan-history/` (link `_task_plan.before-migrate.md`)."""
    root, path = _writable_path(project)
    if not path.is_file():
        raise PlanError(f"task plan not found: {path}")
    draft_path = Path(source) if Path(source).is_absolute() else root / source
    if not draft_path.is_file():
        raise PlanError(f"draft not found: {source}")
    old = parse_plan(path)
    draft = parse_plan_text(path, draft_path.read_text(encoding="utf-8"))
    if not draft.outline:
        raise PlanError("草稿不是目录格式：需要 `## 目标`、`## 各阶段` 和 `### P<n> <阶段名>` 标题（模板见 templates/minimal）")
    errors = _error_dicts(draft)
    base = {"schema_version": SCHEMA_VERSION, "tool": "plan-migrate", "project": str(root),
            "apply": apply, "format_before": old.format}
    archived = _archived_by_phase(path)
    errors += [{"code": "PLAN_PHASE_NO_STEPS",
                "message": f"{phase.id} {phase.title}：做完的阶段也要列 3–5 条关键步骤（做了什么、结果怎样），"
                           "卡片上才能点开看"}
               for phase in draft.phases
               if phase.mark == "✅" and not phase_steps(phase, draft.items) and not archived.get(phase.id)]
    if errors:
        return {**base, "verdict": "block", "errors": errors, "next_hint": "按 errors 改草稿后重跑（草稿里的步骤写法同 plan add）"}
    # An ID names one piece of work forever (`Task:` trailers point at it): a draft step may reuse
    # an old ID only for that same step. From an outline plan a rewrite may still reword titles.
    known = {item.id: item.title for item in old.items} if not old.outline else {}
    known.update(_archived_titles(path))
    reused = [f"{item.id}：旧「{known[item.id]}」→ 新「{item.title}」" for item in draft.items
              if item.id in known and known[item.id] != item.title]
    if reused:
        return {**base, "verdict": "block",
                "errors": [{"code": "PLAN_MIGRATE_ID_REUSED", "message": text} for text in reused],
                "next_hint": "这些编号以前指别的任务（提交记录里还引用着）：新步骤换一个没用过的编号"}
    final_text = render_plan_with_mirrors(draft, draft.items)
    final = parse_plan_text(path, final_text)
    new_titles = {item.id: item.title for item in final.items}
    dropped = [f"{item.id} {item.title}" for item in old.items if not item.closed
               and (item.id not in new_titles or (not old.outline and new_titles[item.id] != item.title))]
    result = {
        **base,
        "verdict": "ok",
        "phases": len(final.phases),
        "steps": len(final.items),
        "open_steps": sum(1 for item in final.items if not item.closed),
        "bytes_before": len(old.text.encode("utf-8")),
        "bytes_after": len(final_text.encode("utf-8")),
        "dropped_open": dropped,
        "warnings": readability_warnings(final),
        "preview": _outline_fields(final),
    }
    if not apply:
        result["next_hint"] = (f"预览通过：{len(final.phases)} 个阶段、{len(final.items)} 步"
                               + (f"；旧计划有 {len(dropped)} 个未关闭任务不在草稿里，确认放弃后加 --accept-dropped"
                                  if dropped else "")
                               + f"；确认后 plan migrate {root} {source} --apply")
        return result
    if dropped and not accept_dropped:
        return {**result, "verdict": "block",
                "next_hint": "旧计划的这些未关闭任务不在草稿里：写进草稿，或确认放弃后加 --accept-dropped"}
    now = datetime.now()
    history = _log_dir(path) / PLAN_HISTORY_DIR
    history.mkdir(parents=True, exist_ok=True)
    snapshot = history / f"{now:%Y-%m-%d-%H%M%S}-before-migrate.md"
    counter = 1
    while snapshot.exists():   # two rewrites in one second keep both originals
        counter += 1
        snapshot = history / f"{now:%Y-%m-%d-%H%M%S}-{counter}-before-migrate.md"
    snapshot.write_text(old.text, encoding="utf-8")
    snapshot_rel = str(snapshot.relative_to(path.parent))
    try:
        atomic_replace_plan(path, old.sha256, final_text)
    except PlanConflict:
        snapshot.unlink()
        raise
    link = path.parent / MIGRATE_LINK
    # the link keeps pointing at the last pre-outline original; later rewrites only add snapshots
    if (link.is_symlink() or not link.exists()) and (not old.outline or not link.is_symlink()):
        tmp_link = link.with_name(link.name + ".tmp")
        if tmp_link.is_symlink() or tmp_link.exists():
            tmp_link.unlink()
        tmp_link.symlink_to(snapshot_rel)
        os.replace(tmp_link, link)
    result["original_snapshot"] = str(snapshot)
    result["log"] = _append_log_line(
        path, f"migrate plan → 目录格式：{len(final.phases)} 个阶段 {len(final.items)} 步 · ev={snapshot_rel}"
              + (f" · dropped={','.join(item.split(' ', 1)[0] for item in dropped)}" if dropped else ""))
    result["next_hint"] = f"已替换；替换前原文 {snapshot_rel}（旧格式原文软链 {MIGRATE_LINK}）；plan show 看新目录"
    return result


def _archived_titles(plan_path: Path) -> dict[str, str]:
    """id → title of the task lines moved to `_logs/plan-archive.md`."""
    return {item_id: title for item_id, (title, _) in _archived_steps(plan_path).items()}


def _archived_steps(plan_path: Path) -> dict[str, tuple[str, str]]:
    """id → (title, state) of the task lines moved to `_logs/plan-archive.md`."""
    archive_path = _log_dir(plan_path) / ARCHIVE_NAME
    if not archive_path.is_file():
        return {}
    text = "## Active Work\n\n" + "\n".join(
        line.strip() for line in archive_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if TASK_LINE_RE.match(line)) + "\n"
    return {item.id: (item.title, item.state) for item in parse_plan_text(plan_path, text).items}


# ---------- plan compact: move journal sections out of the plan ----------

COMPACT_INDEX_HEADING = "## 历史索引（plan compact 移出，原文在 _logs）"
JOURNAL_SUFFIX = "-journal-archive.md"
SECTION_BYTES_BUDGET = 2_000
PREAMBLE_BYTES_BUDGET = 1_500
PROSE_LINE_BYTES_BUDGET = 1_000
INDEX_TITLES = 12
# 瘦身前的完整原文：_logs/plan-history/<时间>-before-compact.md，
# 并用 _top/ 下的固定软链指向最近一份，AI 读摘要，需要时一步打开原文。
PLAN_HISTORY_DIR = "plan-history"
BEFORE_COMPACT_LINK = "_task_plan.before-compact.md"
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_HEADING_RE = re.compile(r"^(#{2,6})\s+(.*\S)\s*$")
_HISTORY_RE = re.compile(r"^(历史|旧|history|archive|legacy)", re.I)
_TASK_LINE_RE = re.compile(r"^\s*[-*]\s+\[[ xX]\]\s+P\d")
_COORD_HEADING_RE = re.compile(r"^##\s+Current Coordinate\s*$", re.I)


def _nbytes(lines: list[str]) -> int:
    return sum(len(line.encode("utf-8")) + 1 for line in lines)


def _headings(lines: list[str], start: int, end: int) -> list[tuple[int, int, str]]:
    """(index, level, title) of markdown headings in [start, end), skipping fenced code."""
    out, fenced = [], False
    for index in range(start, end):
        stripped = lines[index].strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fenced = not fenced
            continue
        match = None if fenced else _HEADING_RE.match(lines[index])
        if match:
            out.append((index, len(match.group(1)), match.group(2)))
    return out


def _is_journal(title: str) -> bool:
    return bool(_DATE_RE.search(title) or _HISTORY_RE.match(title.strip("*_ 🔴")))


def _parse_signature(state) -> dict[str, Any]:
    return {
        "phase": state.phase_id,
        "stamp_task": state.stamp_task_id,
        "coordinate": state.coordinate,
        "items": [render_plan_item(item) for item in state.items],
        "done_criteria": done_criteria_line(state.text),
        "errors": sorted({code for code, _ in plan_invariant_errors(state)}),
    }


def _plan_compact_blocks(state) -> tuple[list[tuple[int, int, str, str]], int | None]:
    """Blocks (start, end, label, reason) to move, and the index section start (if any)."""
    lines = state.lines
    moves: list[tuple[int, int, str, str]] = []
    h2 = [(i, t) for i, level, t in _headings(lines, 0, len(lines)) if level == 2]
    index_at = next((i for i, t in h2 if lines[i].strip() == COMPACT_INDEX_HEADING), None)
    bounds = [(i, (h2[n + 1][0] if n + 1 < len(h2) else len(lines)), t) for n, (i, t) in enumerate(h2)]
    # Preamble: keep title, current stamp line and the Done Criteria paragraph; move the rest.
    first_h2 = h2[0][0] if h2 else len(lines)
    if _nbytes(lines[:first_h2]) > PREAMBLE_BYTES_BUDGET:
        keep: set[int] = set()
        stamp_seen = False
        for index in range(first_h2):
            line = lines[index]
            if line.startswith("# ") and not keep:
                keep.add(index)
            elif not stamp_seen and index < PLAN_HEAD_LIMIT and is_current_line(line) and STAMP_TOKEN_RE.search(line):
                keep.add(index)
                stamp_seen = True
            elif "Done Criteria" in line and index < PLAN_HEAD_LIMIT:
                keep.add(index)
                follow = index + 1
                while follow < first_h2 and lines[follow].strip() not in ("", ">") \
                        and "Done Criteria" not in lines[follow] and not is_current_line(lines[follow]):
                    keep.add(follow)
                    follow += 1
        run_start = None
        for index in range(first_h2 + 1):
            movable = index < first_h2 and index not in keep
            if movable and run_start is None:
                run_start = index
            elif not movable and run_start is not None:
                if _nbytes(lines[run_start:index]) > 200:
                    moves.append((run_start, index, "文件头部长说明", "preamble"))
                run_start = None
    for start, end, title in bounds:
        if start == index_at or _COORD_HEADING_RE.match(lines[start]):
            continue
        if state.outline and (start == state.active_start or title.strip() in ("目标", "现在")):
            continue   # the table of contents itself is never moved; plan archive folds phases
        if start == state.active_start:
            taken_until = start
            for sub, level, sub_title in _headings(lines, start + 1, end):
                if sub < taken_until or not _is_journal(sub_title):
                    continue
                sub_end = next((i for i, lv, _ in _headings(lines, sub + 1, end) if lv <= level), end)
                if any(_TASK_LINE_RE.match(line) for line in lines[sub:sub_end]):
                    continue
                moves.append((sub, sub_end, sub_title, "Active Work 内按日期的流水小节"))
                taken_until = sub_end
            for index in range(start + 1, end):
                if index < taken_until or any(a <= index < b for a, b, _, _ in moves):
                    continue
                line = lines[index]
                if not _TASK_LINE_RE.match(line) and not line.lstrip().startswith("#") \
                        and len(line.encode("utf-8")) > PROSE_LINE_BYTES_BUDGET:
                    moves.append((index, index + 1, line.strip()[:40], "Active Work 内超长说明行"))
            continue
        size = _nbytes(lines[start:end])
        if _is_journal(title):
            moves.append((start, end, title, "按日期/历史段落"))
        elif size > SECTION_BYTES_BUDGET:
            moves.append((start, end, title, f"段落 {size // 1024}KB 超过 {SECTION_BYTES_BUDGET // 1000}KB"))
    return sorted(moves), index_at


def original_commit_path(plan_path: Path) -> str:
    top = top_git.toplevel(plan_path.parent)
    try:
        return str(plan_path.resolve().relative_to(top.resolve())) if top else plan_path.name
    except ValueError:
        return plan_path.name


def _plan_head_commit(plan_path: Path) -> str | None:
    """Commit holding exactly the current plan text (plan clean at HEAD), else None."""
    top = top_git.toplevel(plan_path.parent)
    if top is None:
        return None
    return top_git.clean_head_commit(top, original_commit_path(plan_path))


def compact(project: str, *, apply: bool = False) -> dict[str, Any]:
    """Move dated journal sections / long history out of the plan into `_logs/<date>-journal-archive.md`.

    Keeps the header stamp, Done Criteria, Current Coordinate, Active Work task lines and a short
    index. Dry-run by default; `apply=True` writes the archive first, then compare-and-swaps the plan
    (rolling the archive back on conflict). Refuses if the parsed plan would change in any way.
    """
    root, path = _writable_path(project)
    if not path.is_file():
        raise PlanError(f"task plan not found: {path}")
    state = parse_plan(path)
    before = len(state.text.encode("utf-8"))
    if state.active_start is None:
        return {"schema_version": SCHEMA_VERSION, "tool": "plan-compact", "project": str(root),
                "apply": apply, "lightweight": True, "verdict": "ok", "moved": [], "bytes_before": before,
                "next_hint": "轻量模式计划（没有 ## Active Work）：不做 compact，也不要求维护"}
    moves, index_at = _plan_compact_blocks(state)
    now = datetime.now()
    archive_path = _log_dir(path) / f"{now:%Y-%m-%d}{JOURNAL_SUFFIX}"
    archive_rel = str(archive_path.relative_to(path.parent))
    snapshot_path = _log_dir(path) / PLAN_HISTORY_DIR / f"{now:%Y-%m-%d-%H%M%S}-before-compact.md"
    snapshot_rel = str(snapshot_path.relative_to(path.parent))
    link_path = path.parent / BEFORE_COMPACT_LINK
    base = {"schema_version": SCHEMA_VERSION, "tool": "plan-compact", "project": str(root),
            "task_plan": str(path.relative_to(root)), "apply": apply, "bytes_before": before}
    if not moves:
        return {**base, "verdict": "ok", "moved": [], "bytes_after": before,
                "next_hint": "没有按日期的流水段或超长历史可移出"}
    drop = {i for start, end, _, _ in moves for i in range(start, end)}
    kept = [line for i, line in enumerate(state.lines) if i not in drop]
    labels = [label for _, _, label, _ in moves]
    original_commit = _plan_head_commit(path)
    git_note = f"；Git 原文 `git show {original_commit}:{original_commit_path(path)}`" if original_commit else ""
    entry = "\n".join([f"- {now:%Y-%m-%d} 移出 {len(moves)} 段 → `{archive_rel}`；"
                       f"瘦身前完整原文 `{BEFORE_COMPACT_LINK}`（软链 → `{snapshot_rel}`）{git_note}",
                       *(f"  - {label[:40]}" for label in labels[:INDEX_TITLES]),
                       *([f"  - …另 {len(labels) - INDEX_TITLES} 段"] if len(labels) > INDEX_TITLES else [])])
    if index_at is None:
        while kept and not kept[-1].strip():
            kept.pop()
        kept += ["", COMPACT_INDEX_HEADING, "", entry]
    else:
        heading_pos = next(i for i, line in enumerate(kept) if line.strip() == COMPACT_INDEX_HEADING)
        insert_at = next((i for i in range(heading_pos + 1, len(kept)) if kept[i].startswith("## ")), len(kept))
        while insert_at > heading_pos + 1 and not kept[insert_at - 1].strip():
            insert_at -= 1
        kept.insert(insert_at, entry)
    new_text = "\n".join(kept).rstrip() + "\n"
    if _parse_signature(parse_plan_text(path, new_text)) != _parse_signature(state):
        raise PlanError("compact 会改变计划的解析结果（stamp/坐标/任务/Done Criteria），已拒绝；请人工整理")
    after = len(new_text.encode("utf-8"))
    moved = [{"lines": f"{start + 1}-{end}", "bytes": _nbytes(state.lines[start:end]),
              "title": label[:80], "reason": reason} for start, end, label, reason in moves]
    result = {**base, "verdict": "ok", "moved": moved, "bytes_after": after,
              "archive_file": str(archive_path), "original_snapshot": str(snapshot_path),
              "original_link": str(link_path), "original_commit": original_commit}
    closed = sum(1 for item in state.items if item.closed)
    archive_hint = f"；已关闭任务 {closed} 个仍在 Active Work，可再 plan archive {root}" if closed > 10 else ""
    if not apply:
        result["next_hint"] = (f"预览：{len(moves)} 段 {before // 1024}KB→{after // 1024}KB；"
                               f"确认后 plan compact {root} --apply{archive_hint}")
        return result
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(state.text, encoding="utf-8")
    previous_link = os.readlink(link_path) if link_path.is_symlink() else None
    if link_path.exists() and not link_path.is_symlink():
        snapshot_path.unlink()
        raise PlanError(f"{link_path} 已存在且不是软链，拒绝覆盖")
    tmp_link = link_path.with_name(link_path.name + ".tmp")
    if tmp_link.is_symlink() or tmp_link.exists():
        tmp_link.unlink()
    tmp_link.symlink_to(snapshot_rel)
    os.replace(tmp_link, link_path)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    existed = archive_path.is_file()
    size_before = archive_path.stat().st_size if existed else 0
    header = "" if existed else (f"# {now:%Y-%m-%d} journal archive\n\n"
                                 "plan compact 从 `_task_plan.md` 原样移出的流水段落；只读历史，不是当前状态。\n")
    body = [f"\n## compact {now:%H:%M} · 自 {path.name}（{len(moves)} 段）\n"]
    for start, end, _, reason in moves:
        body.append(f"\n<!-- 原第 {start + 1}-{end} 行 · {reason} -->\n" + "\n".join(state.lines[start:end]) + "\n")
    with archive_path.open("a", encoding="utf-8") as handle:
        handle.write(header + "".join(body))
    try:
        atomic_replace_plan(path, state.sha256, new_text)
    except PlanConflict:
        if existed:
            with archive_path.open("r+b") as handle:
                handle.truncate(size_before)
        else:
            archive_path.unlink()
        link_path.unlink()
        if previous_link:
            link_path.symlink_to(previous_link)
        snapshot_path.unlink()
        raise
    result["log"] = _append_log_line(path, f"compact plan 移出 {len(moves)} 段 {before // 1024}KB→{after // 1024}KB"
                                           f" · ev={archive_rel} · 原文={snapshot_rel}")
    result["next_hint"] = (f"已移出 {len(moves)} 段到 {archive_rel}；瘦身前原文 {BEFORE_COMPACT_LINK}；"
                           f"计划 {after // 1024}KB{archive_hint}")
    return result
