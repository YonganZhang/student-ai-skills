#!/usr/bin/env python3
"""Diagnose Topic responsibility drift and lifecycle gaps."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from top_common import read_text, rel
from topic_brief import (
    WIKI_ENTRY_NAMES,
    capability_flags,
    find_project_root,
    legacy_file,
    load_yaml,
    registry_key_count,
    root_clutter,
    sandbox_drift,
    suggest_profile,
    top_paths,
)


STATE_RE = re.compile(r"(当前(状态|阶段|优先|活跃|问题|队列)|下一步|active (bug|queue|work|phase)|current (state|phase|work|priority))", re.I)
POINTER_RE = re.compile(r"(task_plan|_task_plan|只链接|链接|pointer only|指向任务计划|see _task_plan|see task_plan)", re.I)
NEGATED_STATE_RE = re.compile(
    r"(不是当前|非当前|不作为当前|不是.*当前|not (the )?current|not.*active|only pointer|pointer only|只作?为?指针|只看)",
    re.I,
)
REF_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])"
    r"(?P<type>code|data|test|wiki|decision|finding|pipeline):"
    r"(?P<slug>[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?)"
    # trailing "/" means MIME/URI/path (e.g. `data:image/png`), not a native ref
    r"(?![A-Za-z0-9_/-])"
)
RETIRED_STATUSES = {"deprecated", "archived", "retired", "superseded"}
DERIVED_NAMES = {"_topic_index.yml", "_topic_reverse_refs.yml", "_topic_report.md"}


@dataclass
class Issue:
    severity: str
    code: str
    path: str
    message: str


@dataclass
class ResourceDecl:
    ref: str
    path: Path
    status: str = ""
    superseded_by: str = ""
    retire_reason: str = ""
    module: str = ""  # declaring module/file for code refs; distinct modules sharing a name are not a re-declaration


LIGHT_PROFILE_MISSING_CODES = {
    "REGISTRY_MISSING",
    "DATA_REGISTRY_MISSING",
    "WIKI_MISSING",
    "WIKI_ENTRY_MISSING",
    "TESTS_MISSING",
    "TESTS_BRIEF_MISSING",
}
LIGHT_PROFILES = {"public-contrib", "upstream-wrapper", "mini"}
SSDO_TEXT_RE = re.compile(r"(ssdo|audit[- ]?first|audit reader|trace/ssdo|timeline|report\.json|trace truth|读真实过程)", re.I)
SSDO_SIGNAL_RE = re.compile(r"(trace|timeline|report|status|audit|playwright|e2e|pipeline|service|server|log)", re.I)
SSDO_SIGNAL_SUFFIXES = {".log", ".jsonl"}
SSDO_SIGNAL_NAMES = {"report.json", "status.json", "timeline.jsonl", "trace.jsonl"}
SSDO_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "_legacy", "_tmp", "_sandbox"}


def load_yaml_dict(path: Path) -> dict[str, Any]:
    data = load_yaml(path)
    return data if isinstance(data, dict) else {}


def ref_for(kind: str, value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if ":" in text:
        prefix, slug = text.split(":", 1)
        if prefix in {"code", "data", "test", "wiki", "decision", "finding", "pipeline"} and slug:
            return f"{prefix}:{slug}"
        return None
    return f"{kind}:{text}"


def strip_code_fences(text: str) -> str:
    lines = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            lines.append("")
            continue
        lines.append("" if in_fence else line)
    return "\n".join(lines)


def frontmatter_dict(path: Path) -> dict[str, Any]:
    text = read_text(path)
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    try:
        data = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def add_decl(decls: dict[str, list[ResourceDecl]], kind: str, value: Any, path: Path, meta: dict[str, Any] | None = None) -> None:
    ref = ref_for(kind, value)
    if not ref:
        return
    meta = meta or {}
    decls.setdefault(ref, []).append(
        ResourceDecl(
            ref=ref,
            path=path,
            module=str(meta.get("module") or meta.get("file") or "").strip(),
            status=str(meta.get("status") or "").strip().lower(),
            superseded_by=str(meta.get("superseded_by") or meta.get("successor") or "").strip(),
            retire_reason=str(meta.get("retire_reason") or meta.get("reason") or "").strip(),
        )
    )


def collect_yaml_decls(decls: dict[str, list[ResourceDecl]], path: Path, kind: str, keys: tuple[str, ...]) -> None:
    data = load_yaml_dict(path)
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    add_decl(decls, kind, item.get("id") or item.get("name") or item.get("key"), path, item)
        elif isinstance(value, dict):
            # Container shape: a section dict whose real resources live in an inner
            # `tools`/`entries` list (e.g. `plugin_tools: {source_file: ..., total: 22,
            # tools: [{id: ...}, ...]}`). Mirrors registry_key_count's container
            # detection in topic-brief.py — mint ids from the inner list items and
            # treat every sibling key (source_file/total/cache_protocol/...) as
            # metadata, NOT as resource declarations. Minting sibling keys created
            # phantom refs (code:total, code:source_file) that false-fired
            # REF_DUPLICATE across sections and polluted the REF_DANGLING allowlist.
            inner = next(
                (value[k] for k in ("tools", "entries") if isinstance(value.get(k), list)),
                None,
            )
            if inner is not None:
                for item in inner:
                    if isinstance(item, dict):
                        add_decl(decls, kind, item.get("id") or item.get("name") or item.get("key"), path, item)
                continue
            # Flat id->meta dict (no inner list): each subkey is a resource id.
            for item_key, item_value in value.items():
                # Numeric subkeys are summary counts (e.g. `total: 30`), never ids.
                if isinstance(item_value, (int, float)) and not isinstance(item_value, bool):
                    continue
                meta = item_value if isinstance(item_value, dict) else {}
                add_decl(decls, kind, item_key, path, meta)


def collect_markdown_decls(decls: dict[str, list[ResourceDecl]], directory: Path, root: Path, kind: str) -> None:
    if not directory.is_dir():
        return
    for path in sorted(directory.rglob("*.md")):
        if path.name.lower() in {"readme.md", "index.md", "_template.md", "template.md"}:
            continue
        meta = frontmatter_dict(path)
        stem = path.stem.lstrip("_")
        add_decl(decls, kind, meta.get("id") or stem, path, meta)


def collect_resource_decls(root: Path) -> dict[str, list[ResourceDecl]]:
    decls: dict[str, list[ResourceDecl]] = {}
    registry = root / "_meta" / "_registry.yml"
    if registry.is_file():
        collect_yaml_decls(
            decls,
            registry,
            "code",
            ("entries", "functions", "entrypoints", "plugin_tools", "scenarios", "contract_tests", "code_domains"),
        )
    data_registry = root / "_meta" / "_data_registry.yml"
    if data_registry.is_file():
        collect_yaml_decls(decls, data_registry, "data", ("assets", "datasets"))
    collect_markdown_decls(decls, root / "_wiki-methodology" / "_wiki", root, "wiki")
    collect_markdown_decls(decls, root / "_wiki-methodology" / "_tests", root, "test")
    collect_markdown_decls(decls, root / "_wiki-methodology" / "_top" / "_findings", root, "finding")
    collect_markdown_decls(decls, root / "_wiki-methodology" / "_top" / "_decisions", root, "decision")
    pipelines = root / "_pipelines"
    if pipelines.is_dir():
        for path in sorted(pipelines.glob("*.yml")) + sorted(pipelines.glob("*.yaml")):
            data = load_yaml_dict(path)
            add_decl(decls, "pipeline", data.get("pipeline") or data.get("id") or path.stem.lstrip("_"), path, data)
    return decls


def link_scan_files(root: Path) -> list[Path]:
    files = []
    candidates = [
        root / "_codemap.md",
        root / "_meta" / "_registry.yml",
        root / "_meta" / "_data_registry.yml",
        root / "_wiki-methodology" / "_wiki",
        root / "_wiki-methodology" / "_top",
        root / "_wiki-methodology" / "_tests",
        root / "_pipelines",
    ]
    for candidate in candidates:
        if candidate.is_file():
            files.append(candidate)
        elif candidate.is_dir():
            for suffix in ("*.md", "*.yml", "*.yaml"):
                files.extend(sorted(candidate.rglob(suffix)))
    return [path for path in files if path.name not in DERIVED_NAMES]


CLOSED_ITEM_RE = re.compile(r"^\s*[-*]\s+\[[xX]\]\s")


def is_history_file(path: Path, root: Path) -> bool:
    parts = path.relative_to(root).parts
    return "_logs" in parts or "logs" in parts[-2:-1]


def check_links(root: Path, include_history: bool = True) -> list[Issue]:
    """Typed-ref checks. include_history=False (core doctor) skips `_logs/` and closed `- [x]` items:
    history may cite refs that were valid at the time; only live references must resolve."""
    decls = collect_resource_decls(root)
    issues: list[Issue] = []
    for ref, items in sorted(decls.items()):
        if len(items) > 1:
            locations = ", ".join(rel(item.path, root) for item in items[:3])
            mods = [it.module for it in items]
            if all(mods) and len(set(mods)) == len(mods):
                # 同名散在不同模块 = 各自独立函数(每 pipeline step 都有 main/run)→ info 不阻塞
                # (试点项目反馈: code:main declared 39 times 误 block)
                issues.append(Issue("info", "REF_MULTIMODULE", locations,
                                    f"{ref} declared in {len(items)} distinct modules (not a duplicate)"))
            else:
                issues.append(Issue("block", "REF_DUPLICATE", locations, f"{ref} declared {len(items)} times"))
        for item in items:
            if item.status in RETIRED_STATUSES and not (item.superseded_by or item.retire_reason):
                issues.append(Issue("warn", "REF_RETIRED_WITHOUT_EXIT", rel(item.path, root), f"{ref} status={item.status} needs superseded_by or retire_reason"))
    declared = set(decls)
    for path in link_scan_files(root):
        if not include_history and is_history_file(path, root):
            continue
        text = read_text(path)
        if path.suffix == ".md":
            text = strip_code_fences(text)
        for line_no, line in enumerate(text.splitlines(), start=1):
            if not include_history and CLOSED_ITEM_RE.match(line):
                continue
            for match in REF_RE.finditer(line):
                ref = f"{match.group('type')}:{match.group('slug')}"
                if ref not in declared:
                    issues.append(Issue("block", "REF_DANGLING", f"{rel(path, root)}:{line_no}", f"{ref} is not declared by its owner"))
    if declared and not any(issue.code.startswith("REF_") and issue.severity == "block" for issue in issues):
        issues.append(Issue("info", "REF_SCHEMA", ".", f"declared_refs={len(declared)}"))
    return issues


def recognized_registry(data: dict[str, Any]) -> tuple[str, int]:
    parts = []
    total = 0
    for key in ("functions", "entries", "entrypoints", "plugin_tools", "scenarios", "contract_tests", "code_domains", "cross_domain_edges"):
        count = registry_key_count(data, key)
        if count:
            parts.append(key)
            total += count
    wrapper = 0
    for key in ("pre_processing", "pipeline", "post_processing"):
        value = data.get(key)
        if isinstance(value, list):
            wrapper += len(value)
    if wrapper:
        parts.append("pipeline_refs")
        total += wrapper
    return "+".join(parts), total


def registry_ref_exists(root: Path, registry: Path, ref: str) -> bool:
    candidates = [root / ref, registry.parent / ref]
    if ref.startswith("../"):
        candidates.append((registry.parent / ref).resolve())
    return any(path.exists() for path in candidates)


def check_state_drift(root: Path, top: Path | None) -> list[Issue]:
    candidates = [root / "_codemap.md"]
    if top:
        candidates.extend(
            [
                top / "_roadmap.md",
                top / "_SYSTEM-ARCH.md",
                top / "SYSTEM-ARCH.md",
                top / "_audit-triage.md",
                top / "v2-roadmap.md",
            ]
        )
        candidates.extend(sorted(top.glob("*handoff*.md"))[:5])
    issues: list[Issue] = []
    for path in candidates:
        if not path.is_file():
            continue
        for line_no, line in enumerate(read_text(path).splitlines(), start=1):
            clean = line.strip()
            if not clean or POINTER_RE.search(clean) or NEGATED_STATE_RE.search(clean):
                continue
            if STATE_RE.search(clean):
                issues.append(
                    Issue(
                        "warn",
                        "STATE_DRIFT",
                        f"{rel(path, root)}:{line_no}",
                        "current-state wording outside task_plan; link instead of restating",
                    )
                )
                break
    return issues


def check_registry(root: Path) -> list[Issue]:
    path = root / "_meta" / "_registry.yml"
    if not path.is_file():
        legacy_code = legacy_file(root, "code-index.md")
        if legacy_code:
            return [
                Issue(
                    "warn",
                    "REGISTRY_LEGACY",
                    rel(legacy_code, root),
                    "legacy code index found; upgrade deliberately to _meta/_registry.yml",
                )
            ]
        return [Issue("warn", "REGISTRY_MISSING", "_meta/_registry.yml", "code registry is missing")]
    data = load_yaml_dict(path)
    if data.get("__unreadable__"):
        return [Issue("block", "REGISTRY_UNREADABLE", rel(path, root), "registry YAML is unreadable")]
    schema, total = recognized_registry(data)
    issues: list[Issue] = []
    if not schema:
        issues.append(Issue("warn", "REGISTRY_SCHEMA_UNKNOWN", rel(path, root), "registry has no recognized functions/entries/pipeline schema"))
    else:
        issues.append(Issue("info", "REGISTRY_SCHEMA", rel(path, root), f"{schema} total={total}"))
    for key in ("entries", "functions", "entrypoints", "code_domains"):
        value = data.get(key)
        if not isinstance(value, list):
            continue
        missing = 0
        for item in value:
            if not isinstance(item, dict):
                continue
            ref = item.get("path") or item.get("module")
            if isinstance(ref, str) and ref and not registry_ref_exists(root, path, ref):
                missing += 1
        if missing:
            issues.append(Issue("warn", "REGISTRY_PATH_MISSING", rel(path, root), f"{missing} registered paths do not exist"))
    return issues


def check_data_registry(root: Path) -> list[Issue]:
    path = root / "_meta" / "_data_registry.yml"
    if not path.is_file():
        return [Issue("warn", "DATA_REGISTRY_MISSING", "_meta/_data_registry.yml", "data registry is missing")]
    data = load_yaml_dict(path)
    if data.get("__unreadable__"):
        return [Issue("block", "DATA_REGISTRY_UNREADABLE", rel(path, root), "data registry YAML is unreadable")]
    entries = []
    for key in ("assets", "datasets"):
        value = data.get(key)
        if isinstance(value, list):
            entries.extend(item for item in value if isinstance(item, dict))
    missing = 0
    for item in entries:
        ref = item.get("path") or item.get("local_path")
        if isinstance(ref, str) and ref and not ref.startswith(("http://", "https://", "s3://")):
            if not (root / ref).exists() and not (path.parent / ref).exists():
                missing += 1
    if missing:
        return [Issue("warn", "DATA_PATH_MISSING", rel(path, root), f"{missing} data paths do not exist")]
    return [Issue("info", "DATA_REGISTRY", rel(path, root), f"entries={len(entries)}")]


def check_wiki(root: Path) -> list[Issue]:
    candidates = [
        (root / "_wiki-methodology" / "_wiki", root / "_wiki-methodology"),
        (root / "wiki-methodology" / "wiki", root / "wiki-methodology"),
    ]
    for wiki, container in candidates:
        if not wiki.is_dir():
            continue
        has_entry = any(
            (container / name).is_file() or (wiki / name).is_file()
            for name in WIKI_ENTRY_NAMES
        )
        if not has_entry:
            return [Issue("warn", "WIKI_ENTRY_MISSING", rel(wiki, root), "wiki has no INDEX/README/SKILL/index/wiki-index entry")]
        return [Issue("info", "WIKI_ENTRY", rel(wiki, root), "wiki entry exists")]
    return [Issue("warn", "WIKI_MISSING", "_wiki-methodology/_wiki", "wiki layer is missing")]


def check_tests(root: Path, profile: str = "", caps: list[str] | None = None) -> list[Issue]:
    candidates = [
        root / "_wiki-methodology" / "_tests",
        root / "wiki-methodology" / "tests",
        root / "_tests",
        root / "tests",
    ]
    existing = [path for path in candidates if path.is_dir()]
    if not existing:
        return [Issue("warn", "TESTS_MISSING", "_wiki-methodology/_tests", "tests layer is missing")]
    issues: list[Issue] = []
    has_doc = any(
        (path / "README.md").is_file()
        or (path / "_coverage.md").is_file()
        or (path.parent / "tests-index.md").is_file()
        for path in existing
    )
    if not has_doc:
        issues.append(Issue("warn", "TESTS_BRIEF_MISSING", rel(existing[0], root), "tests layer has no README/_coverage brief"))
    else:
        issues.append(Issue("info", "TESTS_BRIEF", rel(existing[0], root), "tests brief exists"))
    # gates manifest(COL3 机器外壳, 理念"通用外壳每项目自填"): 活跃 profile 没声明 → info,
    # 不 block(新项目冷启动别被治理压死)。test:<id> owner_ref 按这份 manifest 的 gate id 解析。
    active = profile in {"v4-full", "active-software", "active-research"} or "active-complex-software" in (caps or [])
    if active and not (root / "_wiki-methodology" / "_tests" / "_gates.yml").is_file():
        issues.append(Issue("info", "TESTS_GATES_MANIFEST_ABSENT", "_wiki-methodology/_tests/_gates.yml",
                            "no machine-runnable gates manifest; copy from templates/v4-architecture and declare real gates"))
    return issues


def has_ssdo_signal(root: Path) -> bool:
    registry = load_yaml_dict(root / "_meta" / "_registry.yml")
    for key in ("pipeline", "pipelines", "scenarios", "contract_tests", "plugin_tools", "entrypoints", "entries"):
        if registry_key_count(registry, key):
            if key in {"pipeline", "pipelines", "scenarios", "contract_tests", "plugin_tools"}:
                return True
            if SSDO_SIGNAL_RE.search(str(registry.get(key, ""))):
                return True

    for name in ("logs", "_logs", "reports", "_reports", "traces", "_traces", "playwright-report"):
        if (root / name).exists():
            return True
    for directory in (root / "_outputs", root / "outputs", root / "artifacts"):
        if directory.is_dir() and any(child.name.lower() in {"traces", "reports", "logs"} for child in directory.iterdir()):
            return True

    scanned = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in SSDO_SKIP_DIRS]
        for filename in filenames:
            if scanned > 800:
                return False
            scanned += 1
            lowered = filename.lower()
            path = Path(dirpath) / filename
            if lowered in SSDO_SIGNAL_NAMES:
                return True
            if path.suffix.lower() in SSDO_SIGNAL_SUFFIXES and SSDO_SIGNAL_RE.search(str(path.relative_to(root))):
                return True
    return False


def has_ssdo_entry(root: Path) -> bool:
    candidates = [
        root / "_wiki-methodology" / "_tests" / "_ssdo_protocol.md",
        root / "wiki-methodology" / "tests" / "_ssdo_protocol.md",
    ]
    if any(path.is_file() for path in candidates):
        return True

    tests_dirs = [root / "_wiki-methodology" / "_tests", root / "wiki-methodology" / "tests", root / "_tests", root / "tests"]
    for directory in tests_dirs:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md"))[:40]:
            if SSDO_TEXT_RE.search(read_text(path)):
                return True

    return bool(SSDO_TEXT_RE.search(read_text(root / "_meta" / "_registry.yml")))


def check_ssdo(root: Path, profile: str, caps: list[str]) -> list[Issue]:
    if profile in LIGHT_PROFILES or profile in {"legacy-compatible", "archive", "unknown"}:
        return []
    software = profile in {"active-software", "v4-full"} or "active-complex-software" in caps
    if not software or not has_ssdo_signal(root):
        return []
    if has_ssdo_entry(root):
        return [Issue("info", "SSDO_ENTRY", "_wiki-methodology/_tests", "audit-first/SSDO entry exists")]
    severity = "block" if "active-complex-software" in caps else "warn"
    return [
        Issue(
            severity,
            "SSDO_ENTRY_MISSING",
            "_wiki-methodology/_tests/_ssdo_protocol.md",
            "software project has trace/report/log/live signals but no audit-first/SSDO entry",
        )
    ]


def check_fs(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    clutter = root_clutter(root)
    if clutter:
        issues.append(Issue("warn", "ROOT_CLUTTER", ".", f"{clutter} top-level files look like orphan artifacts"))
    drift = sandbox_drift(root)
    if drift:
        issues.append(Issue("warn", "SANDBOX_INDEX_DRIFT", "_sandbox/_index.yml", f"{drift} sandbox dirs are not indexed"))
    legacy = root / "_legacy"
    missing = 0
    if legacy.is_dir():
        for child in legacy.iterdir():
            if child.is_dir() and not (child / "README.md").is_file() and not (child / "TOMBSTONE.md").is_file():
                missing += 1
    if missing:
        issues.append(Issue("warn", "LEGACY_README_MISSING", "_legacy", f"{missing} legacy dirs lack README/TOMBSTONE"))
    return issues


# topic-doctor stays calm about the optional knowledge tree: config structure blocks, the summary
# backlog is info, everything else warns. `doctree check` itself is the strict merge gate.
TREE_BACKLOG = {"SUMMARY_MISSING", "SUMMARY_AUTO", "COVERAGE", "SUMMARY_SOURCES"}


def check_tree(root: Path) -> list[Issue]:
    """Only for projects that opted in with _meta/_doc_tree.yml; otherwise no output at all."""
    try:
        import doctree_check  # noqa: PLC0415 - sibling script, imported only when needed
        import doctree_model  # noqa: PLC0415
        import doctree_scan  # noqa: PLC0415
        import doctree_summaries  # noqa: PLC0415
    except ImportError:
        return []
    tree = root / doctree_model.DEFAULT_TREE
    if not tree.is_file():
        return []
    try:
        cfg = doctree_model.load_config(root, tree)
        entries = doctree_summaries.load_summaries(cfg.summaries_path)
        found = doctree_check.run_check(cfg, entries, doctree_scan.load_docs(cfg, entries))
    except doctree_model.ConfigError as exc:
        return [Issue("block", "TREE_CONFIG_ERROR", doctree_model.DEFAULT_TREE, f"{exc}; run doctree check")]
    except (OSError, doctree_model.MissingDependency) as exc:
        return [Issue("warn", "TREE_UNREADABLE", doctree_model.DEFAULT_TREE, f"{type(exc).__name__}: {exc}; tree not checked")]
    issues = [Issue("block", "TREE_" + i.code, i.where, i.message)
              for i in found if i.severity == "block" and i.code in doctree_check.STRUCTURAL]
    grouped: dict[str, list] = {}
    for i in found:
        if not (i.severity == "block" and i.code in doctree_check.STRUCTURAL):
            grouped.setdefault(i.code, []).append(i)
    for code in sorted(grouped):
        items = grouped[code]
        severity = "info" if code in TREE_BACKLOG else "warn"
        if len(items) == 1:
            issues.append(Issue(severity, "TREE_" + code, items[0].where, items[0].message))
        else:
            sample = ", ".join(i.where for i in items[:3])
            issues.append(Issue(severity, "TREE_" + code, doctree_model.DEFAULT_TREE,
                                f"{len(items)} items, e.g. {sample}; run doctree check -v"))
    return issues


def lint_project(root: Path, include_links: bool = False) -> list[Issue]:
    issues: list[Issue] = []
    top, plan, kind = top_paths(root)
    profile = suggest_profile(root, kind)
    caps = capability_flags(root)
    if not plan:
        issues.append(Issue("info", "PLAN_MISSING", "_wiki-methodology/_top/_task_plan.md", "no task_plan found"))
        issues.append(Issue("info", "PROFILE_SUGGESTED", str(root), profile))
    else:
        if kind == "v4":
            issues.append(Issue("info", "PLAN_FOUND", rel(plan, root), f"kind={kind}"))
        else:
            issues.append(
                Issue(
                    "warn",
                    "PLAN_FOUND_NONSTANDARD",
                    rel(plan, root),
                    f"kind={kind}; v4 current standard is _wiki-methodology/_top/_task_plan.md",
                )
            )
    if (root / "_wiki-methodology").is_dir() and (root / "wiki-methodology").is_dir():
        issues.append(Issue("warn", "LEGACY_V4_MIXED", "wiki-methodology", "legacy and v4 wiki roots both exist"))
    issues.extend(check_state_drift(root, top))
    issues.extend(check_registry(root))
    issues.extend(check_data_registry(root))
    issues.extend(check_wiki(root))
    issues.extend(check_tree(root))
    issues.extend(check_tests(root, profile, caps))
    issues.extend(check_ssdo(root, profile, caps))
    issues.extend(check_fs(root))
    if include_links:
        issues.extend(check_links(root))
    if profile in LIGHT_PROFILES:
        for issue in issues:
            if issue.code in LIGHT_PROFILE_MISSING_CODES and issue.severity == "warn":
                issue.severity = "info"
                issue.message = f"{issue.message}; {profile} does not require full v4 by default"
    return issues


MD_LINK_RE = re.compile(r"\]\(([^)\s#]+)(?:#[^)]*)?\)")
ENTRY_DOCS = ("AGENTS.md", "CLAUDE.md", "_codemap.md")


def check_entry_links(root: Path) -> list[Issue]:
    """Relative markdown links in the entry docs must resolve (dead links mislead the next agent)."""
    issues: list[Issue] = []
    for name in ENTRY_DOCS:
        path = root / name
        if not path.is_file():
            continue
        for line_no, line in enumerate(strip_code_fences(read_text(path)).splitlines(), start=1):
            for match in MD_LINK_RE.finditer(line):
                target = match.group(1)
                if "://" in target or target.startswith(("mailto:", "/", "~")):
                    continue
                if not (path.parent / target).exists():
                    issues.append(Issue("warn", "DEAD_LINK", f"{name}:{line_no}", f"link target missing: {target}"))
    return issues


def check_registry_paths(root: Path) -> list[Issue]:
    """Registries are optional modules: only check that what they register exists."""
    issues: list[Issue] = []
    if (root / "_meta" / "_registry.yml").is_file():
        issues.extend(i for i in check_registry(root) if i.code != "REGISTRY_SCHEMA_UNKNOWN")
    if (root / "_meta" / "_data_registry.yml").is_file():
        issues.extend(check_data_registry(root))
    return issues


def check_plan(root: Path) -> list[Issue]:
    """plan validate + unrecorded work. Lightweight plans (no structured tasks) get no demands."""
    import top_plan  # local import: keeps the full-mode path free of git helpers

    plan_root, path = top_plan._plan_path(str(root))
    if not path.is_file():
        return [Issue("info", "PLAN_MISSING", "_wiki-methodology/_top/_task_plan.md", "no task_plan; lightweight project")]
    state = top_plan.parse_plan(path)
    plan_rel = rel(path, root)
    if state.format == "qa":
        import top_qa  # noqa: PLC0415
        result = top_qa.validate(str(root))
        if not result["errors"] and not top_qa.load(root).questions:
            return [Issue("info", "PLAN_LIGHTWEIGHT", plan_rel, "question-and-answer plan without questions yet")]
        issues = [Issue("warn", "PLAN_INVALID", plan_rel,
                        f"{len(result['errors'])} plan errors, first {result['errors'][0]['code']}: "
                        f"{result['errors'][0]['message']}; run plan check")] if result["errors"] else []
        issues += [Issue("info", w["code"], plan_rel, f"{w['message']} → {w['hint']}") for w in result["warnings"]]
        return issues
    if top_plan.is_lightweight(state):
        return [Issue("info", "PLAN_LIGHTWEIGHT", plan_rel, "no structured tasks; lightweight mode, nothing to maintain")]
    issues: list[Issue] = []
    errors = top_plan.plan_invariant_errors(state)
    if errors:
        code, message = errors[0]
        issues.append(Issue("warn", "PLAN_INVALID", plan_rel,
                            f"{len(errors)} plan errors, first {code}: {message}; run plan validate"))
    for warning in top_plan.budget_warnings(plan_root, path, state):
        issues.append(Issue("warn", warning["code"], plan_rel, f"{warning['message']} → {warning['hint']}"))
    try:
        unrecorded = top_plan._unrecorded(plan_root, path)
    except (OSError, ValueError, subprocess.SubprocessError):
        unrecorded = None
    if unrecorded and unrecorded.get("commits"):
        # 2026-10-16: short or unrelated work does not belong in the plan; this is context, not a demand
        issues.append(Issue("info", "UNRECORDED_COMMITS", plan_rel,
                            f"{unrecorded['commits']} commits without a Task trailer since the plan was last updated "
                            "(only long-running work needs a plan record)"))
    if unrecorded and unrecorded.get("files"):
        issues.append(Issue("info", "UNRECORDED_FILES", plan_rel,
                            f"{unrecorded['files']} changed files newer than the plan, e.g. {', '.join(unrecorded['sample'])}"))
    return issues


def core_checks(root: Path, include_links: bool = False) -> list[Issue]:
    """Default doctor: dead links, registered paths exist, plan validate, unrecorded work."""
    issues = check_plan(root)
    issues.extend(check_entry_links(root))
    issues.extend(check_registry_paths(root))
    issues.extend(check_tree(root))
    if include_links:
        issues.extend(check_links(root, include_history=False))
    return issues


def emit_text(root: Path, issues: list[Issue]) -> None:
    print(f"[topic-doctor] project={root}")
    for issue in issues:
        print(f"{issue.severity.upper()}\t{issue.code}\t{issue.path}\t{issue.message}")
    print(
        "SUMMARY: "
        + " ".join(
            f"{severity}={sum(1 for issue in issues if issue.severity == severity)}"
            for severity in ("block", "warn", "info")
        )
    )


def doctor_verdict(issues: list[Issue]) -> str:
    """doctor 级 verdict: ok|warn|block。
    注: 'stale'(代码变了账本没跟) 是 closeout 概念, 由 CLI 聚合层结合 topic-closeout 补,
    本工具只判自身 issues 的 ok/warn/block。契约: sixone-doctor/v1。"""
    if any(i.severity == "block" for i in issues):
        return "block"
    if any(i.severity == "warn" for i in issues):
        return "warn"
    return "ok"


def emit_json(root: Path, issues: list[Issue]) -> None:
    import json
    envelope = {
        "schema_version": "sixone-doctor/v1",
        "tool": "topic-doctor",
        "project": str(root),
        "verdict": doctor_verdict(issues),  # ok|warn|block
        "summary": {sev: sum(1 for i in issues if i.severity == sev) for sev in ("block", "warn", "info")},
        "issues": [
            {"severity": i.severity, "code": i.code, "path": i.path, "message": i.message}
            for i in issues
        ],
    }
    print(json.dumps(envelope, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", nargs="?", default=".")
    parser.add_argument("--format", choices=["text", "tsv", "json"], default="text")
    parser.add_argument("--json", action="store_const", const="json", dest="format",
                        help="machine-readable envelope (sixone-doctor/v1); = --format json")
    parser.add_argument("--links", action="store_true", help="also validate Topic resource refs declared by owner files")
    parser.add_argument("--core", action="store_true",
                        help="focused doctor used by `sixone-cli.py doctor`: dead links, registered paths, "
                             "plan validate, unrecorded work (default here stays the legacy full check)")
    args = parser.parse_args()

    root = find_project_root(Path(args.project))
    issues = core_checks(root, include_links=args.links) if args.core else lint_project(root, include_links=args.links)
    if args.format == "json":
        emit_json(root, issues)
    elif args.format == "tsv":
        for issue in issues:
            print(f"{issue.severity}\t{issue.code}\t{issue.path}\t{issue.message}")
    else:
        emit_text(root, issues)
    return 1 if any(issue.severity == "block" for issue in issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
