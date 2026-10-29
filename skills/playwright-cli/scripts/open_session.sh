#!/usr/bin/env bash
# Open a playwright-cli browser session (own systemd scope when available; proxy config when a proxy is set).
#
#   open_session.sh <session> [playwright-cli open options...] <url>
#
# The session daemon outlives this command, so when `systemd-run --user` works it gets a scope of its
# own (MemoryMax 2G) instead of staying in the caller's process group, where a group-wide cleanup
# would take the browser with it. Without systemd (macOS, containers) it runs directly.
# Without --config and with HTTPS_PROXY/ALL_PROXY set, the proxy config from proxy_config.py is added;
# pass --config=... to use another one, e.g. a tunnel config.
set -euo pipefail

session="${1:?usage: open_session.sh <session> [open options...] <url>}"
shift
args=("$@")
has_config=false
for arg in "${args[@]}"; do
  [[ "$arg" == --config* ]] && has_config=true
done
command -v playwright-cli >/dev/null 2>&1 || { echo "playwright-cli not found: npm install -g @playwright/cli" >&2; exit 127; }
if ! $has_config && [[ -n "${HTTPS_PROXY:-}${https_proxy:-}${ALL_PROXY:-}${all_proxy:-}" ]]; then
  config="$(python3 "$(cd "$(dirname "$0")" && pwd)/proxy_config.py")"
  args=(--config="$config" "${args[@]}")
fi
if command -v systemd-run >/dev/null 2>&1 && systemd-run --user --scope --quiet true >/dev/null 2>&1; then
  exec systemd-run --user --scope --quiet --collect --unit="playwright-session-$$" \
    -p MemoryHigh=1536M -p MemoryMax=2G \
    playwright-cli -s="$session" open "${args[@]}"
fi
exec playwright-cli -s="$session" open "${args[@]}"
