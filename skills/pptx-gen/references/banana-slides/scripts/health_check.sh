#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BANANA_CLI_BASE_URL:-http://localhost:5011}"
curl -fsS --max-time 10 "$BASE_URL/health" >/dev/null
printf 'OK %s/health\n' "$BASE_URL"
