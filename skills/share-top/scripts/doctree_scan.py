"""doctree scan: which docs are in scope and what each one says (title, summary, topics, status).

The summaries table is the only source of per-doc topics/summary; a doc without an entry falls back
to a mechanical excerpt that the pages mark as unreviewed. Docs are read, never written.
"""

from __future__ import annotations

import functools
import importlib.util
import os
import re
from dataclasses import dataclass
from pathlib import Path

from doctree_model import BUILTIN_EXCLUDE, SKIP_DIRS, Config, as_list, glob_to_regex, match_any, static_prefix, yaml
from doctree_summaries import Entry


# --------------------------------------------------------------------------- frontmatter (reuse sixone_core)


@functools.lru_cache(maxsize=1)
def _sixone_split():
    core = Path(__file__).resolve().parents[1] / "core" / "sixone_core.py"
    if not core.is_file():
        return None
    spec = importlib.util.spec_from_file_location("_doctree_sixone_core", core)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._split_frontmatter


def split_frontmatter(text: str) -> tuple[dict, str]:
    splitter = _sixone_split()
    if splitter is not None:
        fm, _raw, body = splitter(text)
        return fm, body
    if not text.startswith("---\n") or text.find("\n---", 4) == -1:
        return {}, text
    end = text.find("\n---", 4)
    try:
        fm = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError:
        fm = {}
    body = text[end + 4:]
    return (fm if isinstance(fm, dict) else {}), body[1:] if body.startswith("\n") else body


# --------------------------------------------------------------------------- docs

MD_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
H1 = re.compile(r"^#\s+(.+?)\s*#*\s*$")
HN = re.compile(r"^(#{2,4})\s+(.+?)\s*#*\s*$")


@dataclass
class Doc:
    path: str
    title: str
    summary: str
    summary_src: str  # entry | entry-auto | excerpt | none
    topics: list[str]
    topic_src: str  # entry | mount | none
    status: str
    superseded_by: str
    column: str
    headings: list[str]
    body: str = ""

    @property
    def auto(self) -> bool:
        return self.summary_src in ("entry-auto", "excerpt")


def clean_md(text: str) -> str:
    text = MD_LINK.sub(r"\1", text)
    text = re.sub(r"<!--.*?-->", "", text)
    text = text.replace("**", "").replace("__", "")
    return re.sub(r"\s+", " ", text).strip()


def blocks(lines: list[str]) -> list[tuple[str, str]]:
    """Body lines as (kind, text) blocks; kind is para | quote | list | heading | other."""
    out: list[tuple[str, str]] = []
    buf: list[str] = []
    kind, in_fence = "", False

    def flush() -> None:
        nonlocal buf, kind
        if buf:
            out.append((kind, " ".join(buf)))
        buf, kind = [], ""

    for line in lines:
        s = line.strip()
        if s.startswith(("```", "~~~")):
            flush()
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not s:
            flush()
        elif s.startswith("#"):
            flush()
            out.append(("heading", s))
        elif s.startswith(("|", "<!--")) or re.match(r"^[-*_]{3,}$", s):
            flush()
            out.append(("other", s))
        else:
            k = "quote" if s.startswith(">") else ("list" if re.match(r"^([-*+]|\d+\.)\s", s) else "para")
            if kind and k != kind:
                flush()
            kind = kind or k
            buf.append(s.lstrip(">").strip())
    flush()
    return out


def excerpt(body: str, sections: tuple[str, ...]) -> str:
    """Mechanical summary: the named one-line section, else the first paragraph (plain beats quoted metadata)."""
    bl = blocks(body.splitlines())
    sec_re = re.compile(r"^#{2,3}\s*(" + "|".join(re.escape(s) for s in sections) + r")\s*[:：]?\s*$")
    for idx, (kind, text) in enumerate(bl):
        if kind == "heading" and sec_re.match(text):
            for k2, t2 in bl[idx + 1:]:
                if k2 == "heading":
                    break
                if k2 in ("para", "quote", "list") and clean_md(t2):
                    return clean_md(t2)[:300]
    head = []
    for kind, text in bl:
        if kind == "heading" and text.startswith("##"):
            break
        head.append((kind, text))
    for want in ("para", "quote"):
        for kind, text in head:
            if kind == want and len(clean_md(text)) >= 8:
                return clean_md(text)[:300]
    for kind, text in bl:
        if kind == "para" and len(clean_md(text)) >= 8:
            return clean_md(text)[:300]
    return ""


def title_and_headings(body: str, fallback: str) -> tuple[str, list[str]]:
    title, headings = "", []
    for line in body.splitlines():
        m = H1.match(line)
        if m and not title:
            title = clean_md(m.group(1))
            continue
        m2 = HN.match(line)
        if m2:
            headings.append(clean_md(m2.group(2)))
    return title or fallback, headings[:20]


def mount_topics(cfg: Config, rel: str) -> list[str]:
    topics: list[str] = []
    for m in cfg.mounts:
        if match_any(rel, as_list(m.get("glob"))):
            topics += [t for t in as_list(m.get("topics")) if t not in topics]
    return topics


def column_of(cfg: Config, rel: str) -> str:
    for c in cfg.columns:
        if match_any(rel, as_list(c.get("glob"))):
            return str(c.get("label"))
    return "其他"


def read_doc(cfg: Config, rel: str, entries: dict[str, Entry]) -> Doc:
    text = (cfg.root / rel).read_text(encoding="utf-8", errors="replace")
    fm, body = split_frontmatter(text)
    title, headings = title_and_headings(body, Path(rel).stem)
    entry = entries.get(rel)
    if entry is not None and entry.summary:
        summary, src = entry.summary, ("entry" if entry.source == "reviewed" else "entry-auto")
    else:
        summary = excerpt(body, cfg.summary_sections)
        src = "excerpt" if summary else "none"
    if entry is not None and entry.topics:
        topics, tsrc = list(entry.topics), "entry"
    else:
        topics = mount_topics(cfg, rel)
        tsrc = "mount" if topics else "none"
    return Doc(path=rel, title=title, summary=summary, summary_src=src, topics=topics, topic_src=tsrc,
               status=str(fm.get("status") or ""), superseded_by=str(fm.get("superseded_by") or ""),
               column=column_of(cfg, rel), headings=headings, body=body)


def managed_outputs_rel(cfg: Config) -> list[str]:
    """Generated paths (repo-relative) that the scan must never treat as docs."""
    out = []
    for p in (cfg.tree_out, cfg.catalog_out):
        if p is not None:
            out.append(cfg.rel(p))
    out.append(cfg.rel(cfg.node_dir).rstrip("/") + "/**")
    return out


def scan_paths(cfg: Config) -> list[str]:
    """Walk only the include globs' static prefixes (never the whole repo)."""
    exclude = [*cfg.exclude, *BUILTIN_EXCLUDE, *managed_outputs_rel(cfg)]
    found: set[str] = set()
    for pat in cfg.include:
        base = cfg.root / static_prefix(pat)
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for name in filenames:
                if not name.endswith(".md"):
                    continue
                rel = (Path(dirpath) / name).relative_to(cfg.root).as_posix()
                if glob_to_regex(pat).match(rel) and not match_any(rel, exclude):
                    found.add(rel)
    return sorted(found)


def load_docs(cfg: Config, entries: dict[str, Entry]) -> list[Doc]:
    """Every in-scope doc; the tree shows those with topics, the catalog shows all."""
    return [read_doc(cfg, rel, entries) for rel in scan_paths(cfg)]
