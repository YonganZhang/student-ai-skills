#!/usr/bin/env python3
"""Use ARIS's original evidence checker, rejecting empty/unparseable batches.

Exit 0 only means every cited value was found, NOT that any claim is correct.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys


def check(claims, root):
    if not isinstance(claims, list) or not claims:
        raise ValueError("claims must be a nonempty list")
    ids = set()
    for item in claims:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"].strip():
            raise ValueError("each claim needs a nonempty string id")
        if item["id"] in ids:
            raise ValueError("duplicate claim id")
        ids.add(item["id"])
        if not isinstance(item.get("source"), str) or not item["source"].strip() or "value" not in item or item["value"] is None:
            raise ValueError("each claim needs source and value")
        if not isinstance(item["value"], (str, int, float)) or isinstance(item["value"], bool) or not str(item["value"]).strip():
            raise ValueError("claim value must be a nonempty string or number")
    source = Path(__file__).resolve().parents[1] / "references/aris/vendor/tools/evidence_check.py"
    spec = importlib.util.spec_from_file_location("aris_upstream_evidence", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.check_batch(claims, str(Path(root).resolve(strict=True)))
    result["status"] = "evidence_found" if all(x["status"] == "verified" for x in result["results"]) else "blocked"
    result["meaning"] = "Value presence only: verify metric key, run, split, seed, units and claim support independently."
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("claims", type=Path)
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = check(json.loads(args.claims.read_text()), args.root)
    except (ValueError, OSError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "evidence_found" else 1


if __name__ == "__main__":
    sys.exit(main())
