#!/usr/bin/env python3
"""Emit a tiny TOP working-memory brief for hooks."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from top_common import (
    PLAN_HEAD_LIMIT,
    current_phase_from_lines,
    done_criteria_line,
    first_match,
    latest_markdown,
    phase_files_for,
    project_root,
    read_lines,
    read_text,
    rel,
)


CHECKBOX_RE = re.compile(r"^\s*[-*]\s+\[([ xX])\]\s+(.*)")
SKIP_MARKDOWN = {"_template.md", "_readme.md", "README.md"}


def compact(text: str, limit: int = 180) -> str:
    clean = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text).strip()
    clean = re.sub(r"\s+", " ", clean)
    return clean[:limit]


def markdown_title(path: Path) -> str:
    for line in read_lines(path, 40):
        if line.startswith("#"):
            return compact(line.lstrip("# "))
    return path.stem


def checkbox_counts(lines: list[str]) -> tuple[int, int, int, list[str]]:
    done = 0
    open_ = 0
    next_open: list[str] = []
    for line in lines:
        match = CHECKBOX_RE.match(line)
        if not match:
            continue
        if match.group(1).lower() == "x":
            done += 1
        else:
            open_ += 1
            if len(next_open) < 3:
                next_open.append(compact(match.group(2), 140))
    return done, open_, done + open_, next_open


def latest_entries(directory: Path, root: Path, limit: int) -> list[str]:
    entries = []
    for path in latest_markdown(directory, SKIP_MARKDOWN)[:limit]:
        entries.append(compact(f"{rel(path, root)} — {markdown_title(path)}", 220))
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", nargs="?", default=".")
    parser.add_argument("--limit", type=int, default=1)
    args = parser.parse_args()

    limit = max(0, min(args.limit, 5))
    root = project_root(Path(args.project))
    top = root / "_wiki-methodology" / "_top"
    plan = top / "_task_plan.md"
    if not top.is_dir() or not plan.is_file():
        return 0

    plan_lines = read_lines(plan)
    phase_id = current_phase_from_lines(plan_lines)
    stamp = first_match(plan_lines[:PLAN_HEAD_LIMIT], r"🧭|当前|Current")
    done = done_criteria_line(read_text(plan))
    phase_files = phase_files_for(top, phase_id)
    phase_file = phase_files[0] if len(phase_files) == 1 else None

    print("[TOP Brief]")
    print(f"project: {root}")
    print(f"task_plan: {rel(plan, root)}")
    if stamp:
        print(f"stamp: {compact(stamp)}")
    if done:
        print(f"done: {compact(done)}")
    if phase_file:
        print(f"phase_file: {rel(phase_file, root)}")
        done_count, open_count, total_count, next_open = checkbox_counts(read_lines(phase_file))
        if total_count:
            print(f"phase_checklist: done={done_count} open={open_count} total={total_count}")
        for item in next_open:
            print(f"next_open: {item}")
    elif phase_id:
        print(f"phase_file: missing for {phase_id}")

    for label, directory in (
        ("recent_decision", top / "_decisions"),
        ("recent_finding", top / "_findings"),
        ("recent_review", top / "_external_reviews"),
        ("recent_log", top / "_logs"),
    ):
        for item in latest_entries(directory, root, limit):
            print(f"{label}: {item}")

    print("rule: TOP is state/context; edit via top-update.py when recording progress.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
