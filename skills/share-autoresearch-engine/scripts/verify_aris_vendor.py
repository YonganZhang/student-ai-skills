#!/usr/bin/env python3
"""Verify the explicitly recorded ARIS upstream files; not model correctness."""
import hashlib
import json
from pathlib import Path
import sys


def main():
    root = Path(__file__).resolve().parents[1] / "references/aris/vendor"
    manifest = json.loads((root / "MANIFEST.json").read_text())
    errors = []
    for entry in manifest["files"]:
        path = root / entry["local"]
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            errors.append(entry["local"])
    print(json.dumps({"commit": manifest["commit"], "files": len(manifest["files"]),
                      "status": "changed" if errors else "verified", "errors": errors}))
    return int(bool(errors))


if __name__ == "__main__":
    sys.exit(main())
