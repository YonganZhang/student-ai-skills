#!/usr/bin/env python3
"""Write structured TOP progress entries.

Keeps task state in v4 TOP files instead of ad-hoc plan/progress files.
"""

from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path

from top_common import PHASE_ID_RE, current_phase_from_text, project_root, read_text, rel


SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
STAMP_LINE_RE = re.compile(r"^\s*>\s*\*{0,2}(?:🧭\s*)?(当前|current)\s*:", re.I)
DONE_LINE_RE = re.compile(r"^\s*>?\s*done criteria\s*:", re.I)


def slugify(text: str) -> str:
    slug = SLUG_RE.sub("-", text.strip().lower()).strip("-._")
    return slug[:80] or "entry"


def ensure_top(root: Path) -> Path:
    candidates = [
        root / "_wiki-methodology" / "_top",
        root / "wiki-methodology" / "top",
    ]
    for top in candidates:
        if top.is_dir():
            return top
    raise SystemExit(f"ERR: TOP not found: {candidates[0]} or {candidates[1]}")


def topic_name(top: Path, name: str) -> str:
    if top.name == "_top":
        return f"_{name}"
    return name


def topic_dir(top: Path, name: str) -> Path:
    candidates = [top / topic_name(top, name), top / f"_{name}", top / name]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


def task_plan_name(top: Path) -> str:
    return topic_name(top, "task_plan.md")


def entry_stem(today: str, *parts: str) -> str:
    return "_" + "_".join(part for part in (today, *parts) if part)


def current_phase(top: Path) -> str:
    return current_phase_from_text(read_text(top / task_plan_name(top)))


def phase_for_entry(top: Path, args: argparse.Namespace) -> str:
    phase_id = args.phase or current_phase(top)
    if not phase_id:
        raise SystemExit("ERR: no current P-phase found; pass --phase P<N>[.<sub>]")
    if not PHASE_ID_RE.fullmatch(phase_id):
        raise SystemExit(f"ERR: invalid phase_id: {phase_id}")
    return phase_id


def require_one_line(value: str, field: str) -> str:
    if "\n" in value or "\r" in value or CONTROL_RE.search(value):
        raise SystemExit(f"ERR: {field} must be a single clean line")
    return value


def yaml_scalar(value: str, field: str) -> str:
    value = require_one_line(value, field)
    return "'" + value.replace("'", "''") + "'"


def unique_path(directory: Path, stem: str) -> Path:
    path = directory / f"{stem}.md"
    if not path.exists():
        return path
    for index in range(2, 100):
        candidate = directory / f"{stem}_{index}.md"
        if not candidate.exists():
            return candidate
    raise SystemExit(f"ERR: too many duplicate entries for {stem}")


def yaml_header(phase_id: str, **fields: str) -> str:
    require_one_line(phase_id, "phase_id")
    lines = ["---", f"phase_id: {phase_id}"]
    for key, value in fields.items():
        if value:
            lines.append(f"{key}: {yaml_scalar(value, key)}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def bullet_lines(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- none"


def write_finding(top: Path, args: argparse.Namespace) -> Path:
    phase_id = phase_for_entry(top, args)
    today = datetime.now().date().isoformat()
    slug = slugify(args.slug or args.title)
    text = (
        yaml_header(phase_id, kind="finding", status=args.status or "open")
        + f"# {args.title}\n\n"
        + "## Local Case\n\n"
        + f"{args.local_case or args.summary}\n\n"
        + "## Class Pattern\n\n"
        + f"{args.class_pattern or 'TBD'}\n\n"
        + "## Evidence\n\n"
        + f"{bullet_lines(args.evidence)}\n\n"
        + "## Impact\n\n"
        + f"{args.impact or 'TBD'}\n\n"
        + "## Prevention Rule (candidate)\n\n"
        + f"{args.prevention or 'TBD'}\n\n"
        + "## Links\n\n"
        + f"- task_plan: ../{task_plan_name(top)}\n"
    )
    directory = topic_dir(top, "findings")
    directory.mkdir(parents=True, exist_ok=True)
    path = unique_path(directory, entry_stem(today, slug) if top.name == "_top" else f"{today}_{slug}")
    path.write_text(text, encoding="utf-8")
    return path


def write_decision(top: Path, args: argparse.Namespace) -> Path:
    phase_id = phase_for_entry(top, args)
    today = datetime.now().date().isoformat()
    slug = slugify(args.slug or args.title)
    text = (
        yaml_header(phase_id, kind="decision", status=args.status or "active")
        + f"# Decision: {args.title}\n\n"
        + "## Request / Constraint\n\n"
        + f"{args.request or 'not recorded'}\n\n"
        + "## Decision\n\n"
        + f"{args.summary}\n\n"
        + "## Rationale\n\n"
        + f"{args.rationale or 'TBD'}\n\n"
        + "## Alternatives Considered\n\n"
        + f"{bullet_lines(args.alternative)}\n\n"
        + "## 涉及代码 (Code References)\n\n"
        + "<!-- 文件路径::函数/符号名；record for-file 按这里和 git Decision: trailer 找回本记录 -->\n"
        + f"{bullet_lines(args.file)}\n\n"
        + "## Verification (reported, not executed by this writer)\n\n"
        + f"{bullet_lines(args.test) if args.test else '- not-run: no verification supplied'}\n\n"
        + "## Evidence\n\n"
        + f"{bullet_lines(args.evidence)}\n\n"
        + "## Provenance\n\n"
        + f"{bullet_lines(args.source) if args.source else '- unknown: source not supplied'}\n\n"
        + f"- commit (reported association, not authorship proof): {args.commit or 'unknown / not supplied'}\n\n"
        + "## Follow-up\n\n"
        + f"{args.follow_up or 'none'}\n"
        + "".join(f"\nsupersedes: {old}\n" for old in args.supersedes)
    )
    directory = topic_dir(top, "decisions")
    directory.mkdir(parents=True, exist_ok=True)
    path = unique_path(directory, entry_stem(today, slug) if top.name == "_top" else f"{today}_{slug}")
    path.write_text(text, encoding="utf-8")
    return path


def write_review(top: Path, args: argparse.Namespace) -> Path:
    phase_id = phase_for_entry(top, args)
    today = datetime.now().date().isoformat()
    reviewer = slugify(args.reviewer or "external")
    slug = slugify(args.slug or args.title)
    text = (
        yaml_header(phase_id, reviewer=args.reviewer or "external", status=args.status or "pending")
        + f"# External Review: {args.title}\n\n"
        + "## Scope\n\n"
        + f"{args.summary}\n\n"
        + "## Reviewer Conclusion\n\n"
        + f"{args.conclusion or 'TBD'}\n\n"
        + "## Adoption Decision\n\n"
        + f"{args.adoption or 'pending'}\n\n"
        + "## Evidence\n\n"
        + f"{bullet_lines(args.evidence)}\n\n"
        + "## Follow-up\n\n"
        + f"{args.follow_up or 'none'}\n"
    )
    directory = topic_dir(top, "external_reviews")
    directory.mkdir(parents=True, exist_ok=True)
    path = unique_path(directory, entry_stem(today, reviewer, slug) if top.name == "_top" else f"{today}_{reviewer}_{slug}")
    path.write_text(text, encoding="utf-8")
    return path


def append_log(top: Path, args: argparse.Namespace) -> Path:
    phase_id = phase_for_entry(top, args)
    today = datetime.now().date().isoformat()
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    header = yaml_header(phase_id, kind="log")
    entry = (
        f"## {now} — {args.title}\n\n"
        + f"{args.summary}\n\n"
        + "### Files\n\n"
        + f"{bullet_lines(args.file)}\n\n"
        + "### Verification\n\n"
        + f"{bullet_lines([*args.test, *args.evidence])}\n\n"
    )
    directory = topic_dir(top, "logs")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (f"_{today}.md" if top.name == "_top" else f"{today}.md")
    if not path.exists():
        path.write_text(header + f"# Log {today}\n\n", encoding="utf-8")
    path.write_text(read_text(path).rstrip() + "\n\n" + entry, encoding="utf-8")
    return path


def update_stamp(top: Path, args: argparse.Namespace) -> Path:
    plan = top / task_plan_name(top)
    text = read_text(plan)
    if not text:
        raise SystemExit(f"ERR: missing task plan: {plan}")
    phase_id = phase_for_entry(top, args)
    title = require_one_line(args.title, "title")
    done_criteria = require_one_line(args.done_criteria, "done_criteria")
    stamp = f"> **🧭 当前: [{phase_id}] {title}**"
    done = f"> Done Criteria: {done_criteria}"
    lines = text.splitlines()
    stamp_done = False
    done_done = False
    out: list[str] = []
    for line in lines:
        if not stamp_done and STAMP_LINE_RE.search(line):
            out.append(stamp)
            stamp_done = True
        elif not done_done and DONE_LINE_RE.search(line):
            out.append(done)
            done_done = True
        else:
            out.append(line)
    insert_at = 1 if out else 0
    if not stamp_done:
        out.insert(insert_at, stamp)
        insert_at += 1
    if not done_done:
        out.insert(insert_at, done)
    plan.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    return plan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=["finding", "decision", "review", "log", "stamp"])
    parser.add_argument("project", nargs="?", default=".")
    parser.add_argument("--title", required=True)
    parser.add_argument("--summary", default="")
    parser.add_argument("--phase")
    parser.add_argument("--slug")
    parser.add_argument("--status")
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--local-case")
    parser.add_argument("--class-pattern")
    parser.add_argument("--impact")
    parser.add_argument("--prevention")
    parser.add_argument("--rationale")
    parser.add_argument("--request", help="decision: original requirement or constraint, summarized")
    parser.add_argument("--source", action="append", default=[], help="decision: explicit task/session/message reference")
    parser.add_argument("--commit", help="decision: known associated commit; never guessed from HEAD")
    parser.add_argument("--supersedes", action="append", default=[],
                        help="decision: path of an older decision this one replaces (old record is kept)")
    parser.add_argument("--alternative", action="append", default=[])
    parser.add_argument("--follow-up")
    parser.add_argument("--reviewer")
    parser.add_argument("--conclusion")
    parser.add_argument("--adoption")
    parser.add_argument("--file", action="append", default=[])
    parser.add_argument("--test", action="append", default=[])
    parser.add_argument("--done-criteria")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    require_one_line(args.title, "title")
    if args.kind != "stamp" and not args.summary:
        raise SystemExit("ERR: --summary is required")
    if args.kind == "stamp" and not args.done_criteria:
        raise SystemExit("ERR: --done-criteria is required for stamp")

    if args.kind != "decision" and any((args.request, args.source, args.commit,
                                        args.rationale, args.alternative, args.supersedes)):
        raise SystemExit("ERR: request/source/commit/rationale/alternative/supersedes require kind=decision")
    for old in args.supersedes:
        require_one_line(old, "supersedes")
    if args.kind not in {"decision", "log"} and (args.file or args.test):
        raise SystemExit("ERR: file/test require kind=decision or log")
    if args.kind not in {"decision", "review"} and args.follow_up:
        raise SystemExit("ERR: follow-up requires kind=decision or review")

    root = project_root(Path(args.project))
    top = ensure_top(root)
    handlers = {
        "finding": write_finding,
        "decision": write_decision,
        "review": write_review,
        "log": append_log,
        "stamp": update_stamp,
    }
    path = handlers[args.kind](top, args)
    print(f"{args.kind}: {rel(path, root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
