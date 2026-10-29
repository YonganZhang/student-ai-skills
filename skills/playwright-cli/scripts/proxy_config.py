#!/usr/bin/env python3
"""Write a private playwright-cli config that sends Chromium through this account's proxy; print its path.

    playwright-cli -s=<name> open --config="$(python3 ~/.claude/skills/playwright-cli/scripts/proxy_config.py)" <url>

Chromium reads HTTPS_PROXY by itself but cannot use the credentials inside it, so every site
outside NO_PROXY fails with net::ERR_INVALID_AUTH_CREDENTIALS. Playwright answers the proxy's
auth challenge when the credentials come as launch options, which this config provides.
The file holds the proxy password: it goes to $XDG_RUNTIME_DIR (or ~/.cache; 0700 dir, 0600 file)
and only its path is printed. Exit 1 when no proxy is set.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


def main() -> int:
    proxy = next((os.environ[k] for k in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy") if os.environ.get(k)), "")
    if not proxy:
        print("no HTTPS_PROXY/ALL_PROXY in the environment", file=sys.stderr)
        return 1
    url = urlsplit(proxy)
    settings = {"server": f"{url.scheme}://{url.hostname}:{url.port}"}
    if url.username:
        settings["username"] = unquote(url.username)
        settings["password"] = unquote(url.password or "")
    bypass = os.environ.get("NO_PROXY") or os.environ.get("no_proxy")
    if bypass:
        settings["bypass"] = bypass
    config = {"browser": {"browserName": "chromium", "launchOptions": {"proxy": settings}}}

    runtime = os.environ.get("XDG_RUNTIME_DIR") or str(Path.home() / ".cache")
    folder = Path(runtime) / "playwright-cli"
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    folder.chmod(0o700)
    path = folder / "proxy.json"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(config, handle)
    path.chmod(0o600)
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
