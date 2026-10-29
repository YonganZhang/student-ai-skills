"""doctree check: structure blocks, content drift warns. Shared by `doctree check`, build and topic-doctor."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from doctree_model import Config, as_list, content_sha, match_any
from doctree_summaries import Entry
from doctree_scan import Doc
from doctree_render import children, is_managed, plan_writes, render_all

# Config structure: navigation itself is broken. Blocks everywhere (doctree check, build, topic-doctor).
STRUCTURAL = ("DUP_ID", "ROOT_MISSING", "PARENT_MISSING", "PARENT_CYCLE", "EXTRA_ROOT", "TOPIC_INVALID")
# Block the `doctree check` merge gate, but only warn in the general topic-doctor.
GATE_BLOCK = ("STALE", "DEAD_LINK", "ENTRY_DEAD", "ENTRY_INVALID", "OUTPUT_UNMANAGED")
CODES = {
    "DUP_ID": "node id defined more than once",
    "ROOT_MISSING": "`root` is not a node",
    "PARENT_MISSING": "parent is not a node",
    "PARENT_CYCLE": "parent chain loops",
    "EXTRA_ROOT": "node without parent that is not the root",
    "TOPIC_INVALID": "entry or mount names a topic that is not a node",
    "STALE": "a generated file is missing or differs from a fresh render (run doctree build)",
    "DEAD_LINK": "link in a generated page, or a path-like superseded_by, does not resolve",
    "ENTRY_DEAD": "summaries entry names a file that does not exist (renamed or deleted doc)",
    "ENTRY_INVALID": "summaries entry is malformed (bad key, topics or source)",
    "OUTPUT_UNMANAGED": "a configured output path holds a hand-written file; build will not overwrite it",
    "ORPHAN": "doc inside `coverage` is not on the tree",
    "SUMMARY_MISSING": "in-scope doc has no summaries entry, or the entry has no summary",
    "SUMMARY_STALE": "doc changed since its summary was reviewed (or no reviewed_sha); review, then stamp",
    "SUMMARY_AUTO": "summary is an unreviewed draft (source: auto); pages mark it",
    "ENTRY_OUT_OF_SCOPE": "summaries entry for a file the scan excludes; it will not appear",
    "MOUNT_EMPTY": "mount rule matches no in-scope doc",
    "NODE_EMPTY": "leaf node has no primary docs",
    "UNMANAGED_IN_OUTPUT": "hand-written file inside node_dir; kept, never deleted",
    "CONFIG_UNKNOWN_KEY": "unknown config key (use x-… for project extensions)",
    "COVERAGE": "counts: in scope, on tree, coverage, orphans",
    "SUMMARY_SOURCES": "counts by summary source",
}
PATHLIKE = re.compile(r"^[\w./-]+\.md$")
LINK_RE = re.compile(r"\]\(([^)#]+\.md)\)")


@dataclass
class Issue:
    severity: str  # block | warn | info
    code: str
    where: str
    message: str

    def as_dict(self) -> dict:
        return asdict(self)


def structure_issues(cfg: Config) -> list[Issue]:
    name = cfg.rel(cfg.tree_path)
    issues = [Issue("block", "DUP_ID", name, f"node id `{n}` defined more than once") for n in cfg.dup_ids]
    if cfg.root_id not in cfg.nodes:
        issues.append(Issue("block", "ROOT_MISSING", name, f"root `{cfg.root_id}` is not a node"))
    for nid, n in cfg.nodes.items():
        if n.parent and n.parent not in cfg.nodes:
            issues.append(Issue("block", "PARENT_MISSING", nid, f"parent `{n.parent}` is not a node"))
        seen, cur = set(), nid
        while cur and cur in cfg.nodes:
            if cur in seen:
                issues.append(Issue("block", "PARENT_CYCLE", nid, "parent chain loops"))
                break
            seen.add(cur)
            cur = cfg.nodes[cur].parent
        if n.parent is None and nid != cfg.root_id:
            issues.append(Issue("block", "EXTRA_ROOT", nid, "node has no parent but is not the root"))
    for key in cfg.unknown_keys:
        issues.append(Issue("warn", "CONFIG_UNKNOWN_KEY", name, f"unknown key `{key}` (ignored)"))
    return issues


def renderable(issues: list[Issue]) -> bool:
    return not any(i.severity == "block" and i.code in STRUCTURAL for i in issues)


def entry_issues(cfg: Config, entries: dict[str, Entry], in_scope: set[str]) -> list[Issue]:
    issues: list[Issue] = []
    for rel in sorted(entries):
        e = entries[rel]
        for problem in e.problems:
            issues.append(Issue("block", "ENTRY_INVALID", rel, problem))
        if e.problems:
            continue
        for t in e.topics:
            if t not in cfg.nodes:
                issues.append(Issue("block", "TOPIC_INVALID", rel, f"topic `{t}` is not a node"))
        path = cfg.root / rel
        if not path.is_file():
            issues.append(Issue("block", "ENTRY_DEAD", rel, "file does not exist; update or remove the entry in the same commit"))
            continue
        if rel not in in_scope:
            issues.append(Issue("warn", "ENTRY_OUT_OF_SCOPE", rel, "the scan excludes this file; the entry has no effect"))
            continue
        if not e.summary:
            continue  # reported per doc as SUMMARY_MISSING
        if e.source == "auto":
            issues.append(Issue("warn", "SUMMARY_AUTO", rel, "unreviewed draft; review it, then `doctree summaries stamp`"))
        elif not e.reviewed_sha:
            issues.append(Issue("warn", "SUMMARY_STALE", rel, "reviewed entry has no reviewed_sha; run `doctree summaries stamp`"))
        elif content_sha(path) != e.reviewed_sha:
            issues.append(Issue("warn", "SUMMARY_STALE", rel, "doc changed since the summary was reviewed; check it, then stamp"))
    return issues


def doc_issues(cfg: Config, docs: list[Doc], entries: dict[str, Entry]) -> list[Issue]:
    issues: list[Issue] = []
    for d in docs:
        if d.topic_src == "mount":
            for t in d.topics:
                if t not in cfg.nodes:
                    issues.append(Issue("block", "TOPIC_INVALID", d.path, f"mount topic `{t}` is not a node"))
        target_ok = (cfg.root / d.superseded_by).exists() or (cfg.root / d.path).parent.joinpath(d.superseded_by).exists()
        if PATHLIKE.match(d.superseded_by) and not target_ok:
            issues.append(Issue("block", "DEAD_LINK", d.path, f"superseded_by `{d.superseded_by}` does not exist"))
        e = entries.get(d.path)
        if e is None or not e.summary:
            shown = "an auto excerpt" if d.summary else "（缺摘要）"
            what = "entry has no summary" if e is not None else "no entry in the summaries table"
            issues.append(Issue("warn", "SUMMARY_MISSING", d.path, f"{what}; pages show {shown}"))
    for m in cfg.mounts:
        globs = as_list(m.get("glob"))
        if not any(match_any(d.path, globs) for d in docs):
            issues.append(Issue("warn", "MOUNT_EMPTY", ",".join(globs), "mount rule matches no in-scope doc"))
    attached = {d.path for d in docs if d.topics}
    for d in docs:
        if match_any(d.path, cfg.coverage) and d.path not in attached:
            issues.append(Issue("warn", "ORPHAN", d.path, "inside coverage but not on the tree"))
    primary = {d.topics[0] for d in docs if d.topics}
    for nid in cfg.order:
        if nid != cfg.root_id and not children(cfg, nid) and nid not in primary:
            issues.append(Issue("warn", "NODE_EMPTY", nid, "leaf node has no primary docs"))
    return issues


def output_issues(cfg: Config, docs: list[Doc]) -> list[Issue]:
    files = render_all(cfg, docs)
    wp = plan_writes(cfg, files)
    issues: list[Issue] = []
    for p in wp.unmanaged_targets:
        issues.append(Issue("block", "OUTPUT_UNMANAGED", cfg.rel(p), "hand-written file at a generated path; move it or change output"))
    for p in wp.write:
        what = "missing" if not p.exists() else "differs from sources"
        issues.append(Issue("block", "STALE", cfg.rel(p), f"generated file {what}; run doctree build"))
    for p in wp.delete:
        issues.append(Issue("block", "STALE", cfg.rel(p), "generated page for a node that no longer exists; run doctree build"))
    for p in wp.unmanaged_extra:
        issues.append(Issue("warn", "UNMANAGED_IN_OUTPUT", cfg.rel(p), "hand-written file in the generated pages directory"))
    for p in sorted(files):
        if p.is_file() and is_managed(p):
            for target in LINK_RE.findall(p.read_text(encoding="utf-8")):
                if not (p.parent / target).resolve().exists():
                    issues.append(Issue("block", "DEAD_LINK", cfg.rel(p), f"link to missing `{target}`"))
    return issues


def run_check(cfg: Config, entries: dict[str, Entry], docs: list[Doc]) -> list[Issue]:
    issues = structure_issues(cfg)
    in_scope = {d.path for d in docs}
    issues += entry_issues(cfg, entries, in_scope)
    issues += doc_issues(cfg, docs, entries)
    if renderable(issues):
        issues += output_issues(cfg, docs)
    attached = [d for d in docs if d.topics]
    cov = [d for d in docs if match_any(d.path, cfg.coverage)]
    orphans = sum(1 for i in issues if i.code == "ORPHAN")
    src: dict[str, int] = {}
    for d in docs:
        src[d.summary_src] = src.get(d.summary_src, 0) + 1
    issues.append(Issue("info", "COVERAGE", ".", f"in_scope={len(docs)} on_tree={len(attached)} coverage_docs={len(cov)} orphans={orphans}"))
    issues.append(Issue("info", "SUMMARY_SOURCES", ".", " ".join(f"{k}={v}" for k, v in sorted(src.items()))))
    order = {"block": 0, "warn": 1, "info": 2}
    return sorted(issues, key=lambda i: (order[i.severity], i.code, i.where, i.message))


def verdict(issues: list[Issue]) -> str:
    if any(i.severity == "block" for i in issues):
        return "block"
    return "warn" if any(i.severity == "warn" for i in issues) else "ok"

