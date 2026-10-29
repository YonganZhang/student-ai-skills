"""Validate a wheel-installed CLI from a cwd outside its source checkout.

Usage: python verify_distribution.py --python ENV/bin/python
       --command ENV/bin/example-cli --target generated/README.md
"""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True, type=Path)
    parser.add_argument("--command", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    args = parser.parse_args()
    executable, python, target = args.command.resolve(), args.python.absolute(), args.target.resolve(strict=True)
    name = args.command.name
    with tempfile.TemporaryDirectory() as cwd:
        version = subprocess.check_output(
            [str(python), "-c", "from importlib.metadata import version; import sys; print(version(sys.argv[1]))", name],
            cwd=cwd, text=True).strip()
        checks = []
        for options, expected in [(["--help"], 0), (["--version"], 0),
                                  (["inspect", str(target), "--json"], 0),
                                  (["inspect", str(Path(cwd) / "missing"), "--json"], 1),
                                  (["inspect"], 2)]:
            result = subprocess.run([str(executable), *options], cwd=cwd, capture_output=True, text=True)
            assert result.returncode == expected, (options, result.returncode, result.stderr)
            if expected:
                assert not result.stdout and result.stderr, (options, result.stdout, result.stderr)
            else:
                assert not result.stderr, result.stderr
                if "--json" in options:
                    data = json.loads(result.stdout)
                    assert data["schema_version"] == 1 and data["ok"] is True
                    assert data["data"]["path"] == str(target)
                    assert data["data"]["size_bytes"] == target.stat().st_size
                if "--version" in options:
                    assert f"version {version}" in result.stdout
            checks.append({"args": options, "exit_code": result.returncode})
        module = name.removesuffix("-cli").replace("-", "_") + "_cli"
        result = subprocess.run([str(python), "-m", module, "--version"], cwd=cwd, capture_output=True, text=True)
        assert result.returncode == 0 and not result.stderr and f"version {version}" in result.stdout, result
    print(json.dumps({"ok": True, "subprocess_checks": len(checks) + 1, "checks": checks}, ensure_ascii=False))


if __name__ == "__main__":
    main()
