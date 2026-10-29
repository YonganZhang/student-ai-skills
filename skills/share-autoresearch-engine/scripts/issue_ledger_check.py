#!/usr/bin/env python3
"""Validate an issue-ledger YAML/JSON file without touching project data.

Usage: python scripts/issue_ledger_check.py <ledger.yml> [--strict]

Exit 0 = valid; 2 = contract violations; 1 = usage/parse error.
This is a structural check, not evidence that the issue is real or closed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
STATUS = {"open", "mitigated", "closed", "wontfix"}
SEVERITY = {"P0", "P1", "P2"}
BLOCKS = {"scale", "freeze", "test", "claim", "none"}
LAYERS = {"task", "data", "model", "training", "selection", "eval", "deploy", "process"}
AUTOMATION = {"assert", "script", "gate", "regression", "manual"}
REQUIRED = (
    "id", "title", "status", "severity", "blocks_action", "layer", "symptom",
    "evidence", "root_cause", "invariant", "check", "automation", "owner", "opened",
)


def load(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("PyYAML required for YAML ledger; use JSON or install pyyaml") from exc
    try:
        return yaml.safe_load(text)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"cannot parse {path}: {exc}") from exc


def check(payload: Any, *, strict: bool = False) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["ledger must be a mapping"]
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    issues = payload.get("issues")
    if not isinstance(issues, list):
        return errors + ["issues must be a list"]

    seen: set[str] = set()
    for i, issue in enumerate(issues):
        prefix = f"issues[{i}]"
        if not isinstance(issue, dict):
            errors.append(f"{prefix}: must be a mapping")
            continue
        for key in REQUIRED:
            if key not in issue or issue[key] in ("", None, [], {}):
                errors.append(f"{prefix}.{key}: required and non-empty")
        ident = issue.get("id")
        if isinstance(ident, str):
            if ident in seen:
                errors.append(f"{prefix}.id: duplicate {ident}")
            seen.add(ident)
        for key, allowed in (
            ("status", STATUS), ("severity", SEVERITY), ("blocks_action", BLOCKS),
            ("layer", LAYERS), ("automation", AUTOMATION),
        ):
            value = issue.get(key)
            if value is not None and value not in allowed:
                errors.append(f"{prefix}.{key}: {value!r} not in {sorted(allowed)}")
        evidence = issue.get("evidence")
        if not isinstance(evidence, list):
            errors.append(f"{prefix}.evidence: must be a list of path/fact mappings")
        else:
            if not evidence:
                errors.append(f"{prefix}.evidence: must contain at least one item")
            for j, item in enumerate(evidence):
                if not isinstance(item, dict) or not item.get("path") or not item.get("fact"):
                    errors.append(f"{prefix}.evidence[{j}]: path and fact required")
        if issue.get("status") == "closed":
            for key in ("close_evidence", "closed_by", "reviewed"):
                if not issue.get(key):
                    errors.append(f"{prefix}.{key}: required when status=closed")
        if strict and issue.get("severity") in {"P0", "P1"}:
            if issue.get("automation") == "manual" and not issue.get("reviewed"):
                errors.append(f"{prefix}: manual P0/P1 needs reviewed evidence")
    return errors


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if a != "--strict"]
    if len(args) != 1:
        print("usage: issue_ledger_check.py <ledger.yml> [--strict]", file=sys.stderr)
        return 1
    path = Path(args[0])
    if not path.exists():
        print(f"missing {path}", file=sys.stderr)
        return 1
    try:
        payload = load(path)
        errors = check(payload, strict="--strict" in argv[1:])
    except (ValueError, SystemExit) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if errors:
        print(json.dumps({"status": "invalid", "errors": errors}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps({"status": "ok", "issues": len(payload.get("issues", []))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
