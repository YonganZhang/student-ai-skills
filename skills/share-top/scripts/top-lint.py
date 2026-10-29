#!/usr/bin/env python3
"""Lint v4 TOP planning state.

Read-only. Reports block/warn/info issues; exits 1 when block issues exist.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

from top_common import (
    PHASE_ID_RE,
    current_phase_from_text,
    current_stamp_token_from_text,
    done_criteria_line,
    frontmatter_value,
    has_heading,
    migration_context,
    parse_plan,
    plan_invariant_errors,
    phase_file_groups,
    phase_files_for,
    project_root,
    read_text,
    rel,
)


PLACEHOLDER_RE = re.compile(r"<[^>]+>|TBD|todo|待补|可验证条件", re.I)
LEGACY_PATH_RE = re.compile(r"(?<![_A-Za-z0-9-])wiki-methodology/(?:top|wiki|tests|fs)/|(?<![_A-Za-z0-9-])top/(?:findings|logs|phases)/")
SKIP_MARKDOWN = {"_template.md", "_readme.md", "README.md"}
# finding 形状规则的固定大赦线(规则生效日): 此前的 finding 是史料 → 形状问题降 info。
FINDING_SHAPE_ENFORCED_SINCE = "2026-06-10"


@dataclass
class Issue:
    severity: str
    code: str
    path: str
    message: str


def lint_project(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    top = root / "_wiki-methodology" / "_top"
    plan = top / "_task_plan.md"

    if not top.is_dir():
        return [Issue("info", "TOP_NOT_ENABLED", "_wiki-methodology/_top", "v4 TOP directory is not enabled")]
    if not plan.is_file():
        issues.append(Issue("block", "PLAN_MISSING", rel(plan, root), "_task_plan.md is missing"))
        return issues

    plan_text = read_text(plan)
    plan_state = parse_plan(plan)
    for code, message in plan_invariant_errors(plan_state):
        severity = "warn" if code == "PLAN_ACTIVE_WORK_MISSING" else "block"
        issues.append(Issue(severity, code, rel(plan, root), message))
    phase_id = current_phase_from_text(plan_text)
    stamp_token = current_stamp_token_from_text(plan_text)
    if not phase_id:
        if stamp_token:
            issues.append(Issue("info", "NON_PHASE_STAMP", rel(plan, root), f"current stamp is not a P-phase id: [{stamp_token}]"))
        else:
            issues.append(Issue("block", "STAMP_MISSING", rel(plan, root), "head stamp lacks a current phase id"))

    done = done_criteria_line(plan_text)
    if not done:
        issues.append(Issue("block", "DONE_CRITERIA_MISSING", rel(plan, root), "Done Criteria is missing"))
    elif PLACEHOLDER_RE.search(done) or len(re.split("[:：]", done, maxsplit=1)[-1].strip()) < 8:
        issues.append(Issue("warn", "DONE_CRITERIA_WEAK", rel(plan, root), "Done Criteria looks empty or unverifiable"))

    duplicate_top_phases = set()
    phase_groups = phase_file_groups(top)
    phase_files_all = [path for files in phase_groups.values() for path in files]
    for top_phase, files in phase_groups.items():
        if len(files) > 1:
            duplicate_top_phases.add(top_phase)
            paths = ", ".join(rel(path, root) for path in files)
            issues.append(Issue("block", "PHASE_DUPLICATE", rel(top / "_phases", root), f"multiple top-level phase files for {top_phase}: {paths}"))

    yaml_groups: dict[str, list[Path]] = {}
    for phase_file in phase_files_all:
        filename_phase = phase_file.name.split("_", 1)[0]
        yaml_phase = frontmatter_value(read_text(phase_file), "phase_id")
        if not yaml_phase:
            issues.append(Issue("warn", "PHASE_ID_YAML", rel(phase_file, root), f"YAML phase_id should be {filename_phase}"))
            continue
        if not PHASE_ID_RE.fullmatch(yaml_phase):
            issues.append(Issue("warn", "PHASE_ID_YAML", rel(phase_file, root), f"YAML phase_id is invalid: {yaml_phase}"))
            continue
        yaml_top_phase = yaml_phase.split(".", 1)[0]
        yaml_groups.setdefault(yaml_top_phase, []).append(phase_file)
        if yaml_top_phase != filename_phase:
            issues.append(Issue("warn", "PHASE_ID_YAML", rel(phase_file, root), f"YAML phase_id should be {filename_phase}"))

    for top_phase, files in yaml_groups.items():
        filename_files = set(phase_groups.get(top_phase, []))
        yaml_files = set(files)
        if len(files) > 1 and yaml_files != filename_files:
            duplicate_top_phases.add(top_phase)
            paths = ", ".join(rel(path, root) for path in files)
            issues.append(Issue("block", "PHASE_DUPLICATE_YAML", rel(top / "_phases", root), f"multiple phase files claim {top_phase}: {paths}"))

    if phase_id:
        phase_files = phase_files_for(top, phase_id)
        top_phase = phase_id.split(".", 1)[0]
        if top_phase in duplicate_top_phases:
            pass
        elif not phase_files:
            issues.append(Issue("warn", "PHASE_FILE_MISSING", rel(top / "_phases", root), f"no phase file for {phase_id}; stamp remains the state truth"))

    for finding in sorted((top / "_findings").glob("*.md")) if (top / "_findings").is_dir() else []:
        if finding.name in SKIP_MARKDOWN:
            continue
        text = read_text(finding)
        # 固定大赦线: lint 的目的是塑形"新" finding;形状规则生效日之前的是史料,
        # 追溯执法 = 永久 warn 噪声没人会修(淹真信号)。降 info 仍可见。
        # 用固定日期而非滚动窗口 —— 滚动窗口会让新建的不合规 finding "熬过 N 天"自动洗白。
        # 文件名无日期 → 维持 warn(新文件该带日期, 这本身就是命名规范)。
        shape_severity = "warn"
        date_match = re.search(r"_?(\d{4}-\d{2}-\d{2})", finding.name)
        if date_match and date_match.group(1) < FINDING_SHAPE_ENFORCED_SINCE:
            shape_severity = "info"
        finding_phase_id = frontmatter_value(text, "phase_id")
        if not finding_phase_id:
            issues.append(Issue(shape_severity, "FINDING_PHASE_ID", rel(finding, root), "finding lacks phase_id YAML"))
        elif not PHASE_ID_RE.fullmatch(finding_phase_id):
            issues.append(Issue(shape_severity, "FINDING_PHASE_ID", rel(finding, root), f"finding phase_id is invalid: {finding_phase_id}"))
        section_groups = {
            "Local Case": ("Local Case", "局部案例", "局部点"),
            "Class Pattern": ("Class Pattern", "类层模式", "类层问题"),
        }
        for canonical, headings in section_groups.items():
            if not has_heading(text, headings):
                issues.append(Issue(shape_severity, "FINDING_SHAPE", rel(finding, root), f"finding lacks {canonical}"))
        if not has_heading(text, ("Prevention Rule (candidate)", "Prevention Rule", "候选防范规则")):
            issues.append(Issue("info", "FINDING_NO_PREVENTION", rel(finding, root), "finding has no candidate prevention rule"))

    for log in sorted((top / "_logs").glob("*.md")) if (top / "_logs").is_dir() else []:
        if log.name in SKIP_MARKDOWN:
            continue
        text = read_text(log)
        log_phase_id = frontmatter_value(text, "phase_id")
        if log.name.endswith("-plan.md"):
            pass  # machine-appended plan event log (sixone-cli plan complete/block/...), one line per event
        elif not log_phase_id:
            issues.append(Issue("warn", "LOG_PHASE_ID", rel(log, root), "log lacks phase_id YAML"))
        elif not PHASE_ID_RE.fullmatch(log_phase_id):
            issues.append(Issue("warn", "LOG_PHASE_ID", rel(log, root), f"log phase_id is invalid: {log_phase_id}"))
        if re.search(r"(?m)^##\s*(Class Pattern|Prevention Rule|Conclusion|Decision|Finding|结论|决策)\b", text, re.I):
            issues.append(Issue("warn", "LOG_POLLUTION", rel(log, root), "log appears to contain finding/decision content"))

    for review in sorted((top / "_external_reviews").glob("*.md")) if (top / "_external_reviews").is_dir() else []:
        if review.name in SKIP_MARKDOWN:
            continue
        text = read_text(review)
        review_phase_id = frontmatter_value(text, "phase_id")
        if not review_phase_id:
            issues.append(Issue("warn", "REVIEW_PHASE_ID", rel(review, root), "external review lacks phase_id YAML"))
        elif not PHASE_ID_RE.fullmatch(review_phase_id):
            issues.append(Issue("warn", "REVIEW_PHASE_ID", rel(review, root), f"external review phase_id is invalid: {review_phase_id}"))

    for decision in sorted((top / "_decisions").glob("*.md")) if (top / "_decisions").is_dir() else []:
        if decision.name in SKIP_MARKDOWN:
            continue
        text = read_text(decision)
        decision_phase_id = frontmatter_value(text, "phase_id")
        if not decision_phase_id:
            issues.append(Issue("warn", "DECISION_PHASE_ID", rel(decision, root), "decision lacks phase_id YAML"))
        elif not PHASE_ID_RE.fullmatch(decision_phase_id):
            issues.append(Issue("warn", "DECISION_PHASE_ID", rel(decision, root), f"decision phase_id is invalid: {decision_phase_id}"))
        if not has_heading(text, ("Decision", "决策")):
            issues.append(Issue("warn", "DECISION_SHAPE", rel(decision, root), "decision lacks Decision section"))
        if not has_heading(text, ("Rationale", "理由")):
            issues.append(Issue("warn", "DECISION_SHAPE", rel(decision, root), "decision lacks Rationale section"))

    scan_roots = [
        root / "_wiki-methodology",
        root / "_meta",
        root / "_codemap.md",
        root / "AGENTS.md",
        root / "CLAUDE.md",
    ]
    for base in scan_roots:
        files = [base] if base.is_file() else list(base.rglob("*.md")) if base.is_dir() else []
        for file in files:
            if migration_context(file):
                continue
            text = read_text(file)
            if LEGACY_PATH_RE.search(text):
                issues.append(Issue("warn", "LEGACY_PATH_DRIFT", rel(file, root), "legacy TOP path appears outside migration context"))

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", nargs="?", default=".", help="project root")
    parser.add_argument("--format", choices=["text", "tsv"], default="text")
    args = parser.parse_args()

    root = project_root(Path(args.project))
    issues = lint_project(root)
    block_count = sum(1 for issue in issues if issue.severity == "block")

    if args.format == "tsv":
        for issue in issues:
            print(f"{issue.severity}\t{issue.code}\t{issue.path}\t{issue.message}")
    else:
        print(f"[top-lint] project={root}")
        if not issues:
            print("[top-lint] OK")
        for issue in issues:
            print(f"{issue.severity.upper()}\t{issue.code}\t{issue.path}\t{issue.message}")
        print(f"SUMMARY: block={block_count} warn={sum(1 for i in issues if i.severity == 'warn')} info={sum(1 for i in issues if i.severity == 'info')}")

    return 1 if block_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
