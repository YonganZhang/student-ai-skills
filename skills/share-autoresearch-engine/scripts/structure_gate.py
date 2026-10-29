#!/usr/bin/env python3
"""Validate and bind a structural-judgment card before an optimizer step.

JSON is the canonical format; YAML is accepted when PyYAML is installed.

The card is a small JSON record of the six-field judgment in
references/architecture-judgment-gate.md. A training entry calls require_card()
and record_binding() before creating its optimizer; a command-line check is also
available for authors and reviewers.

  python3 structure_gate.py check --card CARD.json [--config CONFIG.json]
  python3 structure_gate.py hash --config CONFIG.json
  python3 structure_gate.py template --out CARD.json

Exit 0 = valid, 2 = invalid/missing; a training entry exits nonzero on a binding conflict.
A valid card is a process contract, not evidence that the proposed mechanism is
correct; it only proves the six fields exist and the run is bound to them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import sys
import time
from pathlib import Path

SCHEMA = "structure-judgment/v1"
BINDING_SCHEMA = "structure-gate-binding/v1"
TEXT_FIELDS = ("target_model", "failure_mode", "failure_evidence", "structure_map",
               "mechanism_hypothesis", "falsification")
AXES = ("position", "module", "mechanism")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
TEMPLATE = {
    "schema": SCHEMA,
    "target_model": "",
    "failure_mode": "",
    "failure_evidence": "",
    "structure_map": "",
    "candidate_positions": [
        {"id": "P0", "name": "native / paper position", "why": ""},
        {"id": "P1", "name": "second position", "why": ""},
    ],
    "single_position_reason": "",
    "mechanism_hypothesis": "",
    "single_axis": {
        "axis": "position",
        "baseline": "",
        "budget_steps": 0,
        "seeds": [],
        "primary_metric": "",
        "success_threshold": "",
    },
    "falsification": "",
    "config_sha256": "",
}


class GateError(ValueError):
    """The card is missing, unreadable, incomplete, or bound to another config."""


def canonical_sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def load_config(path: Path) -> dict:
    """Load JSON, or YAML when PyYAML is available; reject non-object roots."""
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml
        except ImportError as exc:
            raise GateError("config is not JSON and PyYAML is not installed") from exc
        try:
            data = yaml.safe_load(text)
        except Exception as exc:
            raise GateError(f"cannot parse config {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise GateError("config must be a mapping/object")
    return data


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _text(obj: dict, key: str, label: str, issues: list[str]) -> None:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        issues.append(f"{label}.{key} must be a nonempty string")


def validate_card(data) -> list[str]:
    """Return a list of contract violations; an empty list means the card is complete."""
    issues: list[str] = []
    if not isinstance(data, dict):
        return ["card root must be a JSON object"]
    if data.get("schema") != SCHEMA:
        issues.append(f"schema must be {SCHEMA!r}")
    for key in TEXT_FIELDS:
        _text(data, key, "card", issues)

    positions = data.get("candidate_positions")
    if not isinstance(positions, list) or not positions:
        issues.append("candidate_positions must be a nonempty list")
        positions = []
    seen_ids = set()
    for i, pos in enumerate(positions):
        if not isinstance(pos, dict):
            issues.append(f"candidate_positions[{i}] must be an object")
            continue
        for key in ("id", "name", "why"):
            _text(pos, key, f"candidate_positions[{i}]", issues)
        pid = pos.get("id")
        if isinstance(pid, str) and pid.strip():
            if pid in seen_ids:
                issues.append(f"duplicate candidate position id: {pid}")
            seen_ids.add(pid)
    if len(positions) == 1:
        reason = data.get("single_position_reason")
        if not isinstance(reason, str) or not reason.strip():
            issues.append("one position requires nonempty single_position_reason")

    axis = data.get("single_axis")
    if not isinstance(axis, dict):
        issues.append("single_axis must be an object")
    else:
        if axis.get("axis") not in AXES:
            issues.append(f"single_axis.axis must be one of {AXES}")
        _text(axis, "baseline", "single_axis", issues)
        _text(axis, "primary_metric", "single_axis", issues)
        _text(axis, "success_threshold", "single_axis", issues)
        budget = axis.get("budget_steps")
        if type(budget) is not int or budget <= 0:
            issues.append("single_axis.budget_steps must be a positive integer")
        seeds = axis.get("seeds")
        if not isinstance(seeds, list) or not seeds or not all(type(s) is int for s in seeds):
            issues.append("single_axis.seeds must be a nonempty integer list")

    claimed = data.get("config_sha256", "")
    if claimed and (not isinstance(claimed, str) or not HEX64.fullmatch(claimed)):
        issues.append("config_sha256 must be empty or 64 lowercase hex characters")
    return issues


def load_card(path: Path) -> tuple[dict, str]:
    path = Path(path).expanduser().resolve()
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise GateError(f"cannot read card {path}: {exc}") from exc
    issues = validate_card(data)
    if issues:
        raise GateError("invalid structure card: " + "; ".join(issues))
    return data, sha_file(path)


def check_binding(data: dict, config: dict | None) -> str | None:
    """Return the actual config hash, and reject a card bound to a different config."""
    if config is None:
        return None
    if not isinstance(config, dict):
        raise GateError("config must be a mapping/object")
    actual = canonical_sha(config)
    claimed = data.get("config_sha256", "")
    if claimed and claimed != actual:
        raise GateError(f"card config_sha256={claimed} does not match current config {actual}")
    return actual


def require_card(card: Path | str | None, config: dict | None = None, *, required: bool = True,
                 action: str = "training", expected_budget: int | None = None,
                 expected_seed: int | None = None) -> dict | None:
    """Validate a card before optimizer creation.

    required=True is the normal contract for any structural change. required=False
    is only for a baseline that changes no structure; even then, a supplied card
    is validated rather than silently ignored.
    """
    if card is None:
        if required:
            raise GateError(f"{action}: structural change requires --structure-card "
                            "(see assets/structure-card.template.json)")
        return None
    data, card_sha = load_card(Path(card))
    axis = data["single_axis"]
    if expected_budget is not None and axis["budget_steps"] != expected_budget:
        raise GateError(f"card budget_steps={axis['budget_steps']} does not match run budget {expected_budget}")
    if expected_seed is not None and expected_seed not in axis["seeds"]:
        raise GateError(f"card seeds={axis['seeds']} does not include this run's seed {expected_seed}")
    config_sha = check_binding(data, config)
    return dict(status="ok", card=str(Path(card).expanduser().resolve()), card_sha256=card_sha,
                config_sha256=config_sha, schema=SCHEMA,
                budget_steps=axis["budget_steps"], seeds=list(axis["seeds"]))


def record_binding(out: Path | str, card: Path | str, result: dict, argv: list[str] | None = None) -> Path:
    """Write once, or verify the same card+config on resume; never overwrite."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "structure_gate.json"
    rec = dict(schema=BINDING_SCHEMA, card=result["card"], card_sha256=result["card_sha256"],
               config_sha256=result.get("config_sha256"), argv=list(argv or []),
               host=socket.gethostname(), validated_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    snapshot = out / "structure_card.json"
    if snapshot.exists():
        if sha_file(snapshot) != result["card_sha256"]:
            raise GateError(f"card snapshot conflict in {snapshot}; use a new run directory")
    else:
        try:
            fd = os.open(snapshot, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "wb") as f:
                f.write(Path(card).expanduser().read_bytes())
        except FileExistsError:
            if sha_file(snapshot) != result["card_sha256"]:
                raise GateError(f"card snapshot conflict in {snapshot}; use a new run directory")
    if path.exists():
        try:
            old = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            raise GateError(f"unreadable existing binding {path}: {exc}") from exc
        for key in ("card_sha256", "config_sha256"):
            if old.get(key) != rec.get(key):
                raise GateError(f"binding conflict in {path}: {key} changed; use a new run directory")
        return path
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
    except FileExistsError:
        return record_binding(out, card, result, argv)
    return path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("check", help="validate a card (and optionally bind it to a JSON/YAML config)")
    p.add_argument("--card", type=Path, required=True)
    p.add_argument("--config", type=Path)
    p.add_argument("--no-require", action="store_true", help="baseline: a missing card is allowed")

    h = sub.add_parser("hash", help="print the canonical config hash used by the gate")
    h.add_argument("--config", type=Path, required=True)

    t = sub.add_parser("template", help="write an empty card template")
    t.add_argument("--out", type=Path, required=True)

    a = ap.parse_args(argv)
    if a.cmd == "template":
        if a.out.exists():
            print(json.dumps({"status": "blocked", "error": f"refusing to overwrite {a.out}"}, ensure_ascii=False))
            return 2
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(TEMPLATE, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"status": "ok", "template": str(a.out.resolve())}, ensure_ascii=False))
        return 0

    try:
        config = load_config(a.config) if a.config else None
        if a.cmd == "hash":
            if not isinstance(config, dict):
                raise GateError("config must be a mapping/object")
            print(json.dumps({"config_sha256": canonical_sha(config)}, ensure_ascii=False))
            return 0
        result = require_card(a.card, config, required=not a.no_require, action="check")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
