"""doctree render: the generated pages and the one output manifest shared by build and check.

Every generated page starts with GENERATED_PREFIX; that line is how build/check tell managed pages
from hand-written ones. Output is byte-deterministic: fixed ordering, no timestamps, relative links.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from doctree_model import GENERATED_PREFIX, Config
from doctree_scan import Doc

DISPLAY_SUMMARY = 140
AUTO_MARK = "〔自动摘录，未审〕"


def marker(cfg: Config) -> str:
    return (f"{GENERATED_PREFIX} — 派生文件，由 doctree build 生成，不要手改；"
            f"节点改 {cfg.rel(cfg.tree_path)}，归属与摘要改 {cfg.rel(cfg.summaries_path)} -->")


def is_managed(path: Path) -> bool:
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            return fh.readline().startswith(GENERATED_PREFIX)
    except OSError:
        return False


def relink(cfg: Config, from_file: Path, target: str | Path) -> str:
    absolute = target if isinstance(target, Path) else cfg.root / target
    return Path(os.path.relpath(absolute, from_file.parent)).as_posix()


def short(s: str, n: int = DISPLAY_SUMMARY) -> str:
    s = s.replace("|", "／")
    return s if len(s) <= n else s[: n - 1] + "…"


def ancestry(cfg: Config, nid: str) -> list[str]:
    chain, seen = [], set()
    cur: str | None = nid
    while cur and cur in cfg.nodes and cur not in seen:
        seen.add(cur)
        chain.append(cur)
        cur = cfg.nodes[cur].parent
    return list(reversed(chain))


def children(cfg: Config, nid: str) -> list[str]:
    return [n for n in cfg.order if cfg.nodes[n].parent == nid]


def depth_first(cfg: Config) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []

    def walk(n: str, d: int, seen: set[str]) -> None:
        if n in seen:
            return
        seen.add(n)
        out.append((n, d))
        for c in children(cfg, n):
            walk(c, d + 1, seen)

    walk(cfg.root_id, 0, set())
    return out


def docs_by_topic(docs: list[Doc]) -> tuple[dict[str, list[Doc]], dict[str, list[Doc]]]:
    primary: dict[str, list[Doc]] = {}
    secondary: dict[str, list[Doc]] = {}
    for d in docs:
        for i, t in enumerate(d.topics):
            (primary if i == 0 else secondary).setdefault(t, []).append(d)
    return primary, secondary


def column_rank(cfg: Config, label: str) -> int:
    labels = [str(c.get("label")) for c in cfg.columns]
    return labels.index(label) if label in labels else len(labels)


def subtree_count(cfg: Config, nid: str, primary: dict[str, list[Doc]], seen: frozenset = frozenset()) -> int:
    if nid in seen:
        return 0
    return len(primary.get(nid, [])) + sum(subtree_count(cfg, c, primary, seen | {nid}) for c in children(cfg, nid))


def summary_text(doc: Doc, limit: int = DISPLAY_SUMMARY) -> str:
    if not doc.summary:
        return "（缺摘要）"
    return (AUTO_MARK if doc.auto else "") + short(doc.summary, limit)


def doc_line(cfg: Config, page: Path, doc: Doc, with_primary: bool = False) -> str:
    status = f" `状态: {doc.status}`" if doc.status else ""
    sup = f" `被替代: {doc.superseded_by}`" if doc.superseded_by else ""
    prim = f" （主归属 `{doc.topics[0]}`）" if with_primary and doc.topics else ""
    return f"- [{doc.title}]({relink(cfg, page, doc.path)}){status}{sup}{prim} — {summary_text(doc)}"


def sort_docs(cfg: Config, docs: list[Doc]) -> list[Doc]:
    return sorted(docs, key=lambda d: (column_rank(cfg, d.column), d.path))


def render_tree(cfg: Config, on_tree: list[Doc], total: int) -> str:
    primary, _ = docs_by_topic(on_tree)
    root = cfg.nodes[cfg.root_id]
    lines = [marker(cfg), "", f"# {root.title} · 知识树", ""]
    if root.one_line:
        lines += [root.one_line, ""]
    lines.append("从上往下找：先按主题选节点，节点页按列列出该主题的文档和一句话摘要；"
                 f"摘要前标 {AUTO_MARK} 的是机械摘录，可能不准。")
    tail = f"共 {len(on_tree)} 份文档挂在树上（扫描范围内 {total} 份）。"
    if cfg.catalog_out is not None:
        tail += f"没挂上的文档见平铺目录 [CATALOG.md]({relink(cfg, cfg.tree_out, cfg.catalog_out)})；项目原有入口照常使用。"
    else:
        tail += "没挂上的文档用 `rg` 或项目原有入口找。"
    lines += [tail, ""]
    root_docs = sort_docs(cfg, primary.get(cfg.root_id, []))
    if root_docs:
        lines += ["## 总览", ""] + [doc_line(cfg, cfg.tree_out, d) for d in root_docs] + ["", "## 主题", ""]
    for nid, depth in depth_first(cfg):
        if nid == cfg.root_id:
            continue
        n = cfg.nodes[nid]
        link = relink(cfg, cfg.tree_out, cfg.node_dir / f"{nid}.md")
        lines.append(f"{'  ' * (depth - 1)}- [{n.title}]({link}) `{nid}` · {subtree_count(cfg, nid, primary)} 份 — {n.one_line}")
    lines.append("")
    return "\n".join(lines)


def render_node(cfg: Config, nid: str, on_tree: list[Doc]) -> str:
    primary, secondary = docs_by_topic(on_tree)
    n = cfg.nodes[nid]
    page = cfg.node_dir / f"{nid}.md"
    crumbs = []
    for a in ancestry(cfg, nid)[:-1]:
        target = cfg.tree_out if a == cfg.root_id else cfg.node_dir / f"{a}.md"
        crumbs.append(f"[{cfg.nodes[a].title}]({relink(cfg, page, target)})")
    body = [marker(cfg), "", f"# {n.title}", ""]
    if crumbs:
        body += ["位置：" + " › ".join(crumbs + [n.title]), ""]
    if n.one_line:
        body += [n.one_line, ""]
    if n.aliases:
        body += ["别名：" + "、".join(n.aliases), ""]
    kids = children(cfg, nid)
    if kids:
        body += ["## 子主题", ""]
        body += [f"- [{cfg.nodes[c].title}]({c}.md) · {subtree_count(cfg, c, primary)} 份 — {cfg.nodes[c].one_line}"
                 for c in kids]
        body.append("")
    own = sort_docs(cfg, primary.get(nid, []))
    if own:
        body += ["## 文档", ""]
        cur = None
        for doc in own:
            if doc.column != cur:
                if cur is not None:
                    body.append("")
                cur = doc.column
                body += [f"### {cur}", ""]
            body.append(doc_line(cfg, page, doc))
        body.append("")
    sec = sort_docs(cfg, secondary.get(nid, []))
    if sec:
        body += ["## 也相关（主归属在别处）", ""] + [doc_line(cfg, page, d, with_primary=True) for d in sec] + [""]
    if not kids and not own and not sec:
        body += ["（暂无文档）", ""]
    return "\n".join(body)


def render_catalog(cfg: Config, docs: list[Doc]) -> str:
    """Flat numbered list of every in-scope doc: the keyword-grep companion of the tree."""
    assert cfg.catalog_out is not None
    lines = [marker(cfg), "", "# 文档目录（编号 + 摘要，平铺）", "",
             f"扫描范围内全部 {len(docs)} 份文档；摘要前标 {AUTO_MARK} 的是机械摘录。"]
    cur = None
    for i, d in enumerate(sort_docs(cfg, docs), 1):
        if d.column != cur:
            cur = d.column
            lines += ["", f"## {cur}", ""]
        lines.append(f"{i:04d}. [{d.title}]({relink(cfg, cfg.catalog_out, d.path)}) — {summary_text(d, 120)}")
    lines.append("")
    return "\n".join(lines)


def render_all(cfg: Config, docs: list[Doc]) -> dict[Path, str]:
    """The output manifest: every managed file and its exact content. build writes it, check compares it."""
    on_tree = [d for d in docs if d.topics]
    files = {cfg.tree_out: render_tree(cfg, on_tree, len(docs))}
    for nid, _depth in depth_first(cfg):
        files[cfg.node_dir / f"{nid}.md"] = render_node(cfg, nid, on_tree)
    if cfg.catalog_out is not None:
        files[cfg.catalog_out] = render_catalog(cfg, docs)
    return files


@dataclass
class WritePlan:
    write: dict[Path, str] = field(default_factory=dict)  # new or changed managed files
    unchanged: list[Path] = field(default_factory=list)
    delete: list[Path] = field(default_factory=list)  # managed pages no longer in the manifest
    unmanaged_targets: list[Path] = field(default_factory=list)  # target exists but is hand-written: refuse
    unmanaged_extra: list[Path] = field(default_factory=list)  # hand-written files sitting in node_dir: keep


def plan_writes(cfg: Config, files: dict[Path, str]) -> WritePlan:
    wp = WritePlan()
    for p, text in sorted(files.items()):
        if p.exists() and (not p.is_file() or not is_managed(p)):
            wp.unmanaged_targets.append(p)
        elif p.is_file() and p.read_text(encoding="utf-8") == text:
            wp.unchanged.append(p)
        else:
            wp.write[p] = text
    if cfg.node_dir.is_dir():
        for p in sorted(cfg.node_dir.glob("*.md")):
            if p in files:
                continue
            (wp.delete if is_managed(p) else wp.unmanaged_extra).append(p)
    return wp
