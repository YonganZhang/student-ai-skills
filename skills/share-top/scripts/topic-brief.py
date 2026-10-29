#!/usr/bin/env python3
"""Emit a compact six-column Topic brief for agent recall hooks."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import yaml

from top_common import (
    PLAN_HEAD_LIMIT,
    current_phase_from_lines,
    done_criteria_line,
    first_match,
    phase_files_for,
    read_lines,
    read_text,
    rel,
)


ROOT_WHITELIST = {
    "AGENTS.md",
    "CLAUDE.md",
    "README.md",
    ".git",
    ".gitignore",
    ".gitattributes",
    ".obsidian",
    ".claude",
    ".codex",
    ".vscode",
    "wiki-methodology",
}
PLAN_CANDIDATES = [
    ("v4", "_wiki-methodology/_top", "_wiki-methodology/_top/_task_plan.md"),
    ("legacy-compatible", "_wiki-methodology/top", "_wiki-methodology/top/task_plan.md"),
    ("legacy-compatible", "wiki-methodology/top", "wiki-methodology/top/task_plan.md"),
    ("legacy-compatible", "wiki-methodology/top/legacy", "wiki-methodology/top/legacy/task_plan.md"),
    ("mini", "_top", "_top/_task_plan.md"),
    ("mini", "top", "top/task_plan.md"),
    ("legacy-compatible", ".", "TOP.md"),
    ("legacy-compatible", "docs", "docs/task_plan.md"),
    ("legacy-compatible", ".", "task_plan.md"),
]
PROJECT_SIGNAL_FILES = {
    "AGENTS.md",
    "CLAUDE.md",
    "README.md",
    "TOP.md",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "environment.yml",
    "Cargo.toml",
}
PROJECT_SIGNAL_DIRS = {
    ".git",
    "_port",
    "_code",
    "_data",
    "_paper",
    "_figures",
    "_outputs",
    "_wiki-methodology",
    "wiki-methodology",
    "_top",
    "top",
    "src",
    "tests",
    "data",
    "paper",
    "notebooks",
}
WIKI_ENTRY_NAMES = ("INDEX.md", "README.md", "_readme.md", "SKILL.md", "index.md", "_index.md", "_CATALOG.md", "wiki-index.md")
ROOT_CLUTTER_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".svg",
    ".pdf",
    ".py",
    ".ipynb",
    ".csv",
    ".tsv",
    ".xlsx",
    ".parquet",
    ".jsonl",
}
SKIP_TEST_PARTS = {
    "_legacy",
    "legacy",
    "_sandbox",
    "node_modules",
    ".venv",
    "venv",
    ".pytest_cache",
    "__pycache__",
}


def compact(text: str, limit: int = 180) -> str:
    clean = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text).strip()
    clean = re.sub(r"\s+", " ", clean)
    return clean[:limit]


def find_project_root(start: Path) -> Path:
    path = start.resolve()
    signal_root: Path | None = None
    for parent in [path, *path.parents]:
        # Do not let an empty fixture/work directory escape into a broad temp
        # or config ancestor that merely happens to contain README/src files.
        # Nested real projects are still found before this boundary.
        if parent != path and parent.name.lower() in {"tmp", ".tmp", "temp"}:
            break
        if (
            (parent / "_codemap.md").is_file()
            or (parent / "_wiki-methodology").is_dir()
            or (parent / "wiki-methodology").is_dir()
            or any((parent / plan_rel).is_file() for _, _, plan_rel in PLAN_CANDIDATES)
        ):
            return parent
        if signal_root is None and has_project_signals(parent):
            signal_root = parent
    return signal_root or path


def top_paths(root: Path) -> tuple[Path | None, Path | None, str]:
    for kind, top_rel, plan_rel in PLAN_CANDIDATES:
        top = root / top_rel
        plan = root / plan_rel
        if plan.is_file():
            return top, plan, kind
    return None, None, "none"


def legacy_file(root: Path, name: str) -> Path | None:
    candidates = [
        root / "wiki-methodology" / name,
        root / "_wiki-methodology" / name,
        root / "wiki-methodology" / name.replace("_", "-"),
        root / "_wiki-methodology" / name.replace("_", "-"),
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def has_project_signals(root: Path) -> bool:
    if (root / "_codemap.md").is_file():
        return True
    if any((root / name).exists() for name in PROJECT_SIGNAL_FILES):
        return True
    return any((root / name).is_dir() for name in PROJECT_SIGNAL_DIRS)


def suggest_profile(root: Path, plan_kind: str = "none") -> str:
    if plan_kind == "v4":
        return "v4-full"
    if plan_kind == "legacy-compatible":
        return "legacy-compatible"
    if (root / "_port").is_dir():
        return "upstream-wrapper"
    if (root / "package.json").is_file() or (root / "src").is_dir() or (root / "_code").is_dir() or (root / "_meta" / "_registry.yml").is_file():
        return "active-software"
    if any((root / name).is_dir() for name in ("_data", "data", "_paper", "paper", "_figures")):
        return "active-research"
    if plan_kind == "mini":
        return "mini"
    if (root / "README.md").is_file() or (root / "AGENTS.md").is_file() or (root / "CLAUDE.md").is_file():
        return "public-contrib"
    return "unknown"


def capability_flags(root: Path) -> list[str]:
    flags: list[str] = []
    registry = root / "_meta" / "_registry.yml"
    registry_data = load_yaml(registry) if registry.is_file() else {}
    if isinstance(registry_data, dict):
        if registry_key_count(registry_data, "plugin_tools"):
            flags.append("plugins")
        if registry_key_count(registry_data, "scenarios"):
            flags.append("scenarios")
        if registry_key_count(registry_data, "contract_tests"):
            flags.append("contract-tests")
        if registry_key_count(registry_data, "code_domains") or registry_key_count(registry_data, "cross_domain_edges"):
            flags.append("wrapper-registry")
    if (root / "_meta" / "_data_registry.yml").is_file():
        flags.append("data-registry")
    if any((root / path).is_file() for path in ("scripts/test-all.sh", "scripts/run_pytests_ci.sh")):
        flags.append("test-gate-script")
    if (root / "package.json").is_file() or any((root / path).is_dir() for path in ("frontend", "web", "app")):
        flags.append("frontend")
    if any((root / path).is_dir() for path in ("server", "backend", "api")):
        flags.append("backend")
    if any((root / path).exists() for path in ("mcp", "_mcp", "skills", "_skills", "experts", "_experts")):
        flags.append("runtime-mounts")
    if len(flags) >= 4:
        flags.insert(0, "active-complex-software")
    return flags


def load_yaml(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8", errors="ignore")) or {}
    except Exception:
        return {"__unreadable__": True}


def list_len(data: Any, key: str) -> int:
    if isinstance(data, dict) and isinstance(data.get(key), list):
        return len(data[key])
    return 0


def registry_key_count(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        if isinstance(value.get("tools"), list):
            return len(value["tools"])
        return len(value)
    return 0


def registry_summary(root: Path) -> str:
    registry = root / "_meta" / "_registry.yml"
    if not registry.is_file():
        legacy_code = legacy_file(root, "code-index.md")
        if legacy_code:
            return f"legacy_code_index={rel(legacy_code, root)} upgrade_to=_meta/_registry.yml"
        return "registry=missing"
    data = load_yaml(registry)
    if not isinstance(data, dict) or data.get("__unreadable__"):
        return "registry=unreadable"

    parts: list[str] = []
    for key in ("functions", "entries", "entrypoints", "plugin_tools", "scenarios", "contract_tests", "code_domains", "cross_domain_edges"):
        count = registry_key_count(data, key)
        if count:
            parts.append(f"{key}={count}")
    wrapper_count = list_len(data, "pipeline") + list_len(data, "post_processing") + list_len(data, "pre_processing")
    if wrapper_count:
        parts.append(f"pipeline_refs={wrapper_count}")
    if not parts:
        keys = ",".join(list(data)[:4]) or "empty"
        parts.append(f"keys={keys}")
    query = "query=yes" if (root / "_code" / "_query_registry.py").is_file() else "query=no"
    return " ".join(parts + [query])


def data_summary(root: Path) -> str:
    registry = root / "_meta" / "_data_registry.yml"
    if not registry.is_file():
        return "data_registry=missing"
    data = load_yaml(registry)
    if not isinstance(data, dict) or data.get("__unreadable__"):
        return "data_registry=unreadable"
    count = list_len(data, "assets") + list_len(data, "datasets")
    missing = 0
    entries = []
    for key in ("assets", "datasets"):
        value = data.get(key)
        if isinstance(value, list):
            entries.extend(item for item in value if isinstance(item, dict))
    for item in entries:
        path_value = item.get("path") or item.get("local_path")
        if isinstance(path_value, str) and path_value and not path_value.startswith(("http://", "https://", "s3://")):
            if not (root / path_value).exists() and not (registry.parent / path_value).exists():
                missing += 1
    return f"assets={count} missing_paths={missing}"


def wiki_summary(root: Path) -> str:
    candidates = [
        (root / "_wiki-methodology" / "_wiki", root / "_wiki-methodology"),
        (root / "wiki-methodology" / "wiki", root / "wiki-methodology"),
    ]
    for wiki, container in candidates:
        if wiki.is_dir():
            md_count = len([p for p in wiki.rglob("*.md") if "_legacy" not in p.parts])
            entry_bits = []
            for name in WIKI_ENTRY_NAMES:
                if (container / name).is_file() or (wiki / name).is_file():
                    entry_bits.append(name)
            entry = "+".join(entry_bits) if entry_bits else "no_index"
            return f"{rel(wiki, root)} md={md_count} entry={entry}"
    return "wiki=missing"


def tree_summary(root: Path) -> dict | None:
    """Optional knowledge tree; None (no output change at all) unless _meta/_doc_tree.yml exists.
    Cheap: reads the tree config only, never scans docs."""
    try:
        from doctree_model import DEFAULT_OUTPUT, DEFAULT_TREE, GENERATED_PREFIX  # noqa: PLC0415
    except ImportError:  # doctree not installed beside this script: the feature does not exist here
        return None
    cfg = root / DEFAULT_TREE
    if not cfg.is_file():
        return None
    data = load_yaml(cfg)
    if not isinstance(data, dict) or data.get("__unreadable__"):
        return {"state": "unreadable", "config": DEFAULT_TREE}
    out = data.get("output") if isinstance(data.get("output"), dict) else {}
    entry = str(out.get("tree") or DEFAULT_OUTPUT["tree"])
    page = root / entry
    built = page.is_file() and read_text(page)[: len(GENERATED_PREFIX)] == GENERATED_PREFIX
    nodes = len([n for n in data.get("nodes") or [] if isinstance(n, dict)])
    return {"state": "on", "config": DEFAULT_TREE, "entry": entry, "nodes": nodes, "built": built}


def tree_line(tree: dict) -> str:
    if tree["state"] != "on":
        return f"{tree['state']} config={tree['config']}"
    return f"on nodes={tree['nodes']} entry={tree['entry']} built={'yes' if tree['built'] else 'no (run doctree build)'}"


def test_summary(root: Path) -> str:
    candidates = [
        root / "_wiki-methodology" / "_tests",
        root / "wiki-methodology" / "tests",
        root / "_tests",
        root / "tests",
    ]
    existing = [path for path in candidates if path.is_dir()]
    if not existing:
        return "tests=missing"
    docs = []
    for path in existing:
        if (path / "README.md").is_file() or (path / "_coverage.md").is_file() or (path.parent / "tests-index.md").is_file():
            docs.append(rel(path, root))
    test_files = 0
    for path in (root / "tests", root / "_tests"):
        if not path.is_dir():
            continue
        for file in path.rglob("*"):
            if not file.is_file() or file.suffix not in {".py", ".js", ".ts", ".mjs", ".cjs"}:
                continue
            if any(part in SKIP_TEST_PARTS for part in file.parts):
                continue
            test_files += 1
    runner = "runner=yes" if any((root / script).is_file() for script in ("scripts/test-all.sh", "scripts/run_pytests_ci.sh")) else "runner=no"
    # gates manifest(COL3 机器外壳): 声明的可跑 gate 数; 无 manifest → none
    gates = "none"
    gates_file = root / "_wiki-methodology" / "_tests" / "_gates.yml"
    if gates_file.is_file():
        try:
            import yaml as _yaml
            data = _yaml.safe_load(gates_file.read_text(encoding="utf-8")) or {}
            gates = str(len([g for g in (data.get("gates") or []) if isinstance(g, dict) and g.get("id")]))
        except Exception:
            gates = "unreadable"
    return f"docs={len(docs)} files={test_files} {runner} gates={gates}"


def root_clutter(root: Path) -> int:
    count = 0
    for item in root.iterdir() if root.is_dir() else []:
        name = item.name
        if name.startswith("_") or name.startswith(".") or name in ROOT_WHITELIST:
            continue
        if item.is_file() and item.suffix.lower() in ROOT_CLUTTER_SUFFIXES:
            count += 1
    return count


def sandbox_drift(root: Path) -> int:
    sandbox = root / "_sandbox"
    index = sandbox / "_index.yml"
    if not sandbox.is_dir() or not index.is_file():
        return 0
    text = read_text(index)
    drift = 0
    for child in sandbox.iterdir():
        if child.is_dir() and child.name != "_template" and child.name not in text:
            drift += 1
    return drift


def fs_summary(root: Path) -> str:
    tmp_count = len([p for p in (root / "_tmp").iterdir()]) if (root / "_tmp").is_dir() else 0
    legacy_missing = 0
    legacy = root / "_legacy"
    if legacy.is_dir():
        for child in legacy.iterdir():
            if child.is_dir() and not (child / "README.md").is_file() and not (child / "TOMBSTONE.md").is_file():
                legacy_missing += 1
    return f"root_clutter={root_clutter(root)} tmp_entries={tmp_count} sandbox_drift={sandbox_drift(root)} legacy_missing_readme={legacy_missing}"


def plan_summary(root: Path) -> str:
    top, plan, kind = top_paths(root)
    if not plan:
        return "plan=missing"
    lines = read_lines(plan)
    phase_id = current_phase_from_lines(lines)
    stamp = compact(first_match(lines[:PLAN_HEAD_LIMIT], r"current|当前|🧭"), 120)
    done = compact(done_criteria_line(read_text(plan)), 120)
    bits = [f"{kind}:{rel(plan, root)}"]
    if phase_id:
        bits.append(f"phase={phase_id}")
        if top and kind == "v4":
            phase_files = phase_files_for(top, phase_id)
            if len(phase_files) == 1:
                bits.append(f"phase_file={rel(phase_files[0], root)}")
    if stamp:
        bits.append(f"stamp={stamp}")
    if done:
        bits.append(f"done={done}")
    return " | ".join(bits)


SIXONE_LATEST = "v4.5"


def detect_sixone_version(root: Path) -> str:
    """特征探测派生架构版本 —— 盘上事实即版本, 不手写版本戳(手写必漂移)。
    返回: none / pre-v4 / v4 / v4.5-partial / v4.5。
    阶梯定义 + 升级清单 + 怎么加新版本 → references/upgrades/README.md
    (加 v5 = 此处加特征探测 + upgrades/ 加一份 delta 清单 + README 阶梯表加一行)。"""
    _, _, kind = top_paths(root)
    if kind == "none":
        return "none"
    if kind != "v4":
        return "pre-v4"
    cb = root / "_codebook"
    has_codebook = cb.is_dir() and any(
        p.suffix == ".md" and not p.name.startswith("_") for p in cb.rglob("*.md")
    )
    has_gates = (root / "_wiki-methodology" / "_tests" / "_gates.yml").is_file()
    if has_codebook and has_gates:
        return "v4.5"
    if has_codebook or has_gates:
        return "v4.5-partial"
    return "v4"


def collect_brief(root: Path) -> dict:
    """30 秒 whole-picture 摘要(给 sixone CLI)。契约: sixone-brief/v1。
    has_project_signals=False → bootstrap_needed(空项目, 防返回困惑空结果)。"""
    if not has_project_signals(root):
        return {"schema_version": "sixone-brief/v1", "tool": "topic-brief",
                "project": str(root), "bootstrap_needed": True}
    _, _, plan_kind = top_paths(root)
    brief = {
        "schema_version": "sixone-brief/v1",
        "tool": "topic-brief",
        "project": str(root),
        "bootstrap_needed": False,
        "sixone_version": detect_sixone_version(root),
        "sixone_latest": SIXONE_LATEST,
        "profile": suggest_profile(root, plan_kind),
        "capabilities": capability_flags(root),
        "plan": plan_summary(root),
        "code": registry_summary(root),
        "tests": test_summary(root),
        "wiki": wiki_summary(root),
        "fs": fs_summary(root),
        "data": data_summary(root),
        "owners": {
            "plan": "_wiki-methodology/_top/_task_plan.md",
            "code": "_codemap.md + _meta/_registry.yml",
            "data": "_meta/_data_registry.yml",
        },
    }
    tree = tree_summary(root)
    if tree is not None:  # opt-in projects only; others keep the exact previous envelope
        brief["tree"] = tree_line(tree)
    return brief


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", nargs="?", default=".")
    parser.add_argument("--json", action="store_true", help="machine-readable summary (sixone-brief/v1)")
    args = parser.parse_args()

    root = find_project_root(Path(args.project))
    if args.json:
        import json
        print(json.dumps(collect_brief(root), ensure_ascii=False, indent=2))
        return 0
    if not has_project_signals(root):
        return 0

    _, _, plan_kind = top_paths(root)
    print("[Topic Brief]")
    print(f"project: {root}")
    print(f"profile: {suggest_profile(root, plan_kind)}")
    caps = capability_flags(root)
    if caps:
        print(f"capabilities: {','.join(caps)}")
    print(f"plan: {plan_summary(root)}")
    print("preflight: this is a SUMMARY, not the source. Before editing/creating code, data, or tests, OPEN the owner files below and reuse/extend what already exists:")
    print("  plan -> _wiki-methodology/_top/_task_plan.md (current state, next action)")
    print("  code -> _codemap.md + _meta/_registry.yml (entrypoints, modules, tool registry)")
    print("  data -> _meta/_data_registry.yml (data assets, paths, provenance)")
    tree = tree_summary(root)
    if tree is not None and tree["state"] == "on":
        print(f"  docs -> {tree['entry']} (knowledge tree: pick a node, open its page, then the doc; "
              "`doctree place <draft.md>` before filing a new doc)")
    print("  if you skip an owner source, state why before the first Edit/Write/Bash mutation.")
    print(f"code: {registry_summary(root)}")
    print(f"tests: {test_summary(root)}")
    print(f"wiki: {wiki_summary(root)}")
    if tree is not None:
        print(f"tree: {tree_line(tree)}")
    print(f"fs: {fs_summary(root)}")
    print(f"data: {data_summary(root)}")
    ver = detect_sixone_version(root)
    if ver == SIXONE_LATEST:
        print(f"standard: 六合一 {ver}(最新)。")
    else:
        print(f"standard: 本项目六合一版本={ver}, 最新={SIXONE_LATEST} → 说\"把六合一升级到最新\"走 share-top references/upgrades/ 阶梯。")
    print("closeout: if this turn changes code/data/tests/assets/structure, update matching TOP owners before final reply and run topic-closeout + topic-doctor; add finding-doctor when findings/reviews changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
