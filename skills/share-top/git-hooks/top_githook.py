#!/usr/bin/env python3
"""TOP extras for the global git hooks (called by _chain.sh after the repo's own hook).

prepare-commit-msg <msgfile> [<source> [<sha>]]
    Add `Task: <ID>` when the commit belongs to a TOP task and the message has no
    Task trailer yet. The task comes from the branch name `task/<ID>` (task
    worktrees) or, in the main worktree only, from the single in_progress task of
    the plan at the repository root. Skipped for merge/squash/amend/-c/-C sources
    and while a rebase, cherry-pick, revert or merge is in progress.
    Also add `Session: <provider>:<id>` naming the AI conversation that made the
    commit (Claude CLAUDE_CODE_SESSION_ID, Codex CODEX_THREAD_ID, else the tmux
    pane stamp), in TOP projects and repos with `git config top.sessionTrailer
    true`; never when it is `false` (set that in public repositories).
commit-msg <msgfile>
    If the edited message holds nothing but Task trailers (the user emptied the
    editor to abort), remove them so git still aborts on an empty message.
pre-commit
    Block a commit that stages a file over `top.maxFileMB` (default 50 MB) or adds
    a line that looks like a live credential (API keys, tokens, private keys).
    Override for one commit: TOP_ALLOW_LARGE=1 / TOP_ALLOW_SECRETS=1.

Fail-open: any problem prints one `[top-hooks]` line to stderr and exits 0.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
PLAN_CANDIDATES = (Path("_wiki-methodology/_top/_task_plan.md"), Path("wiki-methodology/top/task_plan.md"))
# outline/legacy steps (P3.2, P3.2a) and question-and-answer attempts (Q4.3)
TASK_ID_RE = re.compile(r"^(?:P\d+(?:\.[A-Za-z0-9]+)+|Q\d+\.\d+)$")
TASK_TRAILER_RE = re.compile(r"^task\s*:", re.I)
SESSION_TRAILER_RE = re.compile(r"^session\s*:", re.I)
SESSION_ID_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z-]{7,80}$")
SECRET_PATTERNS = (
    ("OpenAI/Anthropic 风格 API key", re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{32,}")),
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}|\bgithub_pat_[A-Za-z0-9_]{40,}")),
    ("Slack token", re.compile(r"\bxox[baprs]-[0-9]{6,}-[0-9A-Za-z-]{10,}")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("私钥", re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA |PGP )?PRIVATE KEY-----")),
)
SCAN_LIMIT_BYTES = 20 * 1024 * 1024
FOUND_EXIT = 3  # the only exit code _chain.sh treats as "block"; crashes (1) fail open
SKIP_SOURCES = {"merge", "squash", "commit"}
IN_PROGRESS_STATE = ("rebase-merge", "rebase-apply", "CHERRY_PICK_HEAD", "REVERT_HEAD", "MERGE_HEAD")


def git(*args: str) -> str | None:
    try:
        result = subprocess.run(["git", *args], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def comment_char() -> str:
    value = git("config", "core.commentChar") or "#"
    return "#" if value == "auto" or len(value) != 1 else value


def content_lines(text: str, comment: str) -> list[str]:
    """Message lines git keeps: no comments, nothing below the scissors line."""
    kept = []
    for line in text.splitlines():
        if line.startswith(f"{comment} ------------------------ >8"):
            break
        if not line.startswith(comment):
            kept.append(line)
    return kept


def current_task() -> str | None:
    branch = git("symbolic-ref", "--quiet", "--short", "HEAD") or ""
    if branch.startswith("task/") and TASK_ID_RE.fullmatch(branch[5:]):
        return branch[5:]
    top = git("rev-parse", "--show-toplevel")
    listing = git("worktree", "list", "--porcelain") or ""
    main = listing.splitlines()[0][len("worktree "):] if listing.startswith("worktree ") else None
    if not top or not main or Path(top).resolve() != Path(main).resolve():
        return None  # linked worktrees only get a Task from their task/<ID> branch
    plan = next((Path(top) / rel for rel in PLAN_CANDIDATES if (Path(top) / rel).is_file()), None)
    if plan is None:
        return None
    sys.path.insert(0, str(SCRIPTS))
    from top_common import parse_plan  # noqa: E402

    active = [item.id for item in parse_plan(plan).items if item.state == "in_progress"]
    return active[0] if len(active) == 1 else None


def current_session() -> str | None:
    """`<provider>:<id>` of the AI conversation running this commit, or None."""
    for provider, name in (("claude", "CLAUDE_CODE_SESSION_ID"), ("codex", "CODEX_THREAD_ID"),
                           ("codex", "CODEX_SESSION_ID")):
        value = os.environ.get(name, "").strip()
        if SESSION_ID_RE.fullmatch(value):
            return f"{provider}:{value}"
    pane = os.environ.get("TMUX_PANE", "").strip()
    if pane:
        try:
            out = subprocess.run(["tmux", "display-message", "-p", "-t", pane, "#{@ai_provider}\t#{@ai_session_id}"],
                                 capture_output=True, text=True, timeout=3).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None
        provider, _, value = out.partition("\t")
        if provider in {"claude", "codex"} and SESSION_ID_RE.fullmatch(value):
            return f"{provider}:{value}"
    return None


def session_trailer_wanted(has_plan: bool) -> bool:
    setting = (git("config", "--bool", "top.sessionTrailer") or "").lower()
    return setting == "true" or (has_plan and setting != "false")


def add_trailer(msgfile: Path, key: str, value: str) -> None:
    result = subprocess.run(["git", "interpret-trailers", "--in-place", "--where", "end",
                             "--if-exists", "doNothing", "--trailer", f"{key}: {value}", str(msgfile)],
                            capture_output=True, text=True, timeout=5)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git interpret-trailers failed")


def prepare(msgfile: Path, source: str) -> None:
    if source in SKIP_SOURCES:
        return
    git_dir = git("rev-parse", "--git-dir")
    if not git_dir or any((Path(git_dir) / name).exists() for name in IN_PROGRESS_STATE):
        return
    top = git("rev-parse", "--show-toplevel") or ""
    has_plan = bool(top) and any((Path(top) / rel).is_file() for rel in PLAN_CANDIDATES)
    task = current_task() if has_plan else None
    session = current_session() if session_trailer_wanted(has_plan) else None
    if not task and not session:
        return
    comment = comment_char()
    text = msgfile.read_text(encoding="utf-8", errors="surrogateescape")
    lines = content_lines(text, comment)
    if session and not any(SESSION_TRAILER_RE.match(line) for line in lines) and any(line.strip() for line in lines):
        add_trailer(msgfile, "Session", session)
    if not task:
        return
    text = msgfile.read_text(encoding="utf-8", errors="surrogateescape")
    comment = comment_char()
    lines = content_lines(text, comment)
    if any(TASK_TRAILER_RE.match(line) for line in lines):
        return
    if not any(line.strip() for line in lines):
        # empty editor message: leave line 1 for the subject and a blank line before the trailer
        rest = text.lstrip("\n")
        msgfile.write_text(f"\n\nTask: {task}\n" + rest, encoding="utf-8", errors="surrogateescape")
        return
    add_trailer(msgfile, "Task", task)


def staged_blobs() -> list[tuple[str, str]]:
    """(blob sha, path) of files added or modified in the index."""
    raw = subprocess.run(["git", "diff", "--cached", "--raw", "-z", "--no-renames", "--diff-filter=AM"],
                         capture_output=True, timeout=20).stdout.split(b"\0")
    pairs = []
    for meta, path in zip(raw[0::2], raw[1::2]):
        fields = meta.decode("utf-8", "replace").split()
        if len(fields) >= 4 and path:
            pairs.append((fields[3], path.decode("utf-8", "surrogateescape")))
    return pairs


def check_staged() -> list[str]:
    problems: list[str] = []
    blobs = staged_blobs()
    if not blobs:
        return problems
    limit_mb = int(git("config", "--int", "top.maxFileMB") or 50)
    if os.environ.get("TOP_ALLOW_LARGE") != "1":
        sizes = subprocess.run(["git", "cat-file", "--batch-check=%(objectname) %(objectsize)"],
                               input="\n".join(sha for sha, _ in blobs) + "\n",
                               capture_output=True, text=True, timeout=20).stdout.split("\n")
        for (sha, path), line in zip(blobs, sizes):
            parts = line.split()
            if len(parts) == 2 and parts[1].isdigit() and int(parts[1]) > limit_mb * 1024 * 1024:
                problems.append(f"大文件 {path}（{int(parts[1]) // (1024 * 1024)} MB > {limit_mb} MB）")
    if os.environ.get("TOP_ALLOW_SECRETS") != "1":
        diff = subprocess.run(["git", "diff", "--cached", "--no-color", "--no-ext-diff", "-U0", "--diff-filter=AM"],
                              capture_output=True, timeout=30).stdout[:SCAN_LIMIT_BYTES].decode("utf-8", "replace")
        path = "?"
        for line in diff.splitlines():
            if line.startswith("+++ "):
                path = line[6:] if line.startswith("+++ b/") else line[4:]
                continue
            if not line.startswith("+"):
                continue
            for label, pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    problems.append(f"疑似{label}：{path}")
                    break
    return list(dict.fromkeys(problems))


def guard_empty(msgfile: Path) -> None:
    text = msgfile.read_text(encoding="utf-8", errors="surrogateescape")
    lines = content_lines(text, comment_char())
    meaningful = [line for line in lines if line.strip()]
    if meaningful and all(TASK_TRAILER_RE.match(line) for line in meaningful):
        kept = [line for line in text.splitlines() if not TASK_TRAILER_RE.match(line)]
        msgfile.write_text("\n".join(kept) + "\n", encoding="utf-8", errors="surrogateescape")


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] == "pre-commit":
        try:
            problems = check_staged()
        except Exception as exc:  # the checker failing must not block
            print(f"[top-hooks] skipped pre-commit check: {exc}", file=sys.stderr)
            return 0
        if problems:
            print("[top-hooks] 提交已拦下：", file=sys.stderr)
            for problem in problems[:20]:
                print(f"  - {problem}", file=sys.stderr)
            print("  确认无误可单次放行：TOP_ALLOW_LARGE=1 / TOP_ALLOW_SECRETS=1 git commit …"
                  "（大文件建议移出仓库或用 git lfs；凭证按凭证 SOP 入总库，不进 git）", file=sys.stderr)
            return FOUND_EXIT
        return 0
    if len(argv) < 3:
        return 0
    hook, msgfile = argv[1], Path(argv[2])
    if hook == "prepare-commit-msg":
        prepare(msgfile, argv[3] if len(argv) > 3 else "")
    elif hook == "commit-msg":
        guard_empty(msgfile)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except Exception as exc:  # fail-open: a TOP extra must never block a commit
        print(f"[top-hooks] skipped {sys.argv[1] if len(sys.argv) > 1 else '?'}: {exc}", file=sys.stderr)
        sys.exit(0)
