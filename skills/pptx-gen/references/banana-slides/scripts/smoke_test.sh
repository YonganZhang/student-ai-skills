#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
WRAPPER="$SCRIPT_DIR/banana_cli_wrapper.sh"

"$WRAPPER" --help >/dev/null
"$WRAPPER" run --help >/dev/null

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

stderr_file="$tmpdir/stderr.json"
stdout_file="$tmpdir/stdout.txt"
set +e
"$WRAPPER" --json --base-url http://127.0.0.1:59999 projects list >"$stdout_file" 2>"$stderr_file"
code=$?
set -e

if [[ "$code" -eq 0 ]]; then
  printf 'Expected backend-down command to fail\n' >&2
  exit 1
fi

/usr/bin/python3 - "$stderr_file" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["success"] is False
assert payload["error"]["code"] == "HTTP_ERROR"
PY

printf 'banana-slides smoke ok\n'
