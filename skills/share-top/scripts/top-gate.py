#!/usr/bin/env python3
"""Aggregate TOP closeout checks into one compact gate."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from topic_brief import find_project_root


SCRIPT_DIR = Path(__file__).resolve().parent
# Per-platform state: Claude -> ~/.claude/state, Codex -> ~/.codex/state
# (CLAUDECODE env marks Claude Code; SHARE_TOP_PLATFORM=claude|codex overrides).
_PLATFORM = os.environ.get("SHARE_TOP_PLATFORM", "").strip().lower() or (
    "claude" if os.environ.get("CLAUDECODE") else "codex"
)
STATE_DIR = Path.home() / (".claude" if _PLATFORM == "claude" else ".codex") / "state" / "top-gate"
CHECKS = (
    ("closeout", "topic-closeout.py", ()),
    ("doctor", "topic-doctor.py", ("--links",)),
    ("lint", "top-lint.py", ()),
)
SEVERITIES = ("block", "warn", "info")


@dataclass(frozen=True)
class Issue:
    severity: str
    source: str
    code: str
    path: str
    message: str


def parse_tsv(source: str, stdout: str) -> list[Issue]:
    issues: list[Issue] = []
    for line in stdout.splitlines():
        parts = line.split("\t", 3)
        if len(parts) != 4:
            continue
        severity, code, path, message = parts
        if severity not in SEVERITIES:
            continue
        issues.append(Issue(severity, source, code, path, message))
    return issues


def run_check(source: str, script_name: str, extra_args: tuple[str, ...], root: Path, timeout: float) -> list[Issue]:
    script = SCRIPT_DIR / script_name
    if not script.exists():
        return [Issue("block", source, "GATE_SCRIPT_MISSING", str(script), "gate dependency is missing")]

    try:
        result = subprocess.run(
            [sys.executable, str(script), str(root), "--format", "tsv", *extra_args],
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return [Issue("block", source, "GATE_TIMEOUT", script_name, f"check exceeded {timeout:g}s")]

    issues = parse_tsv(source, result.stdout)
    if result.returncode != 0 and not any(issue.severity == "block" for issue in issues):
        detail = (result.stderr or result.stdout or "check failed without details").strip().splitlines()
        message = detail[0] if detail else "check failed without details"
        issues.append(Issue("block", source, "GATE_CHECK_FAILED", script_name, message))
    return issues


def collect_issues(root: Path, timeout: float) -> list[Issue]:
    issues: list[Issue] = []
    for source, script_name, extra_args in CHECKS:
        issues.extend(run_check(source, script_name, extra_args, root, timeout))
    return issues


def counts(issues: list[Issue]) -> dict[str, int]:
    return {severity: sum(1 for issue in issues if issue.severity == severity) for severity in SEVERITIES}


def emit_tsv(issues: list[Issue]) -> None:
    for issue in issues:
        print(f"{issue.severity}\t{issue.source}:{issue.code}\t{issue.path}\t{issue.message}")


def emit_text(root: Path, issues: list[Issue], max_per_severity: int) -> None:
    summary = counts(issues)
    print(f"[top-gate] project={root}")
    print(f"SUMMARY: block={summary['block']} warn={summary['warn']} info={summary['info']}")
    if not issues:
        print("[top-gate] OK")
        return

    for severity in SEVERITIES:
        shown = 0
        total = summary[severity]
        if total == 0:
            continue
        for issue in (item for item in issues if item.severity == severity):
            if shown >= max_per_severity:
                break
            print(f"{severity.upper()}\t{issue.source}:{issue.code}\t{issue.path}\t{issue.message}")
            shown += 1
        if total > shown:
            print(f"{severity.upper()}\tMORE\t.\t{total - shown} more {severity} issue(s)")


# --- diff-not-state: only block what THIS turn introduced/worsened -----------
# Pre-existing debt on files the turn did not touch is downgraded block->info, so
# the Stop gate stops spamming unrelated old issues. Safety contract: every path
# that fails to resolve confidently STAYS block (fail closed); the catastrophic
# direction is under-blocking a real new problem, never over-blocking old debt.


def _git(root: Path, *args: str) -> str | None:
    # A configured TMPDIR can live inside an agent config repository (~/.claude,
    # ~/.codex, a shared skills repo can be Git repositories). Do not let an isolated
    # fixture/work directory inherit that ancestor repo across a tmp boundary:
    # doing so would create a false baseline and downgrade real blocks as
    # "pre-existing" (under-blocking). A genuine repository rooted below /tmp
    # remains valid because its own top-level is reached before the boundary.
    try:
        probe = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            text=True, capture_output=True, check=False, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if probe.returncode != 0:
        return None
    git_root = Path(probe.stdout.strip()).resolve()
    current = root.resolve()
    while current != git_root:
        if current.name.lower() in {"tmp", ".tmp", "temp"}:
            return None
        if current.parent == current:
            return None
        current = current.parent
    try:
        r = subprocess.run(
            ["git", "-C", str(root), *args],
            text=True, capture_output=True, check=False, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def _state_path(root: Path, session: str | None) -> Path:
    # Key by project root AND session_id: a parallel cc session's baseline must not
    # clobber this one's, or Stop would diff against the wrong anchor -> under-block.
    key = hashlib.sha1(str(root.resolve()).encode("utf-8")).hexdigest()[:16]
    if session:
        key = f"{key}.{re.sub(r'[^A-Za-z0-9_-]', '_', session)[:64]}"
    return STATE_DIR / f"{key}.baseline"


def capture_baseline(root: Path, session: str | None) -> None:
    """Record turn-start HEAD (UserPromptSubmit). Fire-and-forget; never raises."""
    head = _git(root, "rev-parse", "HEAD")
    if not head:
        return  # not a git repo / no commits -> consume falls back to full mode
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        _state_path(root, session).write_text(head.strip() + "\n", encoding="utf-8")
    except OSError:
        return


def read_baseline(root: Path, session: str | None) -> str | None:
    try:
        sha = _state_path(root, session).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return sha or None


def touched_paths(root: Path, baseline: str) -> set[Path] | None:
    """Absolute paths changed since baseline: committed-this-turn + uncommitted +
    untracked. Returns None when git cannot answer -> caller must fail CLOSED."""
    top = _git(root, "rev-parse", "--show-toplevel")
    if top is None:
        return None
    git_root = Path(top.strip())
    diff = _git(root, "diff", "--name-only", baseline)
    if diff is None:
        return None  # bad/missing baseline ref -> fail closed (no downgrade)
    untracked = _git(root, "ls-files", "--others", "--exclude-standard") or ""
    touched: set[Path] = set()
    for rel in (diff + "\n" + untracked).splitlines():
        rel = rel.strip()
        if rel:
            touched.add((git_root / rel).resolve())
    return touched


def apply_diff_downgrade(issues: list[Issue], root: Path, touched: set[Path]) -> list[Issue]:
    """block->info for issues NOT attributable to this turn. Path-less (.) blocks
    -> info (documented limitation: a this-turn structural break with no path can
    slip). Unresolvable paths STAY block (fail closed)."""
    out: list[Issue] = []
    for issue in issues:
        if issue.severity != "block":
            out.append(issue)
            continue
        raw = (issue.path or "").strip()
        if raw in ("", "."):
            out.append(Issue("info", issue.source, issue.code, issue.path,
                             "[pre-existing/path-less] " + issue.message))
            continue
        try:
            issue_abs = (root / raw).resolve()
        except (OSError, ValueError, RuntimeError):
            out.append(issue)  # cannot resolve -> fail closed, keep block
            continue
        if issue_abs in touched:
            out.append(issue)  # introduced/worsened this turn -> still blocks
        else:
            out.append(Issue("info", issue.source, issue.code, issue.path,
                             "[pre-existing] " + issue.message))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", nargs="?", default=".", help="project root or nested path")
    parser.add_argument("--format", choices=["text", "tsv"], default="text")
    parser.add_argument("--max-per-severity", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=10.0, help="seconds per underlying check")
    parser.add_argument("--since-baseline", action="store_true",
                        help="diff-not-state mode: only block issues introduced since the "
                             "captured turn baseline; pre-existing debt -> info. Without this "
                             "flag, report ALL debt (full mode). Activation does NOT depend on "
                             "--session, so the gate still works if the host omits session_id.")
    parser.add_argument("--session", default="",
                        help="turn/session id; refines the baseline state key so parallel "
                             "sessions don't clobber each other. Optional — absent falls back "
                             "to a root-only key (single-session still correct).")
    parser.add_argument("--capture-baseline", action="store_true",
                        help="record turn-start git HEAD and exit (UserPromptSubmit hook)")
    args = parser.parse_args()

    root = find_project_root(Path(args.project))

    if args.capture_baseline:
        capture_baseline(root, args.session or None)
        return 0

    issues = collect_issues(root, args.timeout)

    if args.since_baseline:
        baseline = read_baseline(root, args.session or None)
        touched = touched_paths(root, baseline) if baseline else None
        if baseline and touched is not None:
            issues = apply_diff_downgrade(issues, root, touched)
        # else: fail CLOSED -> full mode, every block still blocks

    if args.format == "tsv":
        emit_tsv(issues)
    else:
        emit_text(root, issues, max(1, args.max_per_severity))
    return 1 if any(issue.severity == "block" for issue in issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
