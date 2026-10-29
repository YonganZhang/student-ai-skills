#!/usr/bin/env python3
"""Audit top-level SKILL.md file references without confusing mounted paths."""

from __future__ import annotations

import glob
import re
import sys
from dataclasses import dataclass
from pathlib import Path


TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_./~:-])("
    r"(?:~/(?:\.codex|\.claude|\.agents)/[A-Za-z0-9_./*-]+)"
    r"|(?:[A-Za-z0-9_-]+/)?(?:references|scripts|sub-skills)/[A-Za-z0-9_./*-]+"
    r")"
)
EXT_RE = re.compile(r"\.(?:md|py|sh|js|ts|mjs|json|yaml|yml|toml|txt|tex)$")
ARCHIVE_MARKERS = {"_legacy", "_archive", "_old", "legacy", "archive", "archived"}


@dataclass(frozen=True)
class Ref:
    status: str
    skill: str
    token: str
    line_no: int
    reason: str


def is_archived(path: Path) -> bool:
    return bool({part.lower() for part in path.parts} & ARCHIVE_MARKERS)


def normalize_token(raw: str) -> str:
    return raw.rstrip(".,;:，。；：)`]}>\"'")


def target_exists(path: Path) -> bool:
    if "*" in str(path):
        return any(Path(match).exists() for match in glob.glob(str(path)))
    return path.exists()


def classify(repo: Path, skill_md: Path, token: str, line: str) -> tuple[str, str]:
    skill_dir = skill_md.parent

    if token.startswith("~/"):
        expanded = Path(token).expanduser()
        if target_exists(expanded):
            return "ok-absolute", str(expanded)
        return "missing", f"absolute path not found: {expanded}"

    if token.startswith("scripts/"):
        local = skill_dir / token
        if target_exists(local):
            return "ok-local", str(local)
        mounted = repo / token
        if target_exists(mounted):
            return "ok-mounted-script", str(mounted)
        if "paperfit run" in line or "$(paperfit root)" in line or "paperfit root" in line:
            return "ok-package-script", "resolved by paperfit CLI package root"
        return "missing", f"not local or mounted: {local}"

    if token.startswith(("references/", "sub-skills/")):
        local = skill_dir / token
        if target_exists(local):
            return "ok-local", str(local)
        return "missing", f"local reference not found: {local}"

    # Cross-skill path, e.g. other-skill/references/topic.md.
    cross = repo / "skills" / token
    if target_exists(cross):
        return "ok-cross-skill", str(cross)

    return "missing", f"cross-skill path not found: {cross}"


def audit_repo(repo_arg: str) -> list[Ref]:
    repo = Path(repo_arg).expanduser().resolve()
    skills = repo / "skills"
    if not skills.exists():
        raise SystemExit(f"[ERROR] skills dir not found: {skills}")

    refs: list[Ref] = []
    for skill_md in sorted(skills.glob("*/SKILL.md")):
        if is_archived(skill_md):
            continue
        text = skill_md.read_text(encoding="utf-8", errors="replace")
        seen: set[tuple[str, int]] = set()
        for line_no, line in enumerate(text.splitlines(), start=1):
            for match in TOKEN_RE.finditer(line):
                token = normalize_token(match.group(1))
                if not EXT_RE.search(token):
                    continue
                key = (token, line_no)
                if key in seen:
                    continue
                seen.add(key)
                status, reason = classify(repo, skill_md, token, line)
                refs.append(Ref(status, skill_md.parent.name, token, line_no, reason))
    return refs


def main(argv: list[str]) -> int:
    default_repo = Path(__file__).resolve().parents[3]
    repos = argv[1:] or [str(default_repo)]
    all_refs: list[tuple[str, Ref]] = []
    for repo in repos:
        all_refs.extend((repo, ref) for ref in audit_repo(repo))

    print("=== Skill reference audit ===")
    for repo in repos:
        refs = [ref for repo_name, ref in all_refs if repo_name == repo]
        print(f"{repo}: {len(refs)} refs")
        counts: dict[str, int] = {}
        for ref in refs:
            counts[ref.status] = counts.get(ref.status, 0) + 1
        for status in sorted(counts):
            print(f"  {status}: {counts[status]}")

    missing = [(repo, ref) for repo, ref in all_refs if ref.status == "missing"]
    if missing:
        print("\nMissing references:")
        for repo, ref in missing:
            print(f"  - {repo}:{ref.skill}:{ref.line_no} `{ref.token}` -> {ref.reason}")
        return 1

    print("\nOK: no missing top-level skill references")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
