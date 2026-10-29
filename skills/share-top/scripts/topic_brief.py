"""Import shim for topic-brief.py.

The executable keeps the historical hyphenated script name; tests and sibling
tools import through this underscore module.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).with_name("topic-brief.py")
_SPEC = importlib.util.spec_from_file_location("_topic_brief_impl", _SCRIPT)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load {_SCRIPT}")
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

for _name in dir(_MODULE):
    if not _name.startswith("_"):
        globals()[_name] = getattr(_MODULE, _name)
