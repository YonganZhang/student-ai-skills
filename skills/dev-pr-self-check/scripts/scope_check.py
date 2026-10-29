#!/usr/bin/env python3
"""Pre-PR scope check: summarize the committed diff against a base and flag things that must not ship.

Run from the root of the repository you are about to open a PR for:
  python3 <skill-dir>/scripts/scope_check.py --base origin/main [--head HEAD] [--json] [--allow-dirty]

Scope: commits in merge-base(base, head)..head only. Uncommitted, staged and untracked changes are
not scanned; a dirty work tree is a precondition failure unless --allow-dirty is given.
Secret detection is a heuristic over added lines, not a full secret scanner: 0 blockers does not
prove the diff is free of credentials. Renames are treated as delete + add (--no-renames).
Exit codes: 0 no blockers in the declared scope, 1 blockers found, 2 usage, git or precondition error.
Warnings never change the exit code. Read-only: runs git rev-parse/status/diff/cat-file only.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

SECRET_PATTERNS = [
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b")),
    ("OpenAI/Anthropic style key", re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("Slack token", re.compile(r"\bxox[abpr]-[A-Za-z0-9-]{10,}\b")),
]
ASSIGNED_SECRET = re.compile(
    r"""(?ix)["']?\b(?:password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token)\b
        ["']?\s*[:=]\s*["'](?P<value>[^"'\s]{8,})["']""")
PLACEHOLDER = re.compile(r"(?i)^(?:change[_-]?me|replace[_-]?me|your[_-].*|x{8,}|\*{8,}|<.*>|\$\{.*\}|example.*|dummy.*)$")
BLOCKED_FILES = re.compile(r"(?i)^(\.env(\.[^/]*)?|id_rsa|id_ed25519|.*\.pem|.*\.p12|.*\.key|credentials\.json)$")
ALLOWED_ENV = re.compile(r"(?i)^\.env\.(example|sample|template)$")
HIGH_RISK_FILES = re.compile(
    r"(?i)^(\.gitlab-ci\.yml|Jenkinsfile|Dockerfile[^/]*|CODEOWNERS|(deploy|release)[^/]*\.(sh|py|ya?ml|js|ts|mjs))$")
HIGH_RISK_DIRS = re.compile(r"(?i)^(\.github|deploy|release|migrations?)$")
HIGH_RISK_WORDS = re.compile(r"(?i)(auth|permission|rbac|secret|credential|billing|payment)")
BIG_FILE_BYTES = 5 * 1024 * 1024
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


class CheckError(Exception):
    pass


def git(*args: str) -> str:
    try:
        out = subprocess.run(["git", *args], capture_output=True)
    except OSError as e:
        raise CheckError(f"cannot run git: {e}") from e
    if out.returncode != 0:
        msg = out.stderr.decode("utf-8", "replace").strip()
        raise CheckError(msg or f"git {args[0]} failed")
    return out.stdout.decode("utf-8", "surrogateescape")


def high_risk(path: str) -> bool:
    *dirs, name = path.split("/")
    return bool(HIGH_RISK_FILES.match(name) or any(HIGH_RISK_DIRS.match(d) for d in dirs)
                or any(HIGH_RISK_WORDS.search(seg) for seg in path.split("/")))


def resolve(ref: str) -> str:
    return git("rev-parse", "--verify", "--end-of-options", ref + "^{commit}").strip()


def scan_added_lines(rng: str, path: str):
    """Yield (line_no, label, is_placeholder) for suspicious added lines of one file."""
    patch = git("--literal-pathspecs", "diff", "--no-renames", "--no-ext-diff", "--no-textconv",
                "--src-prefix=a/", "--dst-prefix=b/", "-U0", "--no-color", rng, "--", path)
    line_no, in_hunk = 0, False
    for line in patch.splitlines():
        m = HUNK.match(line)
        if m:
            line_no, in_hunk = int(m.group(1)), True
        elif in_hunk and line.startswith("+"):
            text, seen = line[1:], set()
            for label, pat in SECRET_PATTERNS:
                if pat.search(text) and label not in seen:
                    seen.add(label)
                    yield line_no, label, False
            values = [m2.group("value") for m2 in ASSIGNED_SECRET.finditer(text)]
            if values:  # one finding per line; any real-looking value makes it a blocker
                yield line_no, "assigned secret", all(PLACEHOLDER.match(v) for v in values)
            line_no += 1
        elif in_hunk and line.startswith(" "):
            line_no += 1


def analyze(base: str, head: str, max_lines: int, allow_dirty: bool) -> dict:
    base_sha, head_sha = resolve(base), resolve(head)
    try:
        merge_base = git("merge-base", base_sha, head_sha).strip()
    except CheckError as e:
        raise CheckError(f"{base} and {head} have no common ancestor") from e
    dirty = bool(git("status", "--porcelain=v1", "-z", "--untracked-files=all"))
    if dirty and not allow_dirty:
        raise CheckError("work tree has uncommitted or untracked changes; this check covers commits only. "
                         "Commit the changes that belong to the PR, or rerun with --allow-dirty "
                         "(uncommitted changes stay unchecked). Do not stash or delete other people's work.")
    rng = f"{merge_base}..{head_sha}"
    files = []
    for record in git("diff", "--no-renames", "--numstat", "-z", rng, "--").split("\0"):
        if not record:
            continue
        add, rem, path = record.split("\t", 2)
        files.append({"path": path, "added": None if add == "-" else int(add),
                      "removed": None if rem == "-" else int(rem), "binary": add == "-"})
    # --raw -z: ":<old mode> <new mode> <old sha> <new sha> <status>\0<path>\0"
    tokens = git("diff", "--no-renames", "--raw", "-z", rng, "--").split("\0")
    if tokens and tokens[-1] == "":
        tokens.pop()
    status, new_mode = {}, {}
    for meta, path in zip(tokens[0::2], tokens[1::2]):
        fields = meta.lstrip(":").split()
        new_mode[path], status[path] = fields[1], fields[4]

    blockers, warnings = [], []
    for f in files:
        p = f["path"]
        name = p.rsplit("/", 1)[-1]
        deleted = status.get(p, "M").startswith("D")
        if high_risk(p):
            warnings.append({"path": p, "reason": "high-risk path" + (" deleted" if deleted else "")
                             + ": mark the PR high risk"})
        if deleted:
            continue
        if new_mode.get(p) == "160000":  # submodule pointer: its commits live in another repository
            warnings.append({"path": p, "reason": "submodule pointer changed; its commits were not scanned"})
            continue
        if BLOCKED_FILES.match(name) and not ALLOWED_ENV.match(name):
            blockers.append({"path": p, "reason": "credential or env file must not be committed"})
        size = int(git("cat-file", "-s", f"{head_sha}:{p}").strip())
        if size > BIG_FILE_BYTES:
            blockers.append({"path": p, "reason": f"file is {size / 1024 / 1024:.1f} MiB; use LFS or a release asset"})
        elif f["binary"]:
            warnings.append({"path": p, "reason": "binary file: confirm it belongs in Git"})
        if f["binary"]:
            continue
        for line_no, label, placeholder in scan_added_lines(rng, p):
            item = {"path": p, "line": line_no}
            if placeholder:
                warnings.append({**item, "reason": "placeholder value in a secret-like assignment"})
            else:
                blockers.append({**item, "reason": f"possible {label} in added line"})
    total = sum((f["added"] or 0) + (f["removed"] or 0) for f in files)
    if total > max_lines:
        warnings.append({"path": "*", "reason": f"{total} changed lines > {max_lines}: consider splitting"})
    return {"base": base, "head": head, "base_sha": base_sha, "head_sha": head_sha, "merge_base": merge_base,
            "scope": "committed-only", "dirty": dirty, "files": len(files),
            "added": sum(f["added"] or 0 for f in files), "removed": sum(f["removed"] or 0 for f in files),
            "blockers": blockers, "warnings": warnings, "changed": [f["path"] for f in files],
            "not_checked": ["uncommitted, staged and untracked changes", "ignored files",
                            "secrets that do not match the heuristics"]}


def shown(path: str) -> str:
    """Printable path: escape tabs/newlines and undecodable bytes, keep CJK readable."""
    safe = path.encode("utf-8", "surrogateescape").decode("utf-8", "backslashreplace")
    return json.dumps(safe, ensure_ascii=False)[1:-1]


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--base", required=True, help="PR target branch, e.g. origin/main or upstream/master")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--max-lines", type=int, default=800, help="warn when added+removed exceeds this")
    ap.add_argument("--allow-dirty", action="store_true", help="continue with a dirty work tree (still committed-only)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    a = ap.parse_args()
    if a.max_lines < 0:
        ap.error("--max-lines must be >= 0")
    try:
        r = analyze(a.base, a.head, a.max_lines, a.allow_dirty)
    except CheckError as e:
        if a.json:
            print(json.dumps({"error": str(e)}, ensure_ascii=True))
        print(f"error: {e}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(r, ensure_ascii=True, indent=2))  # ASCII keeps undecodable path bytes valid JSON
    else:
        print(f"scope: {r['files']} files +{r['added']}/-{r['removed']} "
              f"({r['merge_base'][:10]}..{r['head_sha'][:10]}, committed only)")
        if r["dirty"]:
            print("WARNING: work tree is dirty; uncommitted changes were not checked")
        print(f"blockers: {len(r['blockers'])}  warnings: {len(r['warnings'])}")
        for k in ("blockers", "warnings"):
            for item in r[k]:
                loc = shown(item["path"]) + (f":{item['line']}" if "line" in item else "")
                print(f"  [{k[:-1]}] {loc}: {item['reason']}")
        print("changed files:")
        for p in r["changed"]:
            print(f"  {shown(p)}")
        print("Heuristic check only: 0 blockers does not prove there are no secrets.")
    return 1 if r["blockers"] else 0


if __name__ == "__main__":
    sys.exit(main())
