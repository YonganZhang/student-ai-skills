#!/usr/bin/env python3
"""Audit skill routing metadata for router/book discipline."""

from __future__ import annotations

import re
import sys
from collections import defaultdict
import os
from pathlib import Path


DESC_LIMIT = 700
DESC_SOFT_LIMIT = 180
AGENT_LOCK_PATTERNS = [
    re.compile(r"Claude\s*(必须|主会话|一定要|只能)"),
    re.compile(r"Codex\s*(必须|主会话|一定要|只能)"),
    re.compile(r"Task\s*(工具|tool)\s*(必须|只能|优先)?"),
]
ARCHIVE_MARKERS = {"_legacy", "_archive", "_old", "legacy", "archive", "archived"}
ROUTER_HINTS = ("router", "route", "路由", "子技能", "sub-skill", "subskill", "references/sub-skills")


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    data: dict[str, str] = {}
    lines = text[4:end].splitlines()
    i = 0
    while i < len(lines):
        raw_line = lines[i]
        if ":" not in raw_line:
            i += 1
            continue
        key, value = raw_line.split(":", 1)
        value = value.strip()
        if value in {">", "|", ">-", "|-", ">+", "|+"}:
            folded: list[str] = []
            j = i + 1
            while j < len(lines) and (lines[j].startswith(" ") or lines[j].startswith("\t")):
                folded.append(lines[j].strip())
                j += 1
            value = " ".join(part for part in folded if part)
            i = j - 1
        elif not value:
            folded: list[str] = []
            j = i + 1
            while j < len(lines) and (lines[j].startswith(" ") or lines[j].startswith("\t")):
                folded.append(lines[j].strip())
                j += 1
            value = " ".join(part for part in folded if part)
            i = j - 1
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        data[key.strip()] = value
        i += 1
    return data


def is_archived(path: Path) -> bool:
    lowered = {part.lower() for part in path.parts}
    return bool(lowered & ARCHIVE_MARKERS)


def has_child_skills(skill_md: Path) -> bool:
    root = skill_md.parent
    candidates = [
        root / "references" / "sub-skills",
        root / "sub-skills",
        root / "tools",
        root / "baselines",
    ]
    return any(base.exists() and any(base.rglob("SKILL.md")) for base in candidates)


def is_top_level(skill_md: Path, roots: list[Path]) -> bool:
    for root in roots:
        try:
            rel = skill_md.relative_to(root)
        except ValueError:
            continue
        return len(rel.parts) == 2
    return False


# Platform-managed skill trees (Claude plugin sync, Codex system skills); not ours to audit.
PLATFORM_MANAGED = {"synced", ".system"}


def find_skill_files(root: Path) -> list[Path]:
    """SKILL.md files under root. Follows symlinks: shared skills are symlinked into
    ~/.claude/skills and ~/.agents/skills, and Path.rglob does not follow them."""
    found, seen = [], set()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
        dirnames[:] = sorted(d for d in dirnames if d not in PLATFORM_MANAGED)
        if "SKILL.md" in filenames:
            path = Path(dirpath) / "SKILL.md"
            if path.resolve() not in seen:
                seen.add(path.resolve())
                found.append(path)
    return found


def main(argv: list[str]) -> int:
    default_root = Path(__file__).resolve().parents[2]
    roots = [Path(arg).expanduser().resolve() for arg in argv[1:]] or [default_root]
    roots = [root for root in roots if root.exists()]
    if not roots:
        print("[ERROR] no existing skill roots")
        return 2

    skill_files = sorted({path for root in roots for path in find_skill_files(root)})
    failures: list[str] = []
    warnings: list[str] = []
    names: defaultdict[str, list[Path]] = defaultdict(list)

    for skill_md in skill_files:
        text = skill_md.read_text(encoding="utf-8", errors="replace")
        meta = parse_frontmatter(text)
        name = meta.get("name", "").strip()
        desc = meta.get("description", "").strip()
        rel = str(skill_md)

        if not name:
            failures.append(f"missing name: {rel}")
        else:
            names[name].append(skill_md)

        if not desc:
            failures.append(f"missing description: {rel}")
        elif len(desc) > DESC_LIMIT:
            failures.append(f"description too long ({len(desc)}>{DESC_LIMIT}): {rel}")
        elif len(desc) > DESC_SOFT_LIMIT:
            warnings.append(f"description should be compressed ({len(desc)}>{DESC_SOFT_LIMIT}): {rel}")

        if is_archived(skill_md):
            failures.append(f"archived/legacy path still exposes SKILL.md: {rel}")

        for pattern in AGENT_LOCK_PATTERNS:
            if pattern.search(text):
                failures.append(f"agent-specific hard lock in skill body: {rel}")
                break

        if has_child_skills(skill_md) and is_top_level(skill_md, roots):
            body = text[text.find("\n---", 4) + 4 :] if text.startswith("---\n") and text.find("\n---", 4) != -1 else text
            if not any(hint in body for hint in ROUTER_HINTS):
                failures.append(f"top-level skill has children but no obvious router hints: {rel}")

    for name, paths in names.items():
        if len(paths) > 1:
            joined = ", ".join(str(path) for path in paths)
            failures.append(f"duplicate skill name '{name}': {joined}")

    nested = [path for path in skill_files if not is_top_level(path, roots)]

    print("=== Skill routing audit ===")
    print(f"roots: {', '.join(str(root) for root in roots)}")
    print(f"visible SKILL.md files: {len(skill_files)}")
    print(f"nested SKILL.md files: {len(nested)}")

    if warnings:
        print("\nWarnings:")
        for item in warnings:
            print(f"  - {item}")

    if failures:
        print("\nFailures:")
        for item in failures:
            print(f"  - {item}")
        return 1

    print("\nOK: routing metadata passed hard checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
