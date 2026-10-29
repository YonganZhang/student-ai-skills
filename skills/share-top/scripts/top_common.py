#!/usr/bin/env python3
"""Shared read-only helpers for TOP planning scripts."""

from __future__ import annotations

import re
import hashlib
import importlib.util
import os
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


PHASE_ID_RE = re.compile(r"^P\d+(?:\.[A-Za-z0-9]+)*$")
STAMP_TOKEN_RE = re.compile(r"\[([^\]\n]+)\]")
DATE_PREFIX_RE = re.compile(r"^_?(\d{4}-\d{2}-\d{2})")
PLAN_HEAD_LIMIT = 40
TASK_ID_RE = re.compile(r"^P\d+(?:\.[A-Za-z0-9]+)+$")
# any step ID: outline/legacy (P3.2) or question-and-answer attempt (Q4.3); for read-only consumers
ANY_TASK_ID_RE = re.compile(r"^(?:P\d+(?:\.[A-Za-z0-9]+)+|Q\d+\.\d+)$")
ACTIVE_WORK_HEADING_RE = re.compile(r"^##\s+Active Work\s*$", re.I)
TASK_LINE_RE = re.compile(
    r"^\s*[-*]\s+\[([ xX])\]\s+"
    r"(P\d+(?:\.[A-Za-z0-9]+)+)\s+(.+?)\s*$"
)
CURRENT_TASK_STAMP_RE = re.compile(r"\btask=\[([^\]\n]+)\]", re.I)
COORD_FIELD_RE = re.compile(
    r"^\s*-\s*(Goal|Current task|Next task|Latest learning|Blocker)\s*:\s*(.*?)\s*$",
    re.I,
)
PLAN_STATES = {"pending", "in_progress", "blocked", "done", "cancelled"}
REPEATABLE_TASK_KEYS = {"dep", "depends_on", "ev", "scope", "gate"}
TERMINAL_TASK_KEYS = {"reason", "no_artifact_reason"}

# Outline format (2026-09-26, planning-with-files style): the plan reads like a table of
# contents. `## 目标` (goal text), `## 现在` (CLI-generated mirror), `## 各阶段` with one
# `### P<n> <title> <mark>` heading per phase, a short summary paragraph under it, then the
# phase's steps `- [ ] P<n>.<k> <title> <!-- key=value · … -->`. Machine metadata sits in the
# trailing HTML comment, so rendered Markdown shows only the human text.
OUTLINE_HEADING_RE = re.compile(r"^##\s+各阶段\s*$")
GOAL_HEADING_RE = re.compile(r"^##\s+目标\s*$")
NOW_HEADING_RE = re.compile(r"^##\s+现在\s*$")
PHASE_HEADING_RE = re.compile(r"^###\s+(P\d+)(?:\s+(.*?))?\s*$")
COMMENT_TAIL_RE = re.compile(r"^(.*?)\s*<!--(.*?)-->\s*$")
PHASE_MARKS = {"✅": "done", "🔄": "in_progress", "⏸": "blocked", "⏳": "pending", "✕": "cancelled"}
# look-alikes people and models type instead (U+FE0F variation selectors are dropped first)
MARK_ALIASES = {"✔": "✅", "☑": "✅", "❌": "✕", "✖": "✕", "⏯": "⏸", "⌛": "⏳"}
MARK_FOR_STATE = {state: mark for mark, state in PHASE_MARKS.items()}
NOW_NOTE = "<!-- plan 命令自动生成，不要手改 -->"
PHASE_DROP_PREFIX = "阶段放弃："   # `plan phase cancel` reason: the whole phase was given up


class PlanError(ValueError):
    """Invalid plan operation or schema."""


class PlanConflict(PlanError):
    """The plan changed after it was read."""


@dataclass
class PlanItem:
    id: str
    title: str
    checked: bool
    state: str
    line_index: int
    deps: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)
    gates: list[str] = field(default_factory=list)
    reason: str = ""
    no_artifact_reason: str = ""
    unknown_tags: list[str] = field(default_factory=list)
    # How deps are written back: "dep" = one `dep=<ID>` per value (default);
    # "depends_on" = a single `depends_on=<ID>,<ID>` segment (optional alias).
    dep_style: str = "dep"
    # Outline format only: the `### P<n>` heading this step line sits under.
    section: str = ""

    @property
    def closed(self) -> bool:
        return self.state in {"done", "cancelled"}


@dataclass
class PlanPhase:
    """One `### P<n> <title> <mark>` heading of an outline plan."""
    id: str
    title: str
    mark: str
    line_index: int
    end: int                      # exclusive: next phase heading or the section end
    summary: str = ""             # the paragraph between the heading and the first step


@dataclass
class PlanState:
    path: Path
    text: str
    sha256: str
    lines: list[str]
    phase_id: str
    stamp_task_id: str
    coordinate: dict[str, str]
    active_start: int | None
    active_end: int | None
    items: list[PlanItem]
    malformed_task_lines: list[tuple[int, str]]
    format: str = "legacy"        # "outline" (目录格式) or "legacy" (Active Work + stamp)
    phases: list[PlanPhase] = field(default_factory=list)
    malformed_phase_lines: list[tuple[int, str]] = field(default_factory=list)

    def by_id(self) -> dict[str, PlanItem]:
        return {item.id: item for item in self.items}

    @property
    def outline(self) -> bool:
        return self.format == "outline"


def _text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _active_work_bounds(lines: list[str]) -> tuple[int | None, int | None]:
    start = None
    for index, line in enumerate(lines):
        if ACTIVE_WORK_HEADING_RE.match(line.strip()):
            start = index
            break
    if start is None:
        return None, None
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if re.match(r"^##\s+", lines[index]):
            end = index
            break
    return start, end


def _split_task_segments(rest: str) -> tuple[str, list[tuple[str, str]], list[str]]:
    parts = rest.split(" · ")
    title = parts[0].strip()
    tags: list[tuple[str, str]] = []
    unknown: list[str] = []
    index = 1
    while index < len(parts):
        segment = parts[index].strip()
        if "=" not in segment:
            unknown.append(segment)
            index += 1
            continue
        key, value = segment.split("=", 1)
        key = key.strip().lower()
        value = value.strip()
        if key in TERMINAL_TASK_KEYS:
            if index + 1 < len(parts):
                value = " · ".join([value, *parts[index + 1 :]]).strip()
            tags.append((key, value))
            break
        tags.append((key, value))
        index += 1
    return title, tags, unknown


def _parse_plan_item(line: str, line_index: int) -> PlanItem | None:
    match = TASK_LINE_RE.match(line)
    if not match:
        return None
    checked = match.group(1).lower() == "x"
    item_id = match.group(2)
    rest = match.group(3)
    comment = COMMENT_TAIL_RE.match(rest)
    if comment:   # outline style: `title <!-- key=value · … -->`
        title, tags, unknown = _split_task_segments(comment.group(1))
        meta = comment.group(2).strip()
        if meta:
            _, more, more_unknown = _split_task_segments(" · " + meta)
            tags += more
            unknown += more_unknown
    else:
        title, tags, unknown = _split_task_segments(rest)
    values: dict[str, list[str]] = {}
    for key, value in tags:
        values.setdefault(key, []).append(value)
        if key not in REPEATABLE_TASK_KEYS | TERMINAL_TASK_KEYS | {"state"}:
            unknown.append(f"{key}={value}")
    explicit_state = values.get("state", [""])[-1]
    state = explicit_state or ("done" if checked else "pending")
    deps = list(values.get("dep", []))
    for group in values.get("depends_on", []):
        for dep in (value.strip() for value in group.split(",")):
            if dep and dep not in deps:
                deps.append(dep)
    dep_style = "depends_on" if values.get("depends_on") and not values.get("dep") else "dep"
    return PlanItem(
        id=item_id,
        title=title,
        checked=checked,
        state=state,
        line_index=line_index,
        deps=deps,
        evidence=values.get("ev", []),
        scopes=values.get("scope", []),
        gates=values.get("gate", []),
        reason=values.get("reason", [""])[-1],
        no_artifact_reason=values.get("no_artifact_reason", [""])[-1],
        unknown_tags=unknown,
        dep_style=dep_style,
    )


def qa_format():
    """The question-and-answer format module (scripts/qa_format.py), loaded by file path so
    consumers that load this module by path (cards, git hooks) need no sys.path change."""
    module = sys.modules.get("qa_format")
    if module is None:
        spec = importlib.util.spec_from_file_location("qa_format", Path(__file__).with_name("qa_format.py"))
        if spec is None or spec.loader is None:
            raise ImportError("qa_format.py not found next to top_common.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules["qa_format"] = module
        spec.loader.exec_module(module)
    return module


def parse_plan(path: Path) -> PlanState:
    state = parse_plan_text(path, read_text(path))
    if state.format == "qa":
        # read-only view of the attempts as tasks, for consumers of the task model
        # (Task: trailers, cards, status); writes go through top_qa only
        for item_id, title, state_name, gates, ev, reason, no_artifact in qa_format().attempt_tuples(path):
            state.items.append(PlanItem(
                id=item_id, title=title, checked=state_name in {"done", "cancelled"}, state=state_name,
                line_index=-1, gates=gates, evidence=ev, reason=reason, no_artifact_reason=no_artifact,
                section=item_id.split(".", 1)[0]))
    return state


def _section_bounds(lines: list[str], heading_re: re.Pattern[str]) -> tuple[int | None, int | None]:
    """(heading index, exclusive end) of the first `## ` section matching heading_re."""
    for index, line in enumerate(lines):
        if heading_re.match(line.strip()):
            end = next((i for i in range(index + 1, len(lines)) if re.match(r"^##\s+", lines[i])), len(lines))
            return index, end
    return None, None


def _section_text(lines: list[str], heading_re: re.Pattern[str]) -> str:
    start, end = _section_bounds(lines, heading_re)
    if start is None:
        return ""
    body = [line.strip() for line in lines[start + 1:end]
            if line.strip() and not line.strip().startswith("<!--")]
    return " ".join(body)


def _parse_outline(lines: list[str], start: int, end: int):
    """Phases, steps and malformed lines of the `## 各阶段` section."""
    phases: list[PlanPhase] = []
    items: list[PlanItem] = []
    malformed: list[tuple[int, str]] = []
    bad_phases: list[tuple[int, str]] = []
    phase: PlanPhase | None = None
    summary: list[str] = []
    for index in range(start + 1, end):
        line = lines[index]
        if line.startswith("### "):
            if phase is not None:
                phase.end = index
            match = PHASE_HEADING_RE.match(line)
            if not match:
                bad_phases.append((index + 1, line))
                phase = None
                continue
            title, mark = _split_phase_title(match.group(2) or "")
            phase = PlanPhase(id=match.group(1), title=title, mark=mark, line_index=index, end=end)
            phases.append(phase)
            summary = []
            continue
        if re.match(r"^\s*[-*]\s+\[[ xX]\]\s+", line):
            item = _parse_plan_item(line, index)
            if item is None:
                malformed.append((index + 1, line))
            else:
                item.section = phase.id if phase else ""
                items.append(item)
            continue
        stripped = line.strip()
        if phase is not None and stripped and not stripped.startswith("<!--") \
                and not any(i.section == phase.id for i in items):
            summary.append(stripped.lstrip("> ").strip())
            phase.summary = " ".join(summary)
    return phases, items, malformed, bad_phases


def _split_phase_title(text: str) -> tuple[str, str]:
    """(title, trailing mark). Marks written inside the title are dropped: the state is
    derived from the steps and rendered once, at the end of the heading."""
    text = text.replace("\ufe0f", "").strip()
    mark = next((m for m in [*PHASE_MARKS, *MARK_ALIASES] if text.endswith(m)), "")
    return strip_phase_marks(text[: -len(mark)] if mark else text), MARK_ALIASES.get(mark, mark)


def strip_phase_marks(text: str) -> str:
    text = text.replace("\ufe0f", "")
    for mark in [*PHASE_MARKS, *MARK_ALIASES]:
        text = text.replace(mark, " ")
    return " ".join(text.split())


def phase_steps(phase: PlanPhase, items: list[PlanItem]) -> list[PlanItem]:
    return [item for item in items if item.id.startswith(phase.id + ".")]


def phase_state(phase: PlanPhase, items: list[PlanItem]) -> str:
    """Derived from the steps; a phase without steps in the file (not started yet, or its
    steps moved out by `plan archive`) keeps the ✅ / ✕ written on its heading."""
    steps = phase_steps(phase, items)
    if not steps:
        return PHASE_MARKS[phase.mark] if phase.mark in ("✅", "✕") else "pending"
    if any(step.state == "in_progress" for step in steps):
        return "in_progress"
    open_steps = [step for step in steps if not step.closed]
    if not open_steps:
        dropped = any(step.state == "cancelled" and step.reason.startswith(PHASE_DROP_PREFIX) for step in steps)
        return "cancelled" if dropped or all(step.state == "cancelled" for step in steps) else "done"
    if all(step.state == "blocked" for step in open_steps):
        return "blocked"
    return "in_progress" if any(step.state == "done" for step in steps) else "pending"


def current_phase(state: PlanState, items: list[PlanItem] | None = None) -> PlanPhase | None:
    """The phase holding the in-progress step; else the first started/blocked phase; else the
    first one not started; else None (everything closed)."""
    items = state.items if items is None else items
    for phase in state.phases:
        if any(step.state == "in_progress" for step in phase_steps(phase, items)):
            return phase
    states = [(phase, phase_state(phase, items)) for phase in state.phases]
    for wanted in ("in_progress", "blocked", "pending"):
        for phase, value in states:
            if value == wanted:
                return phase
    return None


def blocked_items(items: list[PlanItem]) -> list[PlanItem]:
    return [item for item in items if item.state == "blocked"]


def derive_next_item(state: PlanState) -> PlanItem | None:
    by_id = state.by_id()
    for item in state.items:
        if item.state != "pending":
            continue
        if all(
            dep in by_id and by_id[dep].state in {"done", "cancelled", "in_progress"}
            for dep in item.deps
        ):
            return item
    return None


def plan_invariant_errors(state: PlanState) -> list[tuple[str, str]]:
    if state.format == "qa":
        return []   # question-and-answer plans are checked by top_qa.hard_errors
    errors: list[tuple[str, str]] = []
    if state.active_start is None:
        return [("PLAN_ACTIVE_WORK_MISSING", "missing ## Active Work section")]
    for line_no, line in state.malformed_task_lines:
        errors.append(("PLAN_ITEM_MALFORMED", f"line {line_no}: {line}"))
    ids = [item.id for item in state.items]
    duplicates = sorted({item_id for item_id in ids if ids.count(item_id) > 1})
    for item_id in duplicates:
        errors.append(("PLAN_ID_DUPLICATE", item_id))
    by_id = state.by_id()
    for item in state.items:
        if not TASK_ID_RE.fullmatch(item.id):
            errors.append(("PLAN_ID_INVALID", item.id))
        if state.outline:
            if not item.section or not item.id.startswith(item.section + "."):
                where = f"under ### {item.section}" if item.section else "before the first ### phase heading"
                errors.append(("PLAN_STEP_OUTSIDE_PHASE", f"{item.id} is {where}"))
            elif item.id.count(".") > 1:   # two levels only: phase → step
                errors.append(("PLAN_STEP_TOO_DEEP", f"{item.id}：目录格式只有 阶段 → 步骤 两层，"
                                                     "要补内容就在它后面插一步（plan insert）"))
        elif state.phase_id and not item.id.startswith(state.phase_id + "."):
            errors.append(("PLAN_PHASE_MISMATCH", f"{item.id} is outside {state.phase_id}"))
        if item.state not in PLAN_STATES:
            errors.append(("PLAN_UNKNOWN_STATE", f"{item.id}: {item.state}"))
        if item.checked != (item.state in {"done", "cancelled"}):
            errors.append(("PLAN_CHECKBOX_STATE", f"{item.id}: checked={item.checked} state={item.state}"))
        if item.unknown_tags:
            errors.append(("PLAN_UNKNOWN_TAG", f"{item.id}: {', '.join(item.unknown_tags)}"))
        for dep in item.deps:
            if dep not in by_id:
                errors.append(("PLAN_DEP_MISSING", f"{item.id}: {dep}"))
            elif dep == item.id:
                errors.append(("PLAN_DEP_SELF", item.id))
        if item.state == "done" and not (item.evidence or item.no_artifact_reason):
            errors.append(("PLAN_NO_EVIDENCE", item.id))
        if item.state == "cancelled" and not item.reason:
            errors.append(("PLAN_CANCEL_NO_REASON", item.id))
        if item.closed:
            open_children = [
                child.id for child in state.items
                if child.id.startswith(item.id + ".") and not child.closed
            ]
            if open_children:
                errors.append(("PLAN_PARENT_OPEN_CHILD", f"{item.id}: {', '.join(open_children)}"))
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(item_id: str, trail: list[str]) -> None:
        if item_id in visited or item_id not in by_id:
            return
        if item_id in visiting:
            start = trail.index(item_id) if item_id in trail else 0
            cycle = trail[start:] + [item_id]
            errors.append(("PLAN_DEP_CYCLE", " -> ".join(cycle)))
            return
        visiting.add(item_id)
        trail.append(item_id)
        for dep in by_id[item_id].deps:
            visit(dep, trail)
        trail.pop()
        visiting.remove(item_id)
        visited.add(item_id)

    for item_id in ids:
        visit(item_id, [])
    active = [item for item in state.items if item.state == "in_progress"]
    if len(active) > 1:
        errors.append(("PLAN_MULTI_INPROGRESS", ", ".join(item.id for item in active)))
    if state.outline:
        for line_no, line in state.malformed_phase_lines:
            errors.append(("PLAN_PHASE_MALFORMED", f"line {line_no}: {line}（阶段标题写成 ### P<n> <名称>）"))
        phase_ids = [phase.id for phase in state.phases]
        for phase_id in sorted({pid for pid in phase_ids if phase_ids.count(pid) > 1}):
            errors.append(("PLAN_PHASE_DUPLICATE", phase_id))
        return errors   # the 现在 block is a regenerated mirror: stale = warning, not an error
    active_id = active[0].id if len(active) == 1 else "none"
    stamp_id = state.stamp_task_id or "none"
    coordinate_current = state.coordinate.get("current_task", "none") or "none"
    if stamp_id != active_id:
        errors.append(("PLAN_STAMP_MISMATCH", f"stamp={stamp_id} active={active_id}"))
    if coordinate_current != active_id:
        errors.append(("PLAN_CURRENT_MISMATCH", f"coordinate={coordinate_current} active={active_id}"))
    next_item = derive_next_item(state)
    next_id = next_item.id if next_item else "none"
    coordinate_next = state.coordinate.get("next_task", "none") or "none"
    if coordinate_next != next_id:
        errors.append(("PLAN_NEXT_MISMATCH", f"coordinate={coordinate_next} derived={next_id}"))
    return errors


def render_plan_item(item: PlanItem, outline: bool = False) -> str:
    """Legacy: `- [ ] ID title · key=value · …`. Outline: the metadata goes into a trailing
    HTML comment and sub-steps are indented two spaces per level, so the Markdown reads as a
    table of contents."""
    box = "x" if item.state in {"done", "cancelled"} else " "
    segments: list[str] = []
    default_state = "done" if box == "x" else "pending"
    if item.state != default_state:
        segments.append(f"state={item.state}")
    if item.dep_style == "depends_on" and item.deps:
        segments.append("depends_on=" + ",".join(item.deps))
    else:
        segments.extend(f"dep={value}" for value in item.deps)
    segments.extend(f"scope={value}" for value in item.scopes)
    segments.extend(f"gate={value}" for value in item.gates)
    segments.extend(f"ev={value}" for value in item.evidence)
    if item.no_artifact_reason:
        segments.append(f"no_artifact_reason={item.no_artifact_reason}")
    elif item.reason:
        segments.append(f"reason={item.reason}")
    head = f"- [{box}] {item.id} {item.title}"
    if not outline:
        return " · ".join([head, *segments])
    indent = "  " * max(0, item.id.count(".") - 1)
    return f"{indent}{head}" + (f" <!-- {' · '.join(segments)} -->" if segments else "")


def render_phase_heading(phase: PlanPhase, state_name: str) -> str:
    return f"### {phase.id} {phase.title} {MARK_FOR_STATE[state_name]}".rstrip()


def render_now_block(state: PlanState, items: list[PlanItem]) -> list[str]:
    """Body lines of `## 现在`: a mirror derived from the steps, rewritten on every plan write."""
    phase = current_phase(state, items)
    shadow = PlanState(path=state.path, text="", sha256="", lines=[], phase_id="", stamp_task_id="",
                       coordinate={}, active_start=state.active_start, active_end=state.active_end,
                       items=items, malformed_task_lines=[], format="outline", phases=state.phases)
    active = next((item for item in items if item.state == "in_progress"), None)
    upcoming = derive_next_item(shadow)
    blocked = blocked_items(items)
    if phase is not None:
        position = state.phases.index(phase) + 1
        stage = f"第 {position}/{len(state.phases)} 阶段 · {phase.id} {phase.title}"
    else:
        stage = "全部阶段已完成" if state.phases else "还没有阶段（用 plan phase add 建第一个）"
    blockers = "；".join(f"{item.id} {item.reason or item.title}" for item in blocked[:2])
    if len(blocked) > 2:
        blockers += f"；另 {len(blocked) - 2} 项"
    return [
        NOW_NOTE,
        f"- 阶段：{stage}",
        f"- 正在做：{active.id} {active.title}" if active else "- 正在做：没有",
        f"- 下一步：{upcoming.id} {upcoming.title}" if upcoming else "- 下一步：没有可以直接开始的步骤",
        f"- 卡点：{blockers or '无'}",
    ]


def outline_now_stale(state: PlanState) -> bool:
    start, end = _section_bounds(state.lines, NOW_HEADING_RE)
    if start is None:
        return True
    body = [line for line in state.lines[start + 1:end] if line.strip()]
    return body != render_now_block(state, state.items)


def _render_outline(state: PlanState, items: list[PlanItem]) -> str:
    lines = list(state.lines)
    for item in items:
        if item.line_index >= len(lines):
            raise PlanError(f"invalid item line index: {item.id}")
        lines[item.line_index] = render_plan_item(item, outline=True)
    for phase in state.phases:
        lines[phase.line_index] = render_phase_heading(phase, phase_state(phase, items))
    now = ["", *render_now_block(state, items), ""]
    start, end = _section_bounds(lines, NOW_HEADING_RE)
    if start is not None:
        lines[start + 1:end] = now
    else:   # put `## 现在` right before `## 各阶段`
        at = state.active_start if state.active_start is not None else len(lines)
        lines[at:at] = ["## 现在", *now]
    tidy: list[str] = []
    fenced = False
    for line in lines:   # one blank line between blocks is enough (edits add their own)
        if line.strip().startswith(("```", "~~~")):
            fenced = not fenced
        if not fenced and not line.strip() and (not tidy or not tidy[-1].strip()):
            continue
        tidy.append(line)
    return "\n".join(tidy).rstrip() + "\n"


def _replace_coordinate(lines: list[str], field_name: str, value: str) -> None:
    label = field_name.replace("_", " ").title()
    for index, line in enumerate(lines):
        match = COORD_FIELD_RE.match(line)
        if match and match.group(1).lower().replace(" ", "_") == field_name:
            lines[index] = f"- {label}: {value}"
            return
    raise PlanError(f"missing Current Coordinate field: {label}")


def _replace_stamp_task(lines: list[str], task_id: str) -> None:
    for index, line in enumerate(lines[:PLAN_HEAD_LIMIT]):
        if is_current_line(line):
            if CURRENT_TASK_STAMP_RE.search(line):
                lines[index] = CURRENT_TASK_STAMP_RE.sub(f"task=[{task_id}]", line, count=1)
            else:
                lines[index] = line.rstrip() + f" task=[{task_id}]"
            return
    raise PlanError("missing current stamp")


def render_plan_with_mirrors(state: PlanState, items: list[PlanItem]) -> str:
    if state.outline:
        return _render_outline(state, items)
    lines = list(state.lines)
    for item in items:
        if item.line_index >= len(lines):
            raise PlanError(f"invalid item line index: {item.id}")
        lines[item.line_index] = render_plan_item(item)
    active = [item for item in items if item.state == "in_progress"]
    active_id = active[0].id if len(active) == 1 else "none"
    shadow = PlanState(
        path=state.path,
        text=state.text,
        sha256=state.sha256,
        lines=lines,
        phase_id=state.phase_id,
        stamp_task_id=active_id,
        coordinate=dict(state.coordinate),
        active_start=state.active_start,
        active_end=state.active_end,
        items=items,
        malformed_task_lines=[],
    )
    next_item = derive_next_item(shadow)
    _replace_stamp_task(lines, active_id)
    _replace_coordinate(lines, "current_task", active_id)
    _replace_coordinate(lines, "next_task", next_item.id if next_item else "none")
    return "\n".join(lines).rstrip() + "\n"


def insert_plan_item(state: PlanState, item: PlanItem) -> str:
    if state.active_start is None or state.active_end is None:
        raise PlanError("missing ## Active Work section")
    lines = list(state.lines)
    lo, insert_at = state.active_start, state.active_end
    if state.outline:   # at the end of the phase the ID belongs to
        phase = next((p for p in state.phases if item.id.startswith(p.id + ".")), None)
        if phase is None:
            raise PlanError(f"no phase heading for {item.id}: create it with `plan phase add`")
        lo, insert_at = phase.line_index, phase.end
    while insert_at > lo + 1 and not lines[insert_at - 1].strip():
        insert_at -= 1
    if state.outline and not re.match(r"^\s*[-*]\s+\[[ xX]\]\s+", lines[insert_at - 1]):
        lines.insert(insert_at, "")   # the first step: keep a blank line after heading/summary
        insert_at += 1
    lines.insert(insert_at, render_plan_item(item, outline=state.outline))
    interim = "\n".join(lines).rstrip() + "\n"
    parsed = parse_plan_text(state.path, interim)
    return render_plan_with_mirrors(parsed, parsed.items)


def parse_plan_text(path: Path, text: str) -> PlanState:
    """Parse in-memory text without touching the filesystem."""
    lines = text.splitlines()
    if qa_format().is_qa_text(text):
        root = qa_format().parse_root_text(text)
        return PlanState(
            path=path, text=text, sha256=_text_sha256(text), lines=lines,
            phase_id="", stamp_task_id="", coordinate={"goal": " ".join(root.goal.split())},
            active_start=None, active_end=None, items=[], malformed_task_lines=[], format="qa",
        )
    outline_start, outline_end = _section_bounds(lines, OUTLINE_HEADING_RE)
    if outline_start is not None and outline_end is not None:
        phases, items, malformed, bad_phases = _parse_outline(lines, outline_start, outline_end)
        state = PlanState(
            path=path, text=text, sha256=_text_sha256(text), lines=lines,
            phase_id="", stamp_task_id="",
            coordinate={"goal": _section_text(lines, GOAL_HEADING_RE)},
            active_start=outline_start, active_end=outline_end,
            items=items, malformed_task_lines=malformed,
            format="outline", phases=phases, malformed_phase_lines=bad_phases,
        )
        current = current_phase(state)
        state.phase_id = current.id if current else ""
        return state
    active_start, active_end = _active_work_bounds(lines)
    items: list[PlanItem] = []
    malformed: list[tuple[int, str]] = []
    if active_start is not None and active_end is not None:
        for index in range(active_start + 1, active_end):
            line = lines[index]
            if re.match(r"^\s*[-*]\s+\[[ xX]\]\s+", line):
                item = _parse_plan_item(line, index)
                if item is None:
                    malformed.append((index + 1, line))
                else:
                    items.append(item)
    coordinate: dict[str, str] = {}
    for line in lines[: max(PLAN_HEAD_LIMIT, (active_start or 0) + 1)]:
        match = COORD_FIELD_RE.match(line)
        if match:
            coordinate[match.group(1).lower().replace(" ", "_")] = match.group(2)
    stamp_task_id = ""
    for line in lines[:PLAN_HEAD_LIMIT]:
        if is_current_line(line):
            match = CURRENT_TASK_STAMP_RE.search(line)
            if match:
                stamp_task_id = match.group(1).strip()
                break
    return PlanState(
        path=path,
        text=text,
        sha256=_text_sha256(text),
        lines=lines,
        phase_id=current_phase_from_lines(lines),
        stamp_task_id=stamp_task_id,
        coordinate=coordinate,
        active_start=active_start,
        active_end=active_end,
        items=items,
        malformed_task_lines=malformed,
    )


def atomic_replace_plan(path: Path, expected_sha256: str, new_text: str) -> None:
    current = read_text(path)
    if qa_format().is_qa_text(current) or qa_format().is_qa_text(new_text):
        raise PlanError("这是问答格式的计划，只能经问答命令改（plan help）：plan ask / answer / add / start / done …")
    if _text_sha256(current) != expected_sha256:
        raise PlanConflict("task plan changed concurrently; reread and retry")
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(new_text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def is_current_line(line: str) -> bool:
    lowered = line.lower()
    return "当前" in line or "current" in lowered


def project_root(start: Path) -> Path:
    path = start.resolve()
    for parent in [path, *path.parents]:
        if (
            (parent / "_codemap.md").is_file()
            or (parent / "_wiki-methodology").is_dir()
            or (parent / "wiki-methodology").is_dir()
        ):
            return parent
    return path


def rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.is_file() else ""


def read_lines(path: Path, limit: int | None = None) -> list[str]:
    lines = read_text(path).splitlines()
    return lines if limit is None else lines[:limit]


def first_match(lines: list[str], pattern: str) -> str:
    regex = re.compile(pattern, re.I)
    for line in lines:
        if regex.search(line):
            return line.strip()
    return ""


def current_phase_from_lines(lines: list[str], limit: int = PLAN_HEAD_LIMIT) -> str:
    token = current_stamp_token_from_lines(lines, limit=limit)
    return token if PHASE_ID_RE.fullmatch(token) else ""


def current_phase_from_text(text: str, limit: int = PLAN_HEAD_LIMIT) -> str:
    return current_phase_from_lines(text.splitlines(), limit=limit)


def current_stamp_token_from_lines(lines: list[str], limit: int = PLAN_HEAD_LIMIT) -> str:
    head = lines[:limit]
    for line in head:
        if is_current_line(line):
            match = STAMP_TOKEN_RE.search(line)
            if match:
                return match.group(1)
    return ""


def current_stamp_token_from_text(text: str, limit: int = PLAN_HEAD_LIMIT) -> str:
    return current_stamp_token_from_lines(text.splitlines(), limit=limit)


def done_criteria_line(plan_text: str) -> str:
    for line in plan_text.splitlines()[:PLAN_HEAD_LIMIT]:
        if "Done Criteria" in line:
            return line.strip()
    return ""


def phase_files_for(top: Path, phase_id: str) -> list[Path]:
    if not phase_id:
        return []
    top_phase = phase_id.split(".", 1)[0]
    phase_dir = top / "_phases"
    return sorted(phase_dir.glob(f"{top_phase}_*.md")) if phase_dir.is_dir() else []


def phase_file_groups(top: Path) -> dict[str, list[Path]]:
    phase_dir = top / "_phases"
    groups: dict[str, list[Path]] = {}
    if not phase_dir.is_dir():
        return groups
    for path in sorted(phase_dir.glob("P*_*.md")):
        top_phase = path.name.split("_", 1)[0]
        if re.fullmatch(r"P\d+", top_phase):
            groups.setdefault(top_phase, []).append(path)
    return groups


def frontmatter_value(text: str, key: str) -> str:
    lines = text.lstrip("\ufeff\r\n\t ").splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    for line in lines[1:]:
        if line.strip() == "---":
            break
        match = re.match(rf"^\s*{re.escape(key)}\s*:\s*['\"]?([^'\"\s#]+)", line)
        if match:
            return match.group(1)
    return ""


def latest_markdown(directory: Path, exclude: set[str] | None = None) -> list[Path]:
    if not directory.is_dir():
        return []
    exclude = exclude or set()
    files = [p for p in directory.glob("*.md") if p.name not in exclude]

    def sort_key(path: Path) -> tuple[str, float]:
        stat = path.stat()
        match = DATE_PREFIX_RE.match(path.name)
        date_key = match.group(1) if match else datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d")
        return (date_key, stat.st_mtime)

    return sorted(files, key=sort_key, reverse=True)


def has_heading(text: str, headings: tuple[str, ...]) -> bool:
    escaped = "|".join(re.escape(item) for item in headings)
    return bool(re.search(rf"(?m)^#+\s*({escaped})\s*$", text, re.I))


def migration_context(path: Path) -> bool:
    lowered = [part.lower() for part in path.parts]
    name = path.name.lower()
    legacy_dir = any(
        part == "legacy" and index > 0 and lowered[index - 1] in {"top", "_top"}
        for index, part in enumerate(lowered)
    )
    migration_names = (
        name.startswith("migration")
        or name.startswith("_migration")
        or name.startswith("overturn")
        or name.startswith("_overturn")
        or "-migration" in name
        or "_migration" in name
        or "-overturn" in name
        or "_overturn" in name
    )
    return (
        "_external_reviews" in lowered
        or "_legacy" in lowered
        or legacy_dir
        or migration_names
    )
