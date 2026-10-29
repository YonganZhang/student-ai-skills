#!/usr/bin/env python3
"""Git linkage for TOP tasks, used by top_plan.py.

One rule keeps plan and Git from forming two ledgers:
- The plan (`_task_plan.md` + `_logs/`) lives only in the main worktree and is
  never branched; plan commands run from a task worktree still write there.
- Code for a task either goes straight onto the main line, or into its own
  branch `task/<ID>` checked out at `<main>/.worktrees/<ID>`. Branch and worktree are derived from the task ID, so
  the plan stores no branch field.
- Commits made by the CLI carry a `Task: <ID>` trailer (plus `Decision:` /
  `Handoff:` when given); the global hooks in `git-hooks/` add `Task:` to
  ordinary commits made while a task is in progress.

Nothing here pushes, force-removes, rebases or resets. Failures come back as
dicts with an `error`, never as a half-done silent success.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

BRANCH_PREFIX = "task/"
WORKTREE_DIR = ".worktrees"
TIMEOUT = 60


def git(cwd: Path, *args: str, timeout: int = TIMEOUT) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                          timeout=timeout, env=env)


def _out(cwd: Path, *args: str) -> str | None:
    try:
        result = git(cwd, *args, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def toplevel(path: Path) -> Path | None:
    top = _out(path, "rev-parse", "--show-toplevel")
    return Path(top) if top else None


def main_worktree(path: Path) -> Path | None:
    """Root of the main worktree of the repository containing `path`."""
    listing = _out(path, "worktree", "list", "--porcelain")
    if not listing:
        return None
    first = listing.splitlines()[0]
    return Path(first[len("worktree "):]) if first.startswith("worktree ") else None


def task_branch(item_id: str) -> str:
    return BRANCH_PREFIX + item_id


def current_branch(checkout: Path) -> str | None:
    return _out(checkout, "symbolic-ref", "--quiet", "--short", "HEAD")


def branch_exists(repo: Path, name: str) -> bool:
    return _out(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}") is not None


def worktrees(repo: Path) -> list[dict[str, str]]:
    entries, entry = [], {}
    for line in (_out(repo, "worktree", "list", "--porcelain") or "").splitlines():
        if not line:
            if entry:
                entries.append(entry)
            entry = {}
            continue
        key, _, value = line.partition(" ")
        entry[key] = value
    if entry:
        entries.append(entry)
    return entries


def task_checkout(repo: Path, item_id: str) -> Path | None:
    """Worktree that has `task/<ID>` checked out, if any."""
    ref = f"refs/heads/{task_branch(item_id)}"
    for entry in worktrees(repo):
        if entry.get("branch") == ref:
            return Path(entry["worktree"])
    return None


def ahead_behind(repo: Path, base: str, branch: str) -> tuple[int, int] | None:
    counts = _out(repo, "rev-list", "--left-right", "--count", f"{base}...{branch}")
    if not counts:
        return None
    behind, ahead = (int(x) for x in counts.split())
    return ahead, behind


def is_merged(repo: Path, branch: str, into: str = "HEAD") -> bool:
    try:
        return git(repo, "merge-base", "--is-ancestor", branch, into, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _exclude_worktree_dir(main: Path) -> None:
    common = _out(main, "rev-parse", "--git-common-dir")
    if not common:
        return
    exclude = (main / common if not Path(common).is_absolute() else Path(common)) / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    text = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
    if f"/{WORKTREE_DIR}/" not in text.splitlines():
        exclude.write_text(text + ("" if text.endswith("\n") or not text else "\n") + f"/{WORKTREE_DIR}/\n",
                           encoding="utf-8")


def start_task_worktree(main: Path, item_id: str) -> dict[str, Any]:
    """Check out `task/<ID>` (created from the main worktree's HEAD) at `.worktrees/<ID>`."""
    branch = task_branch(item_id)
    existing = task_checkout(main, item_id)
    if existing:
        return {"branch": branch, "checkout": str(existing), "created": False}
    path = main / WORKTREE_DIR / item_id
    _exclude_worktree_dir(main)
    args = (["worktree", "add", str(path), branch] if branch_exists(main, branch)
            else ["worktree", "add", "-b", branch, str(path), "HEAD"])
    result = git(main, *args)
    if result.returncode != 0:
        return {"branch": branch, "error": result.stderr.strip() or result.stdout.strip()}
    return {"branch": branch, "checkout": str(path), "created": True}


def changed_paths(checkout: Path, pathspecs: list[str], untracked: str = "all") -> list[str]:
    """Dirty or untracked files under the pathspecs (deletions included)."""
    if not pathspecs:
        return []
    try:  # raw stdout: porcelain entries start with a status column that may be a space
        result = git(checkout, "status", "--porcelain", "-z", f"--untracked-files={untracked}", "--", *pathspecs)
    except (OSError, subprocess.SubprocessError):
        return []
    out = result.stdout if result.returncode == 0 else ""
    paths, entries, index = [], out.split("\0"), 0
    while index < len(entries):
        entry = entries[index]
        if len(entry) > 3:
            paths.append(entry[3:])
            if entry[0] in "RC":
                index += 1
        index += 1
    return paths


def dirty_paths(checkout: Path, untracked: str = "all") -> list[str]:
    return changed_paths(checkout, ["."], untracked)


def commit_paths(checkout: Path, paths: list[str], item_id: str | None, subject: str,
                 trailers: list[tuple[str, str]] | None = None) -> dict[str, Any]:
    """Commit exactly `paths` (other staged changes stay staged), with `Task:` (+ extra) trailers."""
    if not paths:
        return {"skipped": "no changed files in scope"}
    added = git(checkout, "add", "--all", "--", *paths)
    if added.returncode != 0:
        return {"error": added.stderr.strip() or added.stdout.strip(), "paths": paths}
    lines = ([f"Task: {item_id}"] if item_id else []) + [f"{key}: {value}" for key, value in trailers or []]
    message = f"{subject}\n\n" + "\n".join(lines) + "\n"
    result = git(checkout, "commit", "--quiet", "-m", message, "--", *paths, timeout=300)
    if result.returncode != 0:
        tail = "\n".join((result.stdout + result.stderr).strip().splitlines()[-8:])
        return {"error": f"git commit failed: {tail}", "paths": paths}
    sha = _out(checkout, "rev-parse", "--short", "HEAD")
    return {"commit": sha, "paths": paths, "checkout": str(checkout)}


def merge_task(main: Path, item_id: str, title: str) -> dict[str, Any]:
    """Merge `task/<ID>` into the main worktree's branch, then remove its worktree and branch.

    Fast-forward when possible, otherwise a merge commit. A conflicted merge is
    aborted and reported; nothing is forced.
    """
    branch = task_branch(item_id)
    if not branch_exists(main, branch):
        return {"skipped": f"no branch {branch}"}
    base = current_branch(main)
    if not base:
        return {"error": "main worktree is on a detached HEAD; check out the main branch first"}
    if base == branch:
        return {"error": f"main worktree has {branch} checked out; switch back to the main branch first"}
    checkout = task_checkout(main, item_id)
    if checkout and checkout != main and dirty_paths(checkout):
        return {"error": f"task worktree has uncommitted changes: {checkout}"}
    result: dict[str, Any] = {"branch": branch, "into": base}
    if is_merged(main, branch):
        result["merge"] = "already merged"
    else:
        ff = git(main, "merge", "--ff-only", "--quiet", branch)
        if ff.returncode == 0:
            result["merge"] = "fast-forward"
        else:
            message = f"Merge {branch}: {title}\n\nTask: {item_id}\n"
            merged = git(main, "merge", "--no-ff", "--no-edit", "-m", message, branch, timeout=300)
            if merged.returncode != 0:
                conflicts = (_out(main, "diff", "--name-only", "--diff-filter=U") or "").splitlines()
                git(main, "merge", "--abort")
                return {**result, "error": "merge conflict; merge aborted, nothing changed",
                        "conflicts": conflicts[:20]}
            result["merge"] = "merge commit"
        result["commit"] = _out(main, "rev-parse", "--short", "HEAD")
    if checkout and checkout != main:
        removed = git(main, "worktree", "remove", str(checkout))
        result["worktree_removed"] = removed.returncode == 0
        if removed.returncode != 0:
            result["worktree_note"] = removed.stderr.strip()
    deleted = git(main, "branch", "-d", branch)
    result["branch_deleted"] = deleted.returncode == 0
    if deleted.returncode != 0:
        result["branch_note"] = deleted.stderr.strip()
    return result


def last_commit_touching(repo: Path, paths: list[str]) -> str | None:
    return _out(repo, "log", "-1", "--format=%H", "--", *paths) or None


def commits_since(repo: Path, commit: str) -> int | None:
    count = _out(repo, "rev-list", "--count", f"{commit}..HEAD")
    return int(count) if count and count.isdigit() else None


# ---------- trailers: Git as the backbone of the plan ----------

TRAILER_KEYS = ("Task", "Decision", "Handoff")
_FIELD, _RECORD, _MULTI = "\x1f", "\x1e", "\x1d"


def log_trailers(repo: Path, *, rev: str | None = None, grep: str | None = None,
                 paths: list[str] | None = None, limit: int = 20, timeout: float = 5) -> list[dict[str, Any]] | None:
    """Commits (newest first) with their Task/Decision/Handoff trailers; None when git fails.

    `grep` is an extended regex applied line-wise to the message (`^Task: P1\\.2$`);
    callers still check the parsed trailers, since --grep also matches body text.
    """
    trailer_fmt = "".join(f"%x1f%(trailers:key={key},valueonly,separator=%x1d)" for key in TRAILER_KEYS)
    args = ["log", f"-n{limit}", f"--format=%h%x1f%H%x1f%ct%x1f%s{trailer_fmt}%x1e"]
    if grep:
        args += ["-E", f"--grep={grep}"]
    if rev:
        args.append(rev)
    if paths:
        args += ["--", *paths]
    try:
        result = git(repo, *args, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    commits = []
    for record in result.stdout.split(_RECORD):
        fields = record.strip("\n").split(_FIELD)
        if len(fields) != 4 + len(TRAILER_KEYS):
            continue
        short, full, ctime, subject, *values = fields
        entry: dict[str, Any] = {"commit": short, "sha": full, "time": int(ctime) if ctime.isdigit() else 0,
                                 "subject": subject}
        for key, value in zip(TRAILER_KEYS, values):
            entry[key.lower()] = [v.strip() for v in value.split(_MULTI) if v.strip()]
        commits.append(entry)
    return commits


def clean_head_commit(repo: Path, rel_path: str) -> str | None:
    """Short SHA of the last commit touching `rel_path` when the file is tracked and unchanged since."""
    if _out(repo, "ls-files", "--error-unmatch", "--", rel_path) is None:
        return None
    status = _out(repo, "status", "--porcelain", "--", rel_path)
    if status is None or status:
        return None
    return _out(repo, "log", "-1", "--format=%h", "--", rel_path) or None


def create_tag(repo: Path, name: str, message: str) -> dict[str, Any]:
    """Annotated tag at HEAD; never moves or overwrites an existing tag."""
    if _out(repo, "check-ref-format", f"refs/tags/{name}") is None:
        return {"error": f"invalid tag name: {name}"}
    if _out(repo, "rev-parse", "--verify", "--quiet", f"refs/tags/{name}") is not None:
        return {"error": f"tag already exists: {name} (tags are never moved)"}
    head = _out(repo, "rev-parse", "--short", "HEAD")
    if not head:
        return {"error": "no commit to tag"}
    result = git(repo, "tag", "-a", name, "-m", message)
    if result.returncode != 0:
        return {"error": result.stderr.strip() or result.stdout.strip()}
    return {"tag": name, "commit": head}
