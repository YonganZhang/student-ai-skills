#!/usr/bin/env python3
"""Diagnose TOP finding/review lifecycle drift."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from top_common import rel
from topic_brief import find_project_root


ACTIVE_FINDING_STATUSES = {"open", "accepted"}
ACTIVE_REVIEW_STATUSES = {"pending", "open", "accepted"}
TERMINAL_STATUSES = {"fixed", "superseded", "rejected", "archived"}
REVIEW_TERMINAL_STATUSES = TERMINAL_STATUSES | {"adopted", "closed"}
KNOWN_FINDING_STATUSES = ACTIVE_FINDING_STATUSES | TERMINAL_STATUSES
KNOWN_REVIEW_STATUSES = ACTIVE_REVIEW_STATUSES | REVIEW_TERMINAL_STATUSES
SKIP_NAMES = {"README.md", "INDEX.md", "_template.md", "template.md"}
ADOPTION_PENDING_RE = re.compile(r"adoption decision\s*[:\n]+\s*pending", re.I)
CLOSURE_EVIDENCE_RE = re.compile(r"(closure evidence|closure_evidence)\s*[:\n]", re.I)


@dataclass
class Issue:
    severity: str
    code: str
    path: str
    message: str


def top_roots(root: Path) -> list[Path]:
    candidates = [
        root / "_wiki-methodology" / "_top",
        root / "wiki-methodology" / "top",
        root / "_top",
        root / "top",
    ]
    return [path for path in candidates if path.is_dir()]


def lifecycle_dirs(top: Path, kind: str) -> list[Path]:
    names = {
        "findings": ("_findings", "findings"),
        "reviews": ("_external_reviews", "external_reviews"),
    }[kind]
    return [top / name for name in names if (top / name).is_dir()]


def markdown_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for directory in paths:
        for path in sorted(directory.glob("*.md")):
            if path.name in SKIP_NAMES:
                continue
            files.append(path)
    return files


def parse_frontmatter(path: Path) -> tuple[dict[str, Any], str, str | None]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text, None
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text, "frontmatter is not closed"
    raw = text[4:end]
    body = text[end + 4 :]
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        return {}, body, str(exc).splitlines()[0]
    if not isinstance(data, dict):
        return {}, body, "frontmatter is not a mapping"
    return data, body, None


def metadata_value(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    return str(value).strip() if value is not None else ""


def has_closure_evidence(data: dict[str, Any], body: str) -> bool:
    return bool(metadata_value(data, "closure_evidence") or CLOSURE_EVIDENCE_RE.search(body))


def check_finding(path: Path, root: Path) -> list[Issue]:
    data, body, error = parse_frontmatter(path)
    target = rel(path, root)
    if error:
        return [Issue("block", "FINDING_FRONTMATTER_INVALID", target, error)]

    issues: list[Issue] = []
    status = metadata_value(data, "status").lower()
    if not status:
        issues.append(Issue("warn", "FINDING_STATUS_MISSING", target, "missing status; use open/accepted/fixed/rejected/superseded/archived"))
        status = "open"
    elif status not in KNOWN_FINDING_STATUSES:
        issues.append(Issue("warn", "FINDING_STATUS_UNKNOWN", target, f"status={status}"))

    if status in ACTIVE_FINDING_STATUSES:
        if not metadata_value(data, "owner_col"):
            issues.append(Issue("warn", "FINDING_OWNER_MISSING", target, "active finding has no owner_col"))
        if status == "accepted" and not metadata_value(data, "phase_id"):
            issues.append(Issue("warn", "FINDING_PHASE_MISSING", target, "accepted finding should point to phase_id"))

    if status in TERMINAL_STATUSES and not has_closure_evidence(data, body):
        issues.append(Issue("block", "FINDING_CLOSURE_MISSING", target, f"status={status} needs closure_evidence"))
    return issues


def check_review(path: Path, root: Path) -> list[Issue]:
    data, body, error = parse_frontmatter(path)
    target = rel(path, root)
    if error:
        return [Issue("block", "REVIEW_FRONTMATTER_INVALID", target, error)]

    issues: list[Issue] = []
    status = metadata_value(data, "status").lower()
    if not status:
        issues.append(Issue("warn", "REVIEW_STATUS_MISSING", target, "missing status; use pending/accepted/fixed/rejected/superseded/archived"))
        status = "pending"
    elif status not in KNOWN_REVIEW_STATUSES:
        issues.append(Issue("warn", "REVIEW_STATUS_UNKNOWN", target, f"status={status}"))

    if status in ACTIVE_REVIEW_STATUSES and ADOPTION_PENDING_RE.search(body):
        issues.append(Issue("warn", "REVIEW_ADOPTION_PENDING", target, "external review still has pending adoption decision"))
    if status in REVIEW_TERMINAL_STATUSES and not has_closure_evidence(data, body):
        issues.append(Issue("block", "REVIEW_CLOSURE_MISSING", target, f"status={status} needs closure_evidence"))
    return issues


def count_active(paths: list[Path], statuses: set[str]) -> int:
    active = 0
    for path in paths:
        data, _, error = parse_frontmatter(path)
        if error:
            continue
        status = metadata_value(data, "status").lower() or next(iter(statuses))
        if status in statuses:
            active += 1
    return active


def lint_project(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    finding_files: list[Path] = []
    review_files: list[Path] = []
    for top in top_roots(root):
        finding_files.extend(markdown_files(lifecycle_dirs(top, "findings")))
        review_files.extend(markdown_files(lifecycle_dirs(top, "reviews")))

    for path in finding_files:
        issues.extend(check_finding(path, root))
    for path in review_files:
        issues.extend(check_review(path, root))

    active_findings = count_active(finding_files, ACTIVE_FINDING_STATUSES)
    if active_findings >= 8:
        issues.append(Issue("warn", "FINDING_DIGEST_NEEDED", "_wiki-methodology/_top/_findings", f"{active_findings} active findings; create active-only digest"))

    active_reviews = count_active(review_files, ACTIVE_REVIEW_STATUSES)
    if active_reviews >= 5:
        issues.append(Issue("warn", "REVIEW_DIGEST_NEEDED", "_wiki-methodology/_top/_external_reviews", f"{active_reviews} active reviews; create adoption digest"))
    return issues


def emit_text(root: Path, issues: list[Issue]) -> None:
    print(f"[finding-doctor] project={root}")
    for issue in issues:
        print(f"{issue.severity.upper()}\t{issue.code}\t{issue.path}\t{issue.message}")
    print(
        "SUMMARY: "
        + " ".join(
            f"{severity}={sum(1 for issue in issues if issue.severity == severity)}"
            for severity in ("block", "warn", "info")
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", nargs="?", default=".")
    parser.add_argument("--format", choices=["text", "tsv"], default="text")
    args = parser.parse_args()

    root = find_project_root(Path(args.project))
    issues = lint_project(root)
    if args.format == "tsv":
        for issue in issues:
            print(f"{issue.severity}\t{issue.code}\t{issue.path}\t{issue.message}")
    else:
        emit_text(root, issues)
    return 1 if any(issue.severity == "block" for issue in issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
