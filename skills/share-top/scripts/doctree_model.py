"""doctree model: tree config, the per-doc summaries table, scanning and doc reading.

Owners (one field, one owner):
  _meta/_doc_tree.yml       nodes, scan scope, coverage, group mount rules, output paths, place thresholds
  _meta/_doc_summaries.yml  per-doc topics (first = primary), summary, source, reviewed_sha
Docs themselves are never read for tree fields and never written. Their own `status:` /
`superseded_by:` are quoted verbatim on the generated pages.
"""

from __future__ import annotations

import functools
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml
except ImportError:  # pragma: no cover - same dependency class as sixone brief/doctor
    yaml = None

DEFAULT_TREE = "_meta/_doc_tree.yml"
DEFAULT_SUMMARIES = "_meta/_doc_summaries.yml"
DEFAULT_OUTPUT = {
    "tree": "_wiki-methodology/TREE.md",
    "node_dir": "_wiki-methodology/_tree",
    "catalog": "_wiki-methodology/CATALOG.md",
}
SUMMARY_SECTIONS_DEFAULT = ("一句话", "一句话结论", "TL;DR", "One-liner")
# share-top's plan structure is written only through `plan`; it is never a topic doc.
BUILTIN_EXCLUDE = (
    "**/_top/_task_plan*.md",
    "**/_top/_plan_details.md",
    "**/_top/_questions/**",
    "**/_top/_logs/**",
    "**/top/task_plan.md",  # legacy layout
)
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__"}
TOP_KEYS = {"version", "root", "output", "summaries", "scan", "coverage", "mounts", "columns",
            "summary_sections", "place", "nodes"}
NODE_KEYS = {"id", "parent", "title", "one_line", "aliases", "place"}
GENERATED_PREFIX = "<!-- doctree:generated"
NODE_ID = re.compile(r"^\w[\w.-]*$")  # a plain file name: node pages are <node_dir>/<id>.md
SHA_LEN = 12


class ConfigError(Exception):
    """Unreadable or invalid tree config / summaries file (exit 2)."""


class MissingDependency(Exception):
    """The environment lacks PyYAML (exit 3, like any runtime failure)."""


def as_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, (str, int, float)):
        return [str(v)]
    if isinstance(v, list):
        return [str(x) for x in v]
    return []


def is_extension_key(key: str) -> bool:
    """`x-…` / `x_…` keys are reserved for project extensions and never warned about."""
    return key.startswith(("x-", "x_"))


def content_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:SHA_LEN]


# --------------------------------------------------------------------------- globbing


@functools.lru_cache(maxsize=None)
def glob_to_regex(pattern: str) -> re.Pattern[str]:
    i, out = 0, ""
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pattern[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile("^" + out + "$")


def match_any(rel: str, patterns: Iterable[str]) -> bool:
    return any(glob_to_regex(p).match(rel) for p in patterns)


def static_prefix(pattern: str) -> str:
    """Directory part of a glob before the first wildcard ("docs/specs/*.md" -> "docs/specs")."""
    parts = []
    for part in pattern.split("/")[:-1]:
        if any(ch in part for ch in "*?["):
            break
        parts.append(part)
    return "/".join(parts)


# --------------------------------------------------------------------------- config


@dataclass
class Node:
    id: str
    title: str
    one_line: str = ""
    parent: str | None = None
    aliases: list[str] = field(default_factory=list)
    place: str = "content"  # "content" | "rule-only" (only mount rules put docs here)


@dataclass
class Config:
    root: Path
    tree_path: Path
    summaries_path: Path
    nodes: dict[str, Node]
    order: list[str]
    root_id: str
    dup_ids: list[str]
    include: list[str]
    exclude: list[str]
    coverage: list[str]
    mounts: list[dict]
    columns: list[dict]
    summary_sections: tuple[str, ...]
    tree_out: Path
    node_dir: Path
    catalog_out: Path | None
    place_cfg: dict
    unknown_keys: list[str]

    def rel(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.root.resolve()).as_posix()
        except ValueError:
            return str(path)


def _inside(root: Path, rel: str, what: str) -> Path:
    p = Path(rel)
    if p.is_absolute() or ".." in p.parts:
        raise ConfigError(f"{what} must be a path relative to the project root without '..': {rel}")
    return root / p


def _mapping(raw: Any, what: str) -> dict:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{what} must be a mapping")
    return raw


def _scalar(raw: Any, what: str) -> str:
    if raw is None:
        return ""
    if isinstance(raw, (dict, list)):
        raise ConfigError(f"{what} must be a single value")
    return str(raw)


def _str_list(raw: Any, what: str) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list) and all(isinstance(x, str) for x in raw):
        return list(raw)
    raise ConfigError(f"{what} must be a string or a list of strings (quote numbers)")


def _rules(raw: Any, what: str, required: tuple[str, ...], lists: tuple[str, ...]) -> list[dict]:
    """A list of mappings, each with the required keys; values named in `lists` become string lists."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ConfigError(f"{what} must be a list")
    out = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict) or any(k not in item for k in required):
            raise ConfigError(f"{what}[{i}] must be a mapping with {', '.join(required)}")
        rule = dict(item)
        for k in lists:
            rule[k] = _str_list(item.get(k), f"{what}[{i}].{k}")
            if k in required and not rule[k]:
                raise ConfigError(f"{what}[{i}].{k} must not be empty")
        out.append(rule)
    return out


def read_text_strict(path: Path) -> str:
    try:
        return path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigError(f"{path.name}: not valid UTF-8 ({exc.reason} at byte {exc.start})") from exc


def read_yaml(path: Path, text: str | None = None) -> Any:
    if yaml is None:
        raise MissingDependency("doctree needs PyYAML (same dependency as sixone brief/doctor)")
    try:
        return yaml.safe_load(read_text_strict(path) if text is None else text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path.name}: YAML error: {exc}") from exc


def _load_nodes(raw: Any, name: str, unknown: list[str]) -> tuple[dict[str, Node], list[str], list[str]]:
    if not isinstance(raw or [], list):
        raise ConfigError(f"{name}: nodes must be a list")
    nodes: dict[str, Node] = {}
    order: list[str] = []
    dup: list[str] = []
    for item in raw or []:
        if not isinstance(item, dict) or not item.get("id"):
            raise ConfigError(f"{name}: every node needs an id")
        nid = _scalar(item["id"], "node id")
        if not NODE_ID.match(nid):
            raise ConfigError(f"{name}: node id {nid!r} must be a plain name (letters, digits, _ . -; no path parts)")
        unknown += [f"{nid}.{k}" for k in item if k not in NODE_KEYS and not is_extension_key(str(k))]
        place = _scalar(item.get("place"), f"node {nid}.place") or "content"
        if place not in ("content", "rule-only"):
            raise ConfigError(f"{name}: node {nid}.place must be content or rule-only")
        if nid in nodes:
            dup.append(nid)
            continue
        nodes[nid] = Node(id=nid, title=_scalar(item.get("title"), f"node {nid}.title") or nid,
                          one_line=_scalar(item.get("one_line"), f"node {nid}.one_line"),
                          parent=_scalar(item.get("parent"), f"node {nid}.parent") or None,
                          aliases=_str_list(item.get("aliases"), f"node {nid}.aliases"), place=place)
        order.append(nid)
    return nodes, order, dup


def _place_cfg(raw: Any, name: str) -> dict:
    place_cfg = _mapping(raw, "place")
    for key in ("min_score", "min_margin"):
        if key in place_cfg and (isinstance(place_cfg[key], bool) or not isinstance(place_cfg[key], (int, float))):
            raise ConfigError(f"{name}: place.{key} must be a number")
    if place_cfg.get("variant", "knn") not in ("knn", "centroid"):
        raise ConfigError(f"{name}: place.variant must be knn or centroid")
    stop = _mapping(place_cfg.get("stopwords"), "place.stopwords")
    for key in stop:
        _str_list(stop[key], f"place.stopwords.{key}")
    return place_cfg


def _check_outputs(root: Path, tree_out: Path, node_dir: Path, catalog: Path | None) -> None:
    """Generated files stay inside the project and never share a path (a collision would silently drop one)."""
    base = root.resolve()
    named = {"output.tree": tree_out, "output.node_dir": node_dir, **({"output.catalog": catalog} if catalog else {})}
    resolved = {}
    for what, p in named.items():
        r = p.resolve()
        if r != base and base not in r.parents:
            raise ConfigError(f"{what} resolves outside the project (symlink?): {r}")
        resolved[what] = r
    if catalog is not None and resolved["output.tree"] == resolved["output.catalog"]:
        raise ConfigError("output.tree and output.catalog are the same file")
    for what in ("output.tree", "output.catalog"):
        if what in resolved and (resolved[what] == resolved["output.node_dir"] or resolved["output.node_dir"] in resolved[what].parents):
            raise ConfigError(f"{what} must not be inside output.node_dir (node pages live there)")


def load_config(root: Path, tree_path: Path, out_dir: Path | None = None,
                summaries_path: Path | None = None) -> Config:
    name = tree_path.name
    raw = read_yaml(tree_path) or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{name}: top level must be a mapping")
    if raw.get("version", 1) != 1:
        raise ConfigError(f"{name}: unsupported version {raw.get('version')!r} (this doctree reads version 1)")
    unknown = [f"<top>.{k}" for k in raw if k not in TOP_KEYS and not is_extension_key(str(k))]
    nodes, order, dup = _load_nodes(raw.get("nodes"), name, unknown)
    scan = _mapping(raw.get("scan"), "scan")
    out = _mapping(raw.get("output"), "output")
    unknown += [f"output.{k}" for k in out if k not in DEFAULT_OUTPUT]
    catalog_raw = out.get("catalog", DEFAULT_OUTPUT["catalog"])
    if out_dir is not None:  # verification output: same file set, different place
        tree_out, node_dir = out_dir / "TREE.md", out_dir / "_tree"
        catalog = (out_dir / "CATALOG.md") if catalog_raw else None
    else:
        tree_out = _inside(root, _scalar(out.get("tree", DEFAULT_OUTPUT["tree"]), "output.tree"), "output.tree")
        node_dir = _inside(root, _scalar(out.get("node_dir", DEFAULT_OUTPUT["node_dir"]), "output.node_dir"), "output.node_dir")
        catalog = _inside(root, _scalar(catalog_raw, "output.catalog"), "output.catalog") if catalog_raw else None
        _check_outputs(root, tree_out, node_dir, catalog)
    if summaries_path is None:
        summaries_path = _inside(root, _scalar(raw.get("summaries"), "summaries") or DEFAULT_SUMMARIES, "summaries")
    roots = [n.id for n in nodes.values() if n.parent is None]
    return Config(
        root=root, tree_path=tree_path, summaries_path=summaries_path, nodes=nodes, order=order,
        root_id=_scalar(raw.get("root"), "root") or (roots[0] if roots else ""), dup_ids=dup,
        include=_str_list(scan.get("include"), "scan.include") or ["**/*.md"],
        exclude=_str_list(scan.get("exclude"), "scan.exclude"),
        coverage=_str_list(raw.get("coverage"), "coverage"),
        mounts=_rules(raw.get("mounts"), "mounts", ("glob", "topics"), ("glob", "topics")),
        columns=[{**c, "label": _scalar(c["label"], "columns[].label")}
                 for c in _rules(raw.get("columns"), "columns", ("label", "glob"), ("glob",))],
        summary_sections=tuple(_str_list(raw.get("summary_sections"), "summary_sections")) or SUMMARY_SECTIONS_DEFAULT,
        tree_out=tree_out, node_dir=node_dir, catalog_out=catalog, place_cfg=_place_cfg(raw.get("place"), name),
        unknown_keys=unknown,
    )
