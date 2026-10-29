"""Keep share-top tests independent of the machine's git setup and AI session.

The global git config installs TOP hooks (core.hooksPath) and the running Claude
or Codex session exports its session id; tests that exercise either set their
own values explicitly.  Everything else sees an empty global config and no
session, as on a clean machine.
"""
from __future__ import annotations

import atexit
import os
import tempfile
from pathlib import Path

_EMPTY = Path(tempfile.mkdtemp(prefix="share-top-tests-")) / "gitconfig"
_EMPTY.write_text("", encoding="utf-8")
atexit.register(lambda: _EMPTY.unlink(missing_ok=True))
os.environ["GIT_CONFIG_GLOBAL"] = str(_EMPTY)
os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
for _name in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "CODEX_SESSION_ID", "TMUX_PANE", "TOP_GIT_HOOKS"):
    os.environ.pop(_name, None)
