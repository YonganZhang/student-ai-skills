#!/usr/bin/env python3
"""Read-only six-column owner discovery and typed-reference resolution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from top_common import project_root


SCHEMA_VERSION = "sixone-owner/v1"


OWNER_PATHS = {
    "wiki": ["_wiki-methodology/_wiki"],
    "top": ["_wiki-methodology/_top"],
    "tests": ["_wiki-methodology/_tests", "tests"],
    "code": ["_codemap.md", "_codebook", "_meta/_registry.yml", "_code", "_pipelines", "src"],
    "lifecycle": ["_meta/_data_registry.yml", "_meta/_capabilities.yml", "_tmp", "_sandbox", "_outputs", "_legacy"],
    "picture": ["_whole_picture"],
}


def _root(project: str) -> Path:
    return project_root(Path(project))


def list_owners(project: str) -> dict[str, Any]:
    root = _root(project)
    owners = []
    for name, candidates in OWNER_PATHS.items():
        paths = [path for path in candidates if (root / path).exists()]
        owners.append({"column": name, "paths": paths, "enabled": bool(paths)})
    return {"schema_version": SCHEMA_VERSION, "tool": "owner-list", "project": str(root), "owners": owners}


def show(project: str, column: str) -> dict[str, Any]:
    root = _root(project)
    if column not in OWNER_PATHS:
        return {"error": f"unknown owner column: {column}"}
    candidates = OWNER_PATHS[column]
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": "owner-show",
        "project": str(root),
        "column": column,
        "paths": [
            {"path": path, "exists": (root / path).exists(), "type": "dir" if (root / path).is_dir() else "file"}
            for path in candidates
        ],
    }


def _safe_relative(root: Path, value: str) -> Path | None:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        return None
    candidate = (root / path).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def _yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def resolve_ref(project: str, typed_ref: str) -> dict[str, Any]:
    root = _root(project)
    if ":" not in typed_ref:
        return {"error": "typed ref must use <kind>:<value>"}
    kind, value = typed_ref.split(":", 1)
    kind, value = kind.lower().strip(), value.strip()
    matches: list[dict[str, Any]] = []
    if kind == "path":
        path = _safe_relative(root, value)
        if path is not None:
            matches.append({"path": str(path.relative_to(root)), "exists": path.exists()})
    elif kind in {"registry", "code"}:
        registry = _yaml(root / "_meta" / "_registry.yml")
        for key, entries in registry.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if isinstance(entry, dict) and str(entry.get("id")) == value:
                    matches.append({"owner": "_meta/_registry.yml", "registry_key": key, "entry": entry})
    elif kind == "data":
        registry = _yaml(root / "_meta" / "_data_registry.yml")
        for key, entries in registry.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if isinstance(entry, dict) and str(entry.get("id")) == value:
                    matches.append({"owner": "_meta/_data_registry.yml", "registry_key": key, "entry": entry})
    elif kind == "pipeline":
        pdir = root / "_pipelines"
        for path in sorted(pdir.glob("*.y*ml")) if pdir.is_dir() else []:
            data = _yaml(path)
            if value in {str(data.get("pipeline")), str(data.get("id")), path.stem.lstrip("_")}:
                matches.append({"path": str(path.relative_to(root)), "id": data.get("pipeline") or data.get("id")})
    elif kind in {"gate", "test"}:
        path = root / "_wiki-methodology" / "_tests" / "_gates.yml"
        for gate in _yaml(path).get("gates") or []:
            if isinstance(gate, dict) and str(gate.get("id")) == value:
                matches.append({"owner": str(path.relative_to(root)), "entry": gate})
    elif kind in {"codebook", "finding"}:
        base = root / ("_codebook" if kind == "codebook" else "_wiki-methodology/_top/_findings")
        direct = _safe_relative(base, value)
        candidates = []
        if direct and direct.is_file():
            candidates.append(direct)
        if base.is_dir():
            candidates.extend(path for path in base.glob("*.md") if value in {path.name, path.stem})
        for path in sorted(set(candidates)):
            matches.append({"path": str(path.relative_to(root)), "exists": True})
    elif kind == "symbol":
        return {
            "schema_version": SCHEMA_VERSION,
            "tool": "owner-resolve",
            "project": str(root),
            "ref": typed_ref,
            "matches": [],
            "next_hint": f"search symbol {value!r} in {str(root)!r} (codegraph or rg), then verify source/registry",
        }
    else:
        return {"error": f"unsupported typed ref kind: {kind}"}
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": "owner-resolve",
        "project": str(root),
        "ref": typed_ref,
        "matches": matches,
        "count": len(matches),
        "next_hint": "open the owner source and verify directly" if matches else "no owner match; check spelling or register the new asset",
    }
