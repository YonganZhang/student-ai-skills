#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${BANANA_SLIDES_PROJECT_ROOT:-$PWD}"
BANANA_REPO="${BANANA_SLIDES_REPO:-$PROJECT_ROOT/_external/banana-slides}"
DEPS_DIR="${BANANA_CLI_DEPS_DIR:-$PROJECT_ROOT/_tmp/banana-cli-deps}"

if [[ ! -d "$BANANA_REPO/cli/banana_cli" ]]; then
  printf 'banana_cli_wrapper: Banana repo not found: %s\n' "$BANANA_REPO" >&2
  exit 127
fi

if [[ ! -d "$DEPS_DIR" ]]; then
  printf 'banana_cli_wrapper: dependency dir not found: %s\n' "$DEPS_DIR" >&2
  printf 'Install isolated deps or rerun the Banana CLI audit setup.\n' >&2
  exit 127
fi

export PYTHONPATH="$DEPS_DIR:$BANANA_REPO${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 -m cli.banana_cli "$@"
