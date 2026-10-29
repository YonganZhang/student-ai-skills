"""doctree summaries: the per-doc table (_meta/_doc_summaries.yml) — reading, and targeted stamping.

The table is written by people and AIs. The tool only ever edits one thing in it: `source` and
`reviewed_sha` of the entries it stamps, in place, by character offsets from the YAML parser.
Every other byte (other entries, broken entries, comments, quoting, order) stays as it was.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from doctree_model import ConfigError, as_list, read_text_strict, read_yaml, yaml

ENTRY_KEYS = ("topics", "summary", "source", "reviewed_sha")
SOURCES = ("reviewed", "auto")


@dataclass
class Entry:
    path: str
    topics: list[str]
    summary: str
    source: str
    reviewed_sha: str
    extra: dict = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)


def restricted_syntax(text: str, path: Path) -> None:
    """The table is tool-managed: plain or quoted scalars only. Block scalars, anchors and aliases are refused
    because a targeted edit cannot prove it touches only the target entry when they are present."""
    problems = []
    for ev in yaml.parse(text):
        line = ev.start_mark.line + 1
        if isinstance(ev, yaml.AliasEvent):
            problems.append(f"line {line}: alias *{ev.anchor}")
        elif getattr(ev, "anchor", None):
            problems.append(f"line {line}: anchor &{ev.anchor}")
        elif isinstance(ev, yaml.ScalarEvent) and ev.style in ("|", ">"):
            problems.append(f"line {line}: block scalar {ev.style}")
    if problems:
        raise ConfigError(f"{path.name}: only plain or quoted scalars are allowed (no block scalars, anchors, aliases): "
                          + "; ".join(problems[:5]) + (f"; +{len(problems) - 5} more" if len(problems) > 5 else ""))


def parse_summaries(text: str, path: Path) -> dict[str, Entry]:
    data = read_yaml(path, text) or {}
    restricted_syntax(text, path)
    if not isinstance(data, dict) or not isinstance(data.get("docs") or {}, dict):
        raise ConfigError(f"{path.name}: expected `docs: {{<repo path>: {{topics, summary, source, reviewed_sha}}}}`")
    if data.get("version", 1) != 1:
        raise ConfigError(f"{path.name}: unsupported version {data.get('version')!r}")
    entries: dict[str, Entry] = {}
    for key, value in (data.get("docs") or {}).items():
        rel, value = str(key), value or {}
        problems: list[str] = []
        if not isinstance(value, dict):
            value, problems = {}, ["entry must be a mapping"]
        if Path(rel).is_absolute() or ".." in Path(rel).parts or rel.startswith("./"):
            problems.append("key must be a repo-relative path (no leading '/', './' or '..')")
        topics = value.get("topics")
        if topics is not None and not isinstance(topics, (list, str)):
            problems.append("topics must be a list of node ids")
        source = str(value.get("source") or "auto")
        if source not in SOURCES:
            problems.append(f"source must be one of {', '.join(SOURCES)} (got {source!r})")
        entries[rel] = Entry(path=rel, topics=as_list(topics), summary=str(value.get("summary") or "").strip(),
                             source=source, reviewed_sha=str(value.get("reviewed_sha") or ""),
                             extra={k: v for k, v in value.items() if k not in ENTRY_KEYS}, problems=problems)
    return entries


def load_summaries(path: Path) -> dict[str, Entry]:
    """Missing file = no entries (a tree may live on mount rules alone)."""
    if not path.is_file():
        return {}
    return parse_summaries(read_text_strict(path), path)


class StampRefused(Exception):
    def __init__(self, failures: list[dict]):
        super().__init__("; ".join(f"{f['path']}: {f['error']}" for f in failures))
        self.failures = failures


def _entry_nodes(text: str) -> dict[str, list[tuple]]:
    root = yaml.compose(text)
    docs = None
    if isinstance(root, yaml.MappingNode):
        docs = next((v for k, v in root.value if isinstance(k, yaml.ScalarNode) and k.value == "docs"), None)
    found: dict[str, list[tuple]] = {}
    if isinstance(docs, yaml.MappingNode):
        for k, v in docs.value:
            if isinstance(k, yaml.ScalarNode):
                found.setdefault(k.value, []).append((k, v))
    return found


def _apply_edits(text: str, edits: list[tuple[int, int, str]]) -> str:
    for start, end, repl in sorted(edits, key=lambda e: (e[0], e[1]), reverse=True):
        text = text[:start] + repl + text[end:]
    return text


def _verify(old_text: str, new_text: str, targets: dict[str, str], path: Path) -> None:
    """Last gate before disk: the new table parses, non-targets are unchanged, targets carry the new stamp."""
    old = parse_summaries(old_text, path)
    try:
        new = parse_summaries(new_text, path)
    except ConfigError as exc:
        raise StampRefused([{"path": path.name, "error": f"edit would break the table ({exc}); nothing written"}]) from exc
    bad = sorted(set(old) ^ set(new))
    for rel in sorted(set(old) & set(new)):
        want = old[rel]
        if rel in targets:
            want = Entry(**{**want.__dict__, "source": "reviewed", "reviewed_sha": targets[rel]})
        if new[rel] != want:
            bad.append(rel)
    if bad:
        raise StampRefused([{"path": rel, "error": "edit would change content it must not touch; nothing written"} for rel in bad])


def stamp_text(text: str, targets: dict[str, str], path: Path = Path("_doc_summaries.yml")) -> str:
    """Set `source: reviewed` and `reviewed_sha` on each target entry; nothing else changes.
    targets maps repo path -> content sha. Raises StampRefused when an entry cannot be edited safely."""
    restricted_syntax(text, path)
    nodes = _entry_nodes(text)
    edits: list[tuple[int, int, str]] = []
    failures: list[dict] = []
    for rel, sha in targets.items():
        pairs = nodes.get(rel, [])
        if len(pairs) != 1:
            failures.append({"path": rel, "error": "no entry in the table" if not pairs else "entry appears more than once"})
            continue
        _key, value = pairs[0]
        if not isinstance(value, yaml.MappingNode) or value.flow_style or not value.value:
            failures.append({"path": rel, "error": "entry is not a block mapping (key: value lines); edit it by hand"})
            continue
        fields = {k.value: v for k, v in value.value if isinstance(k, yaml.ScalarNode)}
        if any(not isinstance(fields[k], yaml.ScalarNode) for k in ("source", "reviewed_sha") if k in fields):
            failures.append({"path": rel, "error": "source / reviewed_sha must be plain values; edit by hand"})
            continue
        first = value.value[0][0]
        line_start = text.rfind("\n", 0, first.start_mark.index) + 1
        if text[line_start:first.start_mark.index].strip():
            failures.append({"path": rel, "error": "entry layout not understood; edit it by hand"})
            continue
        indent = " " * first.start_mark.column
        new = {"source": "reviewed", "reviewed_sha": f"'{sha}'"}
        missing = []
        for key in ("source", "reviewed_sha"):
            node = fields.get(key)
            if node is None:
                missing.append(f"{indent}{key}: {new[key]}\n")
            else:
                start, end = node.start_mark.index, node.end_mark.index
                edits.append((start, end, new[key] if start != end else " " + new[key]))
        if missing:
            src = fields.get("source")
            if src is not None and src.start_mark.line == src.end_mark.line:
                eol = text.find("\n", src.end_mark.index)
                at = len(text) if eol == -1 else eol + 1
                prefix = "\n" if eol == -1 else ""
                edits.append((at, at, prefix + "".join(missing)))
            else:
                edits.append((line_start, line_start, "".join(missing)))
    if failures:
        raise StampRefused(failures)
    new_text = _apply_edits(text, edits)
    _verify(text, new_text, targets, path)
    return new_text
