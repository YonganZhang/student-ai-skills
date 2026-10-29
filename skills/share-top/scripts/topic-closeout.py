#!/usr/bin/env python3
"""Check whether changed project assets have matching Topic owner updates."""

from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from topic_brief import find_project_root, top_paths


CODE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go", ".rs", ".java", ".c", ".cc", ".cpp", ".h", ".hpp", ".sh"}
DATA_SUFFIXES = {".csv", ".tsv", ".xlsx", ".xls", ".parquet", ".feather", ".jsonl", ".nc", ".zarr", ".h5", ".hdf5"}
CODE_DIRS = {"src", "lib", "app", "server", "backend", "frontend", "_code", "_pipelines", "scripts", "skills"}
TEST_DIRS = {"tests", "_tests"}
DATA_DIRS = {"data", "Dataset", "_data", "datasets"}
LIFECYCLE_DIRS = {"_tmp", "_sandbox", "_legacy", "_outputs", "_figures", "_refs"}
SSDO_PATH_RE = re.compile(r"(ssdo|audit|trace|timeline|report|status|playwright|e2e|pipeline|service|server|log)", re.I)


@dataclass
class Issue:
    severity: str
    code: str
    path: str
    message: str


def git_status(root: Path) -> list[str]:
    try:
        probe = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            text=True, capture_output=True, check=False,
        )
        if probe.returncode != 0:
            return []
        git_root = Path(probe.stdout.strip()).resolve()
        current = root.resolve()
        while current != git_root:
            if current.name.lower() in {"tmp", ".tmp", "temp"}:
                return []
            if current.parent == current:
                return []
            current = current.parent
        result = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain=v1"],
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        return []
    if result.returncode != 0:
        return []
    paths: list[str] = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        raw = line[3:] if len(line) > 3 else ""
        if " -> " in raw:
            raw = raw.split(" -> ", 1)[1]
        if raw:
            paths.append(raw)
    return paths


def first_part(path: str) -> str:
    return Path(path).parts[0] if Path(path).parts else path


def is_owner_path(path: str, owners: set[str]) -> bool:
    return path in owners or any(path.startswith(owner.rstrip("/") + "/") for owner in owners if owner.endswith("/"))


def classify(paths: list[str]) -> dict[str, bool]:
    owners = {
        "plan": {"_wiki-methodology/_top/_task_plan.md", "wiki-methodology/top/task_plan.md", "_top/_task_plan.md", "top/task_plan.md"},
        "codemap": {"_codemap.md"},
        "registry": {"_meta/_registry.yml"},
        "data": {"_meta/_data_registry.yml"},
        "tests": {"_wiki-methodology/_tests/", "wiki-methodology/tests/", "_tests/", "tests/"},
        "lifecycle": {"_meta/_naming.md", "_legacy/", "_tmp/", "_sandbox/", "_outputs/", "_figures/", "_refs/"},
    }
    flags = {
        "changed_code": False,
        "changed_data": False,
        "changed_tests": False,
        "changed_lifecycle": False,
        "changed_ssdo_sensitive": False,
        "owner_plan": False,
        "owner_codemap": False,
        "owner_registry": False,
        "owner_data": False,
        "owner_tests": False,
        "owner_lifecycle": False,
    }
    for path in paths:
        part = first_part(path)
        suffix = Path(path).suffix
        if SSDO_PATH_RE.search(path):
            flags["changed_ssdo_sensitive"] = True
        for key, owner_paths in owners.items():
            if is_owner_path(path, owner_paths):
                flags[f"owner_{key}"] = True
        if part in LIFECYCLE_DIRS:
            flags["changed_lifecycle"] = True
            continue
        if part in TEST_DIRS or "/tests/" in path or path.startswith("_wiki-methodology/_tests/"):
            flags["changed_tests"] = True
            continue
        if part in DATA_DIRS or suffix in DATA_SUFFIXES:
            flags["changed_data"] = True
            continue
        if part in CODE_DIRS or suffix in CODE_SUFFIXES:
            # `.claude/` is the Claude Code governance layer (hooks/rules/settings/
            # commands/agents), `*wiki-methodology/` is the six-fold knowledge root,
            # and `_pipelines/` holds TOP pipeline declarations (validated by
            # `topic-doctor --links`, not the codemap/registry) — none is mainline
            # code, so editing them must not demand a codemap/registry closeout.
            # Only mainline code does.
            # `.claude/` exemption is narrowed to known governance subpaths only:
            # `.claude/skills/<x>/scripts/*.py` is real executable code some projects
            # ship, and a blanket `.claude/` carve-out would silently exempt it from
            # the codemap/registry closeout (self-review A-F5).
            # (Only paths with a CODE suffix/dir reach here, so .md/.json under
            # .claude/ never need exempting — the prefixes below cover hook/rule
            # scripts; .claude/skills code stays subject to the check.)
            is_claude_governance = path.startswith(
                (".claude/hooks/", ".claude/rules/", ".claude/commands/", ".claude/agents/")
            )
            if (
                not is_owner_path(path, owners["codemap"])
                and not is_owner_path(path, owners["registry"])
                and not path.startswith("_wiki-methodology/")
                and not path.startswith("wiki-methodology/")
                and not path.startswith("_pipelines/")
                and not is_claude_governance
            ):
                flags["changed_code"] = True
    return flags


def has_ssdo_context(root: Path) -> bool:
    candidates = [
        root / "_wiki-methodology" / "_tests" / "_ssdo_protocol.md",
        root / "wiki-methodology" / "tests" / "_ssdo_protocol.md",
        root / "logs",
        root / "_logs",
        root / "traces",
        root / "_traces",
        root / "reports",
        root / "_reports",
        root / "playwright-report",
        root / "_outputs" / "traces",
        root / "_outputs" / "reports",
        root / "_outputs" / "logs",
    ]
    if any(path.exists() for path in candidates):
        return True
    registry = root / "_meta" / "_registry.yml"
    if registry.is_file():
        text = registry.read_text(encoding="utf-8", errors="ignore")
        return bool(SSDO_PATH_RE.search(text))
    return False


def lint(root: Path) -> tuple[list[str], list[Issue]]:
    paths = git_status(root)
    _, plan, _ = top_paths(root)
    has_topic_truth = bool(
        plan
        or (root / "_codemap.md").is_file()
        or (root / "_meta" / "_registry.yml").is_file()
        or (root / "_meta" / "_data_registry.yml").is_file()
        or (root / "_wiki-methodology").is_dir()
        or (root / "wiki-methodology").is_dir()
    )
    if not has_topic_truth:
        return paths, []
    flags = classify(paths)
    issues: list[Issue] = []
    if flags["changed_code"]:
        if not flags["owner_codemap"]:
            issues.append(Issue("block", "CLOSEOUT_CODEMAP_MISSING", "_codemap.md", "code changed but codemap was not updated"))
        if not flags["owner_registry"]:
            issues.append(Issue("block", "CLOSEOUT_REGISTRY_MISSING", "_meta/_registry.yml", "code changed but registry was not updated"))
        if not flags["owner_tests"] and not flags["changed_tests"]:
            issues.append(Issue("warn", "CLOSEOUT_TEST_GATE_MISSING", "_wiki-methodology/_tests or tests", "code changed without test gate/evidence update"))
    if flags["changed_data"] and not flags["owner_data"]:
        issues.append(Issue("block", "CLOSEOUT_DATA_OWNER_MISSING", "_meta/_data_registry.yml", "data asset changed but data registry was not updated"))
    if flags["changed_lifecycle"] and not flags["owner_lifecycle"]:
        issues.append(Issue("warn", "CLOSEOUT_LIFECYCLE_OWNER_MISSING", "_meta/_naming.md or lifecycle tombstone", "lifecycle dirs changed without naming/tombstone evidence"))
    if flags["changed_ssdo_sensitive"] or (flags["changed_code"] and has_ssdo_context(root)):
        issues.append(Issue("warn", "CLOSEOUT_SSDO_EVIDENCE_NEEDED", "_wiki-methodology/_tests", "final report should split Command gate, Live/user journey, and Trace/SSDO audit evidence or state the downgrade"))
    if any(flags[key] for key in ("changed_code", "changed_data", "changed_tests", "changed_lifecycle")) and not flags["owner_plan"]:
        issues.append(Issue("warn", "CLOSEOUT_PLAN_NOT_TOUCHED", "_wiki-methodology/_top/_task_plan.md", "main project work changed; confirm task_plan current state/evidence is still accurate"))
    return paths, issues


def emit_text(root: Path, paths: list[str], issues: list[Issue]) -> None:
    print(f"[topic-closeout] project={root}")
    print(f"changed_paths={len(paths)}")
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
    paths, issues = lint(root)
    if args.format == "tsv":
        for issue in issues:
            print(f"{issue.severity}\t{issue.code}\t{issue.path}\t{issue.message}")
    else:
        emit_text(root, paths, issues)
    return 1 if any(issue.severity == "block" for issue in issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
