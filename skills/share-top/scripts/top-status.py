#!/usr/bin/env python3
"""Print a compact TOP status summary for v4 projects.

Read-only. Intended for AI cold-start and handoff.
"""

from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path

from top_common import (
    PLAN_HEAD_LIMIT,
    current_phase_from_lines,
    current_stamp_token_from_lines,
    derive_next_item,
    first_match,
    latest_markdown,
    parse_plan,
    plan_invariant_errors,
    phase_files_for,
    project_root,
    read_lines,
)
from topic_brief import top_paths


SKIP_MARKDOWN = {"_template.md", "_readme.md", "README.md"}
CHECKBOX_RE = re.compile(r"^\s*[-*]\s+\[([ xX])\]\s+")


def checkbox_summary(lines: list[str]) -> tuple[int, int, int]:
    done = 0
    open_ = 0
    for line in lines:
        match = CHECKBOX_RE.match(line)
        if not match:
            continue
        if match.group(1).lower() == "x":
            done += 1
        else:
            open_ += 1
    return done, open_, done + open_


def mtime_iso(path: Path) -> str:
    if not path.is_file():
        return "(missing)"
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")


def collect_status(root: Path) -> dict:
    """采集**有界视图**(给 sixone CLI / 无记忆 AI 冷启动用): 当前 stamp + 下一步 +
    最近 K 条 log/finding。读时截断, 不返回无界全文。契约: sixone-status/v1。"""
    top, plan, kind = top_paths(root)
    if not top or not plan:
        top = root / "_wiki-methodology" / "_top"
        plan = top / "_task_plan.md"
    if not plan.is_file():
        return {"schema_version": "sixone-status/v1", "tool": "top-status", "project": str(root),
                "view": {"task_plan": "missing"}}
    lines = read_lines(plan)
    plan_state = parse_plan(plan)
    phase_id = current_phase_from_lines(lines)
    stamp = first_match(lines[:PLAN_HEAD_LIMIT], r"🧭|当前|Current")
    done = first_match(lines[:PLAN_HEAD_LIMIT], r"Done Criteria")
    phase_files = phase_files_for(top, phase_id)
    phase_file = phase_files[0] if len(phase_files) == 1 else None
    checklist = None
    reboot_card = None
    plan_errors = []
    if plan_state.active_start is not None:
        counts = {
            state: sum(1 for item in plan_state.items if item.state == state)
            for state in ("pending", "in_progress", "blocked", "done", "cancelled")
        }
        current_item = next((item for item in plan_state.items if item.state == "in_progress"), None)
        next_item = derive_next_item(plan_state)
        checklist = {
            "done": counts["done"] + counts["cancelled"],
            "open": counts["pending"] + counts["in_progress"] + counts["blocked"],
            "total": len(plan_state.items),
            "states": counts,
        }
        reboot_card = {
            "goal": plan_state.coordinate.get("goal") or None,
            "current": f"{current_item.id} {current_item.title}" if current_item else None,
            "next": f"{next_item.id} {next_item.title}" if next_item else None,
            "completed": f"{checklist['done']}/{checklist['total']}",
            "latest_learning": plan_state.coordinate.get("latest_learning") or None,
            "blocker": plan_state.coordinate.get("blocker") or None,
        }
        plan_errors = [
            {"code": code, "message": message}
            for code, message in plan_invariant_errors(plan_state)
        ]
    elif phase_file:
        pl = read_lines(phase_file)
        d, o, t = checkbox_summary(pl)
        checklist = {"done": d, "open": o, "total": t}
    logs = latest_markdown(top / "_logs", SKIP_MARKDOWN)
    findings = latest_markdown(top / "_findings", SKIP_MARKDOWN)
    recent_log = None
    if logs:
        tail = [ln[:160] for ln in read_lines(logs[0])[-8:] if ln.strip()]
        recent_log = {"file": str(logs[0].relative_to(root)), "tail": tail}
    return {
        "schema_version": "sixone-status/v1",
        "tool": "top-status",
        "project": str(root),
        "kind": kind,
        "view": {
            "stamp": stamp,
            "phase_id": phase_id,
            "done_criteria": done,
            "current_phase_file": str(phase_file.relative_to(root)) if phase_file else None,
            "checklist": checklist,
            "reboot_card": reboot_card,
            "plan_errors": plan_errors,
            "freshness": {
                "task_plan_updated": mtime_iso(plan),
                "latest_log_updated": mtime_iso(logs[0]) if logs else None,
            },
            "recent_log": recent_log,
            "recent_findings": [str(f.relative_to(root)) for f in findings[:5]],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", nargs="?", default=".", help="project root")
    parser.add_argument("--json", action="store_true", help="machine-readable bounded view (sixone-status/v1)")
    args = parser.parse_args()
    if args.json:
        import json
        print(json.dumps(collect_status(project_root(Path(args.project))), ensure_ascii=False, indent=2))
        return 0

    root = project_root(Path(args.project))
    top, plan, kind = top_paths(root)
    if not top or not plan:
        top = root / "_wiki-methodology" / "_top"
        plan = top / "_task_plan.md"
    lines = read_lines(plan)
    plan_state = parse_plan(plan) if plan.is_file() else None

    print(f"# TOP Status: {root.name}")
    print()

    if plan_state and plan_state.active_start is not None:
        current_item = next((item for item in plan_state.items if item.state == "in_progress"), None)
        next_item = derive_next_item(plan_state)
        closed = sum(1 for item in plan_state.items if item.closed)
        print("## Recovery Card")
        print(f"- goal: {plan_state.coordinate.get('goal') or '(missing)'}")
        print(f"- current: {current_item.id + ' ' + current_item.title if current_item else 'none'}")
        print(f"- next: {next_item.id + ' ' + next_item.title if next_item else 'none'}")
        print(f"- completed: {closed}/{len(plan_state.items)}")
        print(f"- latest_learning: {plan_state.coordinate.get('latest_learning') or 'none'}")
        print(f"- blocker: {plan_state.coordinate.get('blocker') or 'none'}")
        print()
    if not plan.is_file():
        print("status: no TOP plan found")
        print("task_plan: missing")
        print("expected_current_standard: _wiki-methodology/_top/_task_plan.md")
        return 0

    print(f"project: {root}")
    print(f"top: {top.relative_to(root)}")
    print(f"task_plan: present")
    print(f"kind: {kind}")
    if kind != "v4":
        print("upgrade_note: non-standard TOP is readable compatibility; migrate deliberately to v4 when asked.")
    print()

    phase_id = current_phase_from_lines(lines)
    stamp_token = current_stamp_token_from_lines(lines)
    stamp = first_match(lines[:PLAN_HEAD_LIMIT], r"🧭|当前|Current")
    done = first_match(lines[:PLAN_HEAD_LIMIT], r"Done Criteria")
    if phase_id:
        phase_display = phase_id
    elif stamp_token:
        phase_display = "(non-P stamp)"
    else:
        phase_display = "(unknown)"
    print("## Current")
    print(f"- stamp: {stamp or '(missing)'}")
    print(f"- phase_id: {phase_display}")
    print(f"- done_criteria: {done or '(missing)'}")
    print()

    phase_files = phase_files_for(top, phase_id)
    phase_file = phase_files[0] if len(phase_files) == 1 else None
    print("## Next Files")
    print(f"- task_plan: {plan.relative_to(root)}")
    if len(phase_files) > 1:
        print(f"- current_phase: ambiguous for {phase_id}")
        for item in phase_files:
            print(f"  - {item.relative_to(root)}")
    elif phase_file:
        print(f"- current_phase: {phase_file.relative_to(root)}")
    elif phase_id:
        print(f"- current_phase: missing for {phase_id}")
    else:
        print("- current_phase: unknown")
    print()

    if plan_state and plan_state.active_start is not None:
        print("## Active Work")
        for item in plan_state.items[:8]:
            print(f"- {item.id}: {item.state} · {item.title}")
        if len(plan_state.items) > 8:
            print(f"- ... {len(plan_state.items) - 8} more")
        print()
    elif phase_file:
        phase_lines_all = read_lines(phase_file)
        phase_lines_head = phase_lines_all[:24]
        substeps = [line.strip() for line in phase_lines_head if CHECKBOX_RE.match(line)]
        done_count, open_count, total_count = checkbox_summary(phase_lines_all)
        print("## Current Phase")
        if total_count:
            print(f"- checklist: done={done_count} open={open_count} total={total_count}")
        for line in substeps[:6]:
            print(line)
        if not substeps:
            title = first_match(phase_lines_head, r"^#")
            print(f"- {title or '(no sub-steps found)'}")
        print()

    logs = latest_markdown(top / "_logs", SKIP_MARKDOWN)
    print("## Freshness")
    print(f"- task_plan_updated: {mtime_iso(plan)}")
    if logs:
        print(f"- latest_log_updated: {mtime_iso(logs[0])}")
    else:
        print("- latest_log_updated: none")
    print()

    print("## Recent Logs")
    if logs:
        latest = logs[0]
        print(f"- file: {latest.relative_to(root)}")
        tail = read_lines(latest)[-8:]
        for line in tail:
            if line.strip():
                print(f"  {line[:160]}")
    else:
        print("- none")
    print()

    findings = latest_markdown(top / "_findings", SKIP_MARKDOWN)
    print("## Recent Findings")
    if findings:
        for item in findings[:5]:
            print(f"- {item.relative_to(root)}")
    else:
        print("- none")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
