#!/usr/bin/env python3
"""Read-only watcher for skill upstream records (UPSTREAM.json, schema skill-upstream/v1).

Usage:
  upstream_watch.py --lint                 # offline format check of every UPSTREAM.json
  upstream_watch.py --remote               # ask GitHub (via gh) whether watched upstream paths changed
  upstream_watch.py --remote --json        # same, machine-readable
  upstream_watch.py --remote --report FILE # also write the text/JSON output to FILE

Remote mode prints only paths that really changed and failed checks. It never edits skills.
Schema: share-skill-creator/references/upstream-tracking.md
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

SCHEMA = "skill-upstream/v1"
DEFAULT_ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {"_legacy", "node_modules", ".git", "__pycache__"}
REQUIRED = ("repo", "paths", "absorbed_commit", "absorbed_at", "mode", "local_paths", "watch", "note")
OPTIONAL = ("license",)
MODES = ("vendored", "semantic")
GH_TIMEOUT = 20

REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class GhError(RuntimeError):
    pass


def find_records(root: Path) -> list[Path]:
    found = []
    for path in sorted(root.rglob("UPSTREAM.json")):
        if SKIP_DIRS.intersection(path.relative_to(root).parts):
            continue
        found.append(path)
    return found


def lint_record(path: Path) -> tuple[list[dict], list[str]]:
    """Return (valid sources, errors). A source with any error is not returned."""
    errors: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [], [f"{path}: unreadable JSON: {exc}"]
    if not isinstance(data, dict):
        return [], [f"{path}: top level must be an object"]
    extra_top = set(data) - {"schema", "sources"}
    if extra_top:
        errors.append(f"{path}: unknown top-level keys {sorted(extra_top)}")
    if data.get("schema") != SCHEMA:
        errors.append(f"{path}: schema must be {SCHEMA!r}")
    sources = data.get("sources")
    if not isinstance(sources, list) or not sources:
        return [], errors + [f"{path}: sources must be a non-empty list"]

    base = path.parent
    valid: list[dict] = []
    for i, src in enumerate(sources):
        where = f"{path}: sources[{i}]"
        errs: list[str] = []
        if not isinstance(src, dict):
            errors.append(f"{where}: must be an object")
            continue
        missing = [k for k in REQUIRED if k not in src]
        if missing:
            errs.append(f"{where}: missing keys {missing}")
        unknown = set(src) - set(REQUIRED) - set(OPTIONAL)
        if unknown:
            errs.append(f"{where}: unknown keys {sorted(unknown)}")
        repo = src.get("repo")
        if not isinstance(repo, str) or not REPO_RE.match(repo):
            errs.append(f"{where}: repo must look like owner/name")
        commit = src.get("absorbed_commit")
        if not isinstance(commit, str) or not SHA_RE.match(commit):
            errs.append(f"{where}: absorbed_commit must be a hex commit sha")
        absorbed_at = src.get("absorbed_at")
        if not isinstance(absorbed_at, str) or not DATE_RE.match(absorbed_at):
            errs.append(f"{where}: absorbed_at must be YYYY-MM-DD")
        else:
            try:
                dt.date.fromisoformat(absorbed_at)
            except ValueError:
                errs.append(f"{where}: absorbed_at is not a real date")
        mode = src.get("mode")
        if mode not in MODES:
            errs.append(f"{where}: mode must be one of {MODES}")
        if not isinstance(src.get("watch"), bool):
            errs.append(f"{where}: watch must be true/false")
        if not isinstance(src.get("note"), str):
            errs.append(f"{where}: note must be a string")
        for key in ("paths", "local_paths"):
            val = src.get(key)
            if not isinstance(val, list) or not val or not all(isinstance(v, str) and v for v in val):
                errs.append(f"{where}: {key} must be a non-empty list of strings")
        local_paths = src.get("local_paths") if isinstance(src.get("local_paths"), list) else []
        for lp in local_paths:
            if isinstance(lp, str) and lp and not (base / lp).exists():
                errs.append(f"{where}: local path does not exist: {lp}")
        if mode == "vendored" and isinstance(src.get("paths"), list) and local_paths:
            if len(src["paths"]) != len(local_paths):
                errs.append(f"{where}: vendored needs paths and local_paths paired 1:1")
            for lp in local_paths:
                if isinstance(lp, str) and (base / lp).is_dir():
                    errs.append(f"{where}: vendored local path must be a file: {lp}")
        if errs:
            errors.extend(errs)
        else:
            valid.append(src)
    return valid, errors


def gh_api(endpoint: str, *, raw: bool = False) -> bytes:
    cmd = ["gh", "api", endpoint]
    if raw:
        cmd[2:2] = ["-H", "Accept: application/vnd.github.raw"]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=GH_TIMEOUT, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise GhError(f"timeout after {GH_TIMEOUT}s: gh api {endpoint}")
    except OSError as exc:
        raise GhError(f"cannot run gh: {exc}")
    if proc.returncode != 0:
        msg = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise GhError(f"gh api {endpoint}: {msg[-1] if msg else 'exit ' + str(proc.returncode)}")
    return proc.stdout


def commit_date(repo: str, sha: str) -> str:
    data = json.loads(gh_api(f"repos/{repo}/commits/{sha}"))
    return data["commit"]["committer"]["date"]


def commits_since(repo: str, path: str, since: str) -> list[dict]:
    endpoint = f"repos/{repo}/commits?path={quote(path)}&since={quote(since)}&per_page=100"
    data = json.loads(gh_api(endpoint))
    if not isinstance(data, list):
        raise GhError(f"unexpected commits payload for {repo}:{path}")
    return data


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_source(skill: str, record: Path, src: dict) -> list[dict]:
    """Return findings: kind CHANGED or FAIL. Unchanged paths produce nothing."""
    repo = src["repo"]
    findings: list[dict] = []
    base = {"skill": skill, "record": str(record), "repo": repo, "mode": src["mode"]}
    absorbed = src["absorbed_commit"]
    try:
        since = commit_date(repo, absorbed)
    except (GhError, KeyError, ValueError) as exc:
        return [{**base, "kind": "FAIL", "path": "*", "detail": f"absorbed commit lookup failed: {exc}"}]

    for i, path in enumerate(src["paths"]):
        try:
            commits = commits_since(repo, path, since)
        except (GhError, ValueError) as exc:
            findings.append({**base, "kind": "FAIL", "path": path, "detail": str(exc)})
            continue
        commits = [c for c in commits if not c.get("sha", "").startswith(absorbed)]
        if not commits:
            continue
        latest = commits[0]
        info = {
            "commits": len(commits),
            "latest_sha": latest.get("sha", "")[:12],
            "latest_date": latest.get("commit", {}).get("committer", {}).get("date", ""),
            "latest_message": (latest.get("commit", {}).get("message", "").splitlines() or [""])[0],
        }
        if src["mode"] == "vendored":
            local = record.parent / src["local_paths"][i]
            try:
                upstream = gh_api(f"repos/{repo}/contents/{quote(path)}", raw=True)
            except GhError as exc:
                findings.append({**base, "kind": "FAIL", "path": path, "detail": f"content fetch failed: {exc}", **info})
                continue
            local_sha = sha256(local.read_bytes())
            if sha256(upstream) == local_sha:
                continue  # commits touched it, but the vendored copy already matches upstream
            info["local_path"] = src["local_paths"][i]
            info["detail"] = "upstream content differs from local vendored copy"
        else:
            info["detail"] = "upstream path has commits after absorbed_commit"
        findings.append({**base, "kind": "CHANGED", "path": path, **info})
    return findings


def skill_name(root: Path, record: Path) -> str:
    rel = record.parent.relative_to(root)
    return str(rel) if str(rel) != "." else record.parent.name


def format_text(findings: list[dict], lint_errors: list[str], summary: dict) -> str:
    lines = [f"LINT  {e}" for e in lint_errors]
    for f in findings:
        if f["kind"] == "CHANGED":
            extra = f" local={f['local_path']}" if f.get("local_path") else ""
            lines.append(
                f"CHANGED  {f['skill']}  {f['repo']}:{f['path']}  [{f['mode']}]  "
                f"{f['commits']} commit(s), latest {f['latest_sha']} {f['latest_date']} "
                f"\"{f['latest_message']}\"{extra}"
            )
        else:
            lines.append(f"FAIL  {f['skill']}  {f['repo']}:{f['path']}  {f['detail']}")
    lines.append(
        f"# {summary['checked_at']} records={summary['records']} watched_sources={summary['watched_sources']} "
        f"changed={summary['changed']} failed={summary['failed']} lint_errors={summary['lint_errors']}"
    )
    return "\n".join(lines) + "\n"


def run(root: Path, remote: bool) -> tuple[list[dict], list[str], dict]:
    records = find_records(root)
    lint_errors: list[str] = []
    findings: list[dict] = []
    watched = 0
    for record in records:
        sources, errors = lint_record(record)
        lint_errors.extend(errors)
        if not remote:
            continue
        for src in sources:
            if not src["watch"]:
                continue
            watched += 1
            findings.extend(check_source(skill_name(root, record), record, src))
    summary = {
        "checked_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "root": str(root),
        "records": len(records),
        "watched_sources": watched,
        "changed": sum(f["kind"] == "CHANGED" for f in findings),
        "failed": sum(f["kind"] == "FAIL" for f in findings),
        "lint_errors": len(lint_errors),
    }
    return findings, lint_errors, summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--lint", action="store_true", help="offline format check only")
    mode.add_argument("--remote", action="store_true", help="query GitHub for upstream changes (read-only)")
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="skills root (default: shared skills dir)")
    ap.add_argument("--json", action="store_true", help="print JSON instead of text")
    ap.add_argument("--report", type=Path, help="also write the output to this file")
    args = ap.parse_args(argv)

    root = args.root.expanduser().resolve()
    findings, lint_errors, summary = run(root, remote=args.remote)
    if args.json:
        out = json.dumps({"summary": summary, "lint_errors": lint_errors, "findings": findings},
                         ensure_ascii=False, indent=2) + "\n"
    else:
        out = format_text(findings, lint_errors, summary)
    sys.stdout.write(out)
    if args.report:
        args.report.expanduser().parent.mkdir(parents=True, exist_ok=True)
        args.report.expanduser().write_text(out, encoding="utf-8")
    return 1 if lint_errors or summary["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
