#!/usr/bin/env python3
"""Git tracking triage: which dirty/untracked paths belong in Git, which do not.

One rule: what people write (authored) goes into Git regardless of its value;
what machines compute (generated) stays out, only its recipe (script + config +
data-registry entry) is tracked; environments, caches and credentials never go
in. Entering Git is not the same as promotion into the main pipeline.

`scan()` classifies `git status` entries plus tracked files that belong to the
ignore classes. It only reads; the one write is `write_gitignore()`, which
merges suggested patterns into a marked block at the end of the root
.gitignore. Nothing here runs `git add`, `commit` or `rm`.
"""

from __future__ import annotations

import fnmatch
import os
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

SCHEMA_VERSION = "sixone-track/v1"
GIT_TIMEOUT = 60
MB = 1024 * 1024
LARGE_MB_DEFAULT = 10
TEXT_REVIEW_BYTES = 1 * MB
GROUP_LIMIT = 20
SAMPLE_LIMIT = 3
BLOCK_BEGIN = "# >>> top track (auto) >>>"
BLOCK_END = "# <<< top track <<<"

CREDENTIAL_SUFFIXES = (".pem", ".key")
CREDENTIAL_PREFIXES = ("id_rsa", "id_ed25519")
CACHE_SEGMENTS = frozenset({
    ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".ipynb_checkpoints", ".julia_depot", ".serena", ".cache", ".gradle", ".next", ".nuxt", ".tox",
    ".eggs", ".playwright-cli", ".codegraph", ".worktrees", ".DS_Store", "Thumbs.db",
    ".packages", "site-packages",                                   # third-party libs vendored into the repo
})
CACHE_SUFFIXES = (".egg-info", "-cache", "_cache", ".cache")   # fulltext-cache, hf_cache, x.cache
CACHE_EXTS = frozenset({"pyc", "pyo"})
TEMP_TOP_DIRS = frozenset({"_tmp", "tmp", "dist", "build", "coverage", "htmlcov"})
TEMP_ANY_DIR = "_artifacts"
DIR_NOTE_NAMES = frozenset({"_readme.md", "readme.md", "readme", ".gitkeep", ".keep"})
TOP_DIRS = frozenset({"_wiki-methodology", "wiki-methodology"})
TOP_ROOT_FILES = frozenset({"AGENTS.md", "CLAUDE.md", "_codemap.md"})
TOP_ANY_FILES = frozenset({".gitignore", ".gitattributes"})
META_EXTS = frozenset({"yml", "yaml", "md"})
AUTHORED_EXTS = frozenset(
    "py ipynb r jl m js mjs cjs ts tsx jsx vue svelte css scss less html htm sh bash zsh ps1 bat sql "
    "c cc cpp cxx h hpp rs go java kt scala swift lua pl rb php toml yaml yml ini cfg conf md markdown "
    "rst tex bib sty cls bst txt json jsonc xml cmake mk".split())
AUTHORED_NAMES = frozenset({"makefile", "dockerfile", "justfile", "procfile", "license", "readme", ".env.example"})
BINARY_EXTS = frozenset(
    "pt pth ckpt safetensors onnx h5 hdf5 joblib pkl pickle npy npz parquet feather arrow nc zarr tif tiff "
    "las segy sgy mat db sqlite sqlite3 zip 7z tar gz tgz bz2 xz rar mp4 webm mov avi mkv wav mp3 flac".split())
FIGURE_EXTS = frozenset("png jpg jpeg svg pdf gif eps webp".split())
TABLE_EXTS = frozenset("csv tsv xlsx xls".split())
PAPER_SEGMENTS = frozenset({"_paper", "paper", "paper_draft", "manuscript", "_figures", "figures"})
# Generated zone: files below these directories come from runs; the extension is only a proxy.
GENERATED_SEGMENTS = frozenset({
    "_outputs", "outputs", "output", "results", "runs", "_runs", "_data", "data", "logs", "wandb",
    "mlruns", "lightning_logs", "checkpoints",
})
CODE_EXTS = frozenset(
    "py ipynb r jl m sh bash zsh ps1 bat js mjs cjs ts tsx jsx vue svelte c cc cpp cxx h hpp rs go java kt "
    "scala swift lua pl rb php sql".split())
CODE_NAMES = frozenset({"makefile", "dockerfile", "justfile", "procfile"})
WORD_EXT = re.compile(r"[a-z][a-z0-9]{0,9}")   # extensions worth an extension-level pattern
COLLAPSE_MIN = 5          # clean bulk subdirectories of one parent before `/<parent>/*/` + exceptions
LEGACY_DIR = "_legacy"
# Only media / binaries / logs / traces under `_artifacts/` are throw-away evidence; notes and scripts there are written.
ARTIFACT_TEMP_EXTS = frozenset(
    "png jpg jpeg gif webp webm mp4 mov zip har trace log txt".split()) | BINARY_EXTS
RECIPE_WORDS = ("recipe", "prompt", "config", "spec", "manifest", "schema", "template")
ROOT_FILE_PATTERNS = tuple(p.lower() for p in (
    "AGENTS.md", "CLAUDE.md", "README*", "LICENSE*", "CHANGELOG*", "CONTRIBUTING*", "_codemap.md",
    ".gitignore", ".gitattributes", ".editorconfig", ".env.example", ".pre-commit-config.yaml",
    "pyproject.toml", "setup.py", "setup.cfg", "requirements*.txt", "environment.yml", "uv.lock",
    "poetry.lock", "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "tsconfig*.json",
    "Makefile", "Justfile", "Dockerfile", "docker-compose*.yml", "Cargo.toml", "Cargo.lock", "go.mod",
    "go.sum", "codegraph.json", "*.code-workspace"))
README_NAMES = frozenset({"readme.md", "readme", "_readme.md"})
EXCEPT_MAX = 5            # kept direct children re-included by `!` before a directory rule gives up
BULK_UNTRACKED_MAX = 200  # more untracked commit-class files than this per two-level dir looks generated/downloaded
BULK_MIN = 50            # untracked generated text/images per two-level dir at or above which it is bulk
TRACKED_IGNORE_REASONS = ("cache", "credential", "temp")


class TrackError(RuntimeError):
    pass


def _git(repo: Path, *args: str) -> bytes:
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    try:
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                                timeout=GIT_TIMEOUT, env=env)
    except subprocess.TimeoutExpired as exc:
        raise TrackError(f"git {args[0]} 超时（>{GIT_TIMEOUT}s）") from exc
    except OSError as exc:
        raise TrackError(f"git {args[0]} 无法运行: {exc}") from exc
    if result.returncode != 0:
        raise TrackError(f"git {args[0]} 失败: {result.stderr.decode(errors='replace').strip()[:300]}")
    return result.stdout


def _ext(name: str) -> str:
    dot = name.rfind(".")
    return name[dot + 1:].lower() if dot > 0 else ""


def _ignore_rule(parts: list[str]) -> tuple[str, str | None] | None:
    """Rules 1-3 (credential / env-cache / temp): (reason, anchor) or None.

    `anchor` is the repo-relative directory (or file) that the rule matched on
    when the rule is about a whole directory, else None.
    """
    name = parts[-1]
    if (name == ".env" or (name.startswith(".env.") and name != ".env.example")
            or name.endswith(CREDENTIAL_SUFFIXES) or name.startswith(CREDENTIAL_PREFIXES)
            or name == "credentials.json"):
        return "credential", None
    for index, part in enumerate(parts):
        if part in CACHE_SEGMENTS or part.endswith(CACHE_SUFFIXES) or part == "cache":
            return "cache", "/".join(parts[:index + 1])
    if _ext(name) in CACHE_EXTS:
        return "cache", None
    if name.lower() in DIR_NOTE_NAMES:
        return None                   # `_tmp/_readme.md`, `.gitkeep`: documents/keeps the temp dir
    if len(parts) > 1 and parts[0] in TEMP_TOP_DIRS:
        return "temp", parts[0]
    if _ext(name) in ARTIFACT_TEMP_EXTS:
        for index, part in enumerate(parts[:-1]):
            if part == TEMP_ANY_DIR:
                return "temp", "/".join(parts[:index + 1])
    return None


def classify(rel: str, size: Callable[[], int | None] | None = None,
             large_bytes: int = LARGE_MB_DEFAULT * MB) -> tuple[str, str, str | None]:
    """(action, reason, anchor) for one repo-relative path; action is commit / ignore / review.

    Judged by origin; the extension is only a proxy. Order: credential > cache > temp >
    non-text over the large limit > TOP records > generated zone > extension.
    `size` is called only when the decision depends on the file size (lazy stat).
    A path ending in "/" is a directory git status could not descend into (nested repo).
    Generated-zone text/images come back as review/generated-summary; `resolve_bulk`
    turns them into ignore/generated-bulk when a two-level directory holds many of them.
    """
    is_dir = rel.endswith("/")
    parts = [p for p in rel.split("/") if p]
    if not parts:
        return "review", "other", None
    hit = _ignore_rule(parts)
    if hit:
        return "ignore", hit[0], hit[1]
    name, dirs = parts[-1], parts[:-1]
    top_record = (bool(TOP_DIRS.intersection(dirs)) or name in TOP_ANY_FILES
                  or (len(parts) == 1 and name in TOP_ROOT_FILES)
                  or (len(parts) == 2 and parts[0] == "_meta" and _ext(name) in META_EXTS))
    if not top_record and LEGACY_DIR in dirs and name.lower() not in DIR_NOTE_NAMES:   # _legacy/_readme.md is a dir note
        return "review", "legacy", None
    if TEMP_ANY_DIR in dirs and name.lower() not in DIR_NOTE_NAMES:
        return "review", "artifact-note", None            # written note/script next to test evidence
    if is_dir:
        return ("commit", "top-record", None) if top_record else ("review", "nested-repo", None)
    ext = _ext(name)
    authored = ext in AUTHORED_EXTS or name.lower() in AUTHORED_NAMES
    binary = ext in BINARY_EXTS
    fixture = binary and "fixtures" in dirs
    if binary and not fixture and not top_record:
        return "ignore", "generated-binary", None       # size does not change the answer
    nbytes = (size() if size else None) or 0
    if not authored and nbytes > large_bytes:
        return "ignore", "large", None
    if top_record:
        if authored and nbytes > TEXT_REVIEW_BYTES:
            return "review", "large-text", None
        return "commit", "top-record", None
    if fixture:
        return "review", "fixture", None
    if GENERATED_SEGMENTS.intersection(dirs):
        if ext in CODE_EXTS or name.lower() in CODE_NAMES:
            return "review", "generated-code", None       # a real script or a snapshot copy
        stem = name.rsplit(".", 1)[0].lower() if "." in name[1:] else name.lower()
        if any(word in stem for word in RECIPE_WORDS):
            return "review", "recipe-like", None          # a written input (recipe, prompt, config…)
        return "review", "generated-summary", None
    if authored:
        return ("review", "large-text", None) if nbytes > TEXT_REVIEW_BYTES else ("commit", "authored", None)
    if ext in FIGURE_EXTS:
        if PAPER_SEGMENTS.intersection(dirs):
            return "commit", "paper-figure", None
        return "review", "figure", None
    if ext in TABLE_EXTS:
        return "review", "table", None
    return "review", "other", None


def resolve_bulk(items: list[list]) -> None:
    """In place, per two-level directory: untracked generated-summary items -> ignore/generated-bulk
    when >= BULK_MIN of them; untracked commit-class items (the TOP directory and project files aside)
    -> review/bulk-untracked when > BULK_UNTRACKED_MAX of them. Items are [path, action, reason, anchor, tracked]."""
    counts: dict[str, int] = {}
    for rel, _, reason, _, tracked in items:
        if reason == "generated-summary" and not tracked:
            key = _group_dir(rel)
            counts[key] = counts.get(key, 0) + 1
    for item in items:
        if item[2] == "generated-summary" and not item[4] and counts[_group_dir(item[0])] >= BULK_MIN:
            item[1], item[2] = "ignore", "generated-bulk"
    # People do not write hundreds of files at once: that many untracked "authored" files in one
    # two-level directory were generated or downloaded. Only the TOP directory (plan, logs, findings,
    # decisions) and root project files are exempt; a wiki or test tree with thousands of fresh files
    # is as suspect as any other directory.
    authored: dict[str, int] = {}
    for rel, action, _, _, tracked in items:
        if action == "commit" and not tracked and not _is_top_core(rel):
            key = _group_dir(rel)
            authored[key] = authored.get(key, 0) + 1
    for item in items:
        if (item[1] == "commit" and not item[4] and not _is_top_core(item[0])
                and authored[_group_dir(item[0])] > BULK_UNTRACKED_MAX):
            item[1], item[2] = "review", "bulk-untracked"


def _is_top_core(rel: str) -> bool:
    """The TOP directory itself (`<wiki-methodology>/_top/...`) or a root/meta project file."""
    parts = rel.split("/")
    if len(parts) == 1:
        return parts[0] in TOP_ROOT_FILES or parts[0] in TOP_ANY_FILES
    if parts[0] == "_meta" or parts[-1] in TOP_ANY_FILES:
        return True
    return any(parts[i] in TOP_DIRS and parts[i + 1] in {"_top", "top"} for i in range(len(parts) - 1))


def large_bytes_for(repo: Path) -> int:
    """`git config top.trackLargeMB` (default 10) in bytes."""
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    try:
        out = subprocess.run(["git", "-C", str(repo), "config", "--get", "top.trackLargeMB"],
                             capture_output=True, text=True, timeout=10, env=env).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        out = ""
    try:
        value = float(out) if out else LARGE_MB_DEFAULT
    except ValueError:
        raise TrackError(f"git config top.trackLargeMB={out!r} 不是数字") from None
    if value <= 0:
        raise TrackError(f"git config top.trackLargeMB={out!r} 必须为正数")
    return int(value * MB)


def _sizer(repo: Path, rel: str) -> Callable[[], int | None]:
    def size() -> int | None:
        try:
            return os.lstat(repo / rel).st_size
        except OSError:          # deleted in the worktree
            return None
    return size


def classify_paths(repo: Path, paths: list[str], large: int | None = None) -> list[tuple[str, str, str]]:
    """[(path, action, reason)] for repo-relative paths (used by plan complete).

    `large` defaults to the repository's `top.trackLargeMB` (TrackError when it is invalid).
    """
    large = large_bytes_for(repo) if large is None else large
    items = [[p, *classify(p, _sizer(repo, p), large), False] for p in paths]
    resolve_bulk(items)
    return [(p, action, reason) for p, action, reason, _, _ in items]


def _status_entries(repo: Path) -> list[tuple[str, str]]:
    """[(XY, path)] from porcelain v1 -z; rename/copy records keep the new path."""
    raw = _git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    fields = raw.decode("utf-8", errors="surrogateescape").split("\0")
    entries, index = [], 0
    while index < len(fields):
        field = fields[index]
        index += 1
        if len(field) < 4:
            continue
        code, path = field[:2], field[3:]
        if "R" in code or "C" in code:
            index += 1                               # skip the original path
        entries.append((code, path))
    return entries


def _tracked_paths(repo: Path) -> list[str]:
    raw = _git(repo, "ls-files", "-z")
    return [p for p in raw.decode("utf-8", errors="surrogateescape").split("\0") if p]


def _parent(rel: str) -> str:
    return rel.rstrip("/").rpartition("/")[0]


def _top_dirs(rel: str) -> tuple[str, str]:
    """(first-level dir, first-two-level dir) of the file's parent; "" at the root."""
    parts = _parent(rel).split("/") if _parent(rel) else []
    return "/".join(parts[:1]), "/".join(parts[:2])


def _group_dir(rel: str) -> str:
    return _top_dirs(rel)[1] or "."


def _escape(path: str) -> str:
    """Literal path -> gitignore pattern text."""
    escaped = re.sub(r"([*?\[\\])", r"\\\1", path)
    if escaped.endswith(" "):
        escaped = escaped[:-1] + "\\ "
    return escaped


def _anchor_pattern(reason: str, anchor: str, rel: str) -> str:
    last = anchor.rsplit("/", 1)[-1]
    if reason == "cache":
        if last.endswith(".egg-info"):
            return "*.egg-info/"
        if anchor != rel.rstrip("/") and last not in CACHE_SEGMENTS:
            return f"/{_escape(anchor)}/"                 # name-derived caches: only this directory
        return last if anchor == rel.rstrip("/") else f"{last}/"   # .DS_Store is a file
    return f"/{_escape(anchor)}/"


def _suggestions(untracked: list[tuple[str, str, str, str | None]], tracked_ok: list[str]) -> list[dict[str, Any]]:
    """Ignore patterns for untracked ignore-class files, never hiding a file that is not ignore-class.

    Whole-directory rules (`/<dir>/`, `/<dir>/*/`, `/<top>/**/<name>/`) only where no kept file
    (tracked, commit- or review-class) sits below, or `/<dir>/*` + `!` for a few kept direct children.
    Rule/directory anchored (cache, temp) -> that directory; credentials -> exact path.
    Generated bulk: its two-level directory unless that holds kept files,
    else `/<dir>/**/*.<ext>`, else the shallowest deeper directory free of such files, else
    the exact path. Otherwise, looking only at the first two directory levels: the second-level
    directory when nothing below it is tracked or non-ignore; else `/<dir>/**/*.<ext>`
    at the shallowest level where no tracked or non-ignore file has that extension;
    else the exact path.
    """
    # "kept" = tracked, commit-class or review-class: a whole-directory rule must hide none of them
    kept_dirs: set[str] = set()               # dirs (any depth) holding kept files
    kept_deep: set[str] = set()               # dirs holding kept files below a subdirectory
    kept_direct: dict[str, list[str]] = {}    # dir -> kept files directly inside it
    kept_ext: set[tuple[str, str]] = set()    # (dir at any depth, ext) of kept files
    mixed_ext: set[tuple[str, str]] = set()   # (dir, ext) pairs with such files; "" = root
    direct_ext: set[tuple[str, str]] = set()  # (parent dir, ext) of such files, direct children only
    kept_named: dict[tuple[str, str], set[str]] = {}  # (top dir, zone name) -> such dirs above kept files
    keep = [rel for rel, action, _, _ in untracked if action != "ignore"] + tracked_ok
    for rel in keep:
        d1, d2 = _top_dirs(rel)
        ext = _ext(rel.rstrip("/").rsplit("/", 1)[-1])
        parent = _parent(rel)
        kept_direct.setdefault(parent, []).append(rel.rstrip("/"))
        first = True
        while parent:
            kept_dirs.add(parent)
            kept_ext.add((parent, ext))
            if not first:
                kept_deep.add(parent)
            first = False
            parent = _parent(parent)
        mixed_ext.update(((d1, ext), (d2, ext), ("", ext)))
        direct_ext.add((_parent(rel), ext))
        parent = _parent(rel)
        while "/" in parent:
            name = parent.rsplit("/", 1)[1]
            if name in GENERATED_SEGMENTS:
                kept_named.setdefault((d1, name), set()).add(parent)
            parent = _parent(parent)
    patterns: dict[str, dict[str, Any]] = {}

    def add(pattern: str, reason: str) -> None:
        slot = patterns.setdefault(pattern, {"pattern": pattern, "count": 0, "reasons": {}})
        slot["count"] += 1
        slot["reasons"][reason] = slot["reasons"].get(reason, 0) + 1

    def whole_dir(directory: str, reason: str, notes_only: bool = False) -> bool:
        """`/<dir>/` when nothing kept is below; with `notes_only` (temp dirs holding e.g. a tracked
        `_readme.md`) also `/<dir>/*` + `!` for a few kept direct children. False when neither is safe."""
        if directory not in kept_dirs:
            add(f"/{_escape(directory)}/", reason)
            return True
        kept = kept_direct.get(directory, [])
        if not notes_only or directory in kept_deep or not kept or len(kept) > EXCEPT_MAX:
            return False
        pattern = f"/{_escape(directory)}/*"
        add(pattern, reason)
        patterns[pattern]["except"] = [f"!/{_escape(k)}" for k in sorted(kept)]
        return True

    bulk_dirs: dict[str, int] = {}
    for rel, action, reason, anchor in untracked:
        if action != "ignore":
            continue
        ext = _ext(rel.rstrip("/").rsplit("/", 1)[-1])
        if anchor:
            if reason == "cache" or anchor not in kept_dirs:
                add(_anchor_pattern(reason, anchor, rel), reason)
            elif not whole_dir(anchor, reason, notes_only=True):
                add(f"/{_escape(anchor)}/**/*.{ext}" if WORD_EXT.fullmatch(ext) and (anchor, ext) not in kept_ext
                    else f"/{_escape(rel)}", reason)
            continue
        d1, d2 = _top_dirs(rel)
        parent = _parent(rel)
        exact = f"/{_escape(rel.rstrip('/'))}"
        direct = exact
        if parent and WORD_EXT.fullmatch(ext) and (parent, ext) not in direct_ext:
            direct = f"/{_escape(parent)}/*.{ext}"     # bulk: direct children only; still hides nothing kept
        if reason == "cache" and ext in CACHE_EXTS:
            add(f"*.{ext}", reason)
        elif reason == "credential":
            add(exact, reason)
        elif "/" in d2 and whole_dir(d2, reason):
            pass
        elif reason == "generated-bulk":
            # never widen bulk past its own two-level directory (smaller summaries may sit next to it)
            if WORD_EXT.fullmatch(ext) and (d2, ext) not in mixed_ext:   # not `.1`, `.144830` suffixes
                add(f"/{_escape(d2)}/**/*.{ext}", reason)
            else:                          # deepest-first is too fine: take the first clean subdirectory
                parts = parent.split("/")
                clean = next(("/".join(parts[:k]) for k in range(3, len(parts) + 1)
                              if "/".join(parts[:k]) not in kept_dirs), None)
                if clean:
                    bulk_dirs[clean] = bulk_dirs.get(clean, 0) + 1
                else:
                    add(direct, reason)
        elif ext and (d1, ext) not in mixed_ext:
            add(f"/{_escape(d1)}/**/*.{ext}" if d1 else f"/*.{ext}", reason)
        elif ext and d2 != d1 and (d2, ext) not in mixed_ext:
            add(f"/{_escape(d2)}/**/*.{ext}", reason)
        else:
            add(exact, reason)
    _collapse_bulk_dirs(bulk_dirs, kept_dirs, kept_named, add, patterns)
    return sorted(patterns.values(), key=lambda s: (-s["count"], s["pattern"]))


def _collapse_bulk_dirs(bulk_dirs: dict[str, int], kept_dirs: set[str], kept_named: dict[tuple[str, str], set[str]],
                        add: Callable[[str, str], None], patterns: dict[str, dict[str, Any]]) -> None:
    """Merge clean bulk subdirectories into fewer patterns without hiding anything kept.

    1. Same generated-zone name under one top dir (e.g. many `runs/` in `_sandbox`) ->
       `/<top>/**/<name>/` plus `!/<dir>/` for each same-named directory holding kept files.
    2. Many clean children of one parent -> `/<parent>/*/` plus `!/<parent>/<kept>/` for
       every child that holds tracked, commit- or review-class files.
    """
    by_name: dict[tuple[str, str], list[str]] = {}
    for clean in bulk_dirs:
        name = clean.rsplit("/", 1)[-1]
        if name in GENERATED_SEGMENTS:
            by_name.setdefault((clean.split("/", 1)[0], name), []).append(clean)
    merged: set[str] = set()
    for (top, name), dirs in by_name.items():
        kept = sorted(kept_named.get((top, name), set()) - set(dirs))
        if len(dirs) >= COLLAPSE_MIN and len(kept) < len(dirs):
            pattern = f"/{_escape(top)}/**/{_escape(name)}/"
            for clean in dirs:
                for _ in range(bulk_dirs[clean]):
                    add(pattern, "generated-bulk")
            patterns[pattern]["except"] = [f"!/{_escape(d)}/" for d in kept]
            merged.update(dirs)
    by_parent: dict[str, list[str]] = {}
    for clean in bulk_dirs:
        if clean not in merged:
            by_parent.setdefault(_parent(clean), []).append(clean)
    kept_children: dict[str, list[str]] = {}
    for directory in kept_dirs:
        kept_children.setdefault(_parent(directory), []).append(directory)
    for parent, children in by_parent.items():
        kept = sorted(kept_children.get(parent, []))
        if len(children) >= COLLAPSE_MIN and len(kept) < len(children):
            pattern = f"/{_escape(parent)}/*/"
            for child in children:
                for _ in range(bulk_dirs[child]):
                    add(pattern, "generated-bulk")
            patterns[pattern]["except"] = [f"!/{_escape(child)}/" for child in kept]
        else:
            for child in children:
                for _ in range(bulk_dirs[child]):
                    add(f"/{_escape(child)}/", "generated-bulk")


def _groups(items: list[tuple[str, str, bool]]) -> tuple[list[dict[str, Any]], int]:
    buckets: dict[str, dict[str, Any]] = {}
    for rel, reason, tracked in items:
        key = _group_dir(rel)
        slot = buckets.setdefault(key, {"dir": key, "count": 0, "tracked": 0, "reasons": {}, "sample": []})
        slot["count"] += 1
        slot["tracked"] += int(tracked)
        slot["reasons"][reason] = slot["reasons"].get(reason, 0) + 1
        if len(slot["sample"]) < SAMPLE_LIMIT:
            slot["sample"].append(rel)
    ordered = sorted(buckets.values(), key=lambda g: (-g["count"], g["dir"]))
    return ordered[:GROUP_LIMIT], max(0, len(ordered) - GROUP_LIMIT)


def _tracked_should_ignore(tracked: list[str]) -> tuple[list[dict[str, Any]], int, set[str]]:
    buckets: dict[str, dict[str, Any]] = {}
    total = 0
    bad: set[str] = set()
    for rel in tracked:
        hit = _ignore_rule([p for p in rel.split("/") if p])
        if not hit or hit[0] not in TRACKED_IGNORE_REASONS:
            continue
        reason, anchor = hit
        total += 1
        bad.add(rel)
        key = anchor or rel
        slot = buckets.setdefault(key, {"path": key, "count": 0, "reason": reason, "sample": []})
        slot["count"] += 1
        if len(slot["sample"]) < SAMPLE_LIMIT:
            slot["sample"].append(rel)
    ordered = sorted(buckets.values(), key=lambda g: (-g["count"], g["path"]))
    for slot in ordered:
        slot["command"] = f"git rm -r --cached -- {shlex.quote(slot['path'])}"
        if slot["reason"] == "credential":
            slot["note"] = "凭证已进 Git 历史：rm --cached 不清历史，需轮换该密钥"
    return ordered[:GROUP_LIMIT], total, bad


def _root_whitelisted(name: str) -> bool:
    return any(fnmatch.fnmatchcase(name.lower(), pat) for pat in ROOT_FILE_PATTERNS)


def _ignored_dirs(root: Path, dirs: list[str]) -> set[str]:
    """Top-level dirs that .gitignore ignores as a whole (e.g. `/_tmp/`); their README cannot be tracked."""
    if not dirs:
        return set()
    try:
        result = subprocess.run(["git", "-C", str(root), "check-ignore", "--no-index", "--stdin", "-z"],
                                input="\0".join(f"{d}/" for d in dirs).encode() + b"\0", capture_output=True,
                                timeout=GIT_TIMEOUT, env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"))
    except subprocess.TimeoutExpired as exc:
        raise TrackError(f"git check-ignore 超时（>{GIT_TIMEOUT}s）") from exc
    if result.returncode not in (0, 1):                  # 1 = nothing ignored
        raise TrackError(f"git check-ignore 失败: {result.stderr.decode(errors='replace').strip()[:300]}")
    return {p.rstrip("/") for p in result.stdout.decode("utf-8", errors="surrogateescape").split("\0") if p}


def _structure(root: Path, tracked: list[str], entries: list[tuple[str, str]]) -> dict[str, Any]:
    """Read-only layout check from the ls-files/status lists already in hand.

    Archived area = a top-level dir that starts with `_` or carries a README. `unarchived` counts
    untracked, not-ignored files outside it: root files beyond the usual project files, and files in
    plain top-level dirs without a README. Hidden dirs (`.github/` …) are config, not content.
    """
    deleted = {rel for code, rel in entries if "D" in code}
    untracked = [rel for code, rel in entries if code == "??"]
    files = [rel for rel in tracked if rel not in deleted] + untracked
    loose, dirs_with_files, readme_dirs = [], set(), set()
    for rel in files:
        parts = rel.rstrip("/").split("/")
        if len(parts) == 1:
            if not rel.endswith("/") and not _root_whitelisted(rel):
                loose.append(rel)
            continue
        top = parts[0]
        if top.startswith("."):
            continue
        dirs_with_files.add(top)
        if len(parts) == 2 and not rel.endswith("/") and parts[1].lower() in README_NAMES:
            readme_dirs.add(top)
    candidates = sorted(dirs_with_files - readme_dirs - TOP_DIRS)   # TOP's own tree is documented by share-top
    ignored = _ignored_dirs(root, candidates)
    missing = [d for d in candidates if d not in ignored]
    unarchived = []
    for rel in untracked:
        parts = rel.rstrip("/").split("/")
        if len(parts) == 1:
            if not _root_whitelisted(parts[0]):
                unarchived.append(rel)
        elif not parts[0].startswith(("_", ".")) and parts[0] not in readme_dirs:
            unarchived.append(rel)
    loose.sort()
    unarchived.sort()
    return {"root_loose": {"count": len(loose), "sample": loose[:10]},
            "dirs_without_readme": {"count": len(missing), "dirs": missing[:20]},
            "unarchived": {"count": len(unarchived), "sample": unarchived[:10]},
            "note": "只读；已归档区 = `_` 开头或带 README 的顶层目录；README 按五问写（模板 templates/dir-readme.md）"}


def _hint(counts: dict[str, int], untracked_commit: int, tracked_commit: int, rules: int) -> str:
    parts = []
    if untracked_commit:
        parts.append(f"{untracked_commit} 份写出来的文件没进 Git：补进任务 scope 或单独提交")
    if tracked_commit:
        parts.append(f"{tracked_commit} 份已追踪文件有改动待提交")
    untracked_ignore = counts["ignore_untracked"]
    if untracked_ignore:
        parts.append(f"{untracked_ignore} 个生成物/缓存（归并为 {rules} 条规则）可用 --write-gitignore 加忽略")
    if counts["review"]:
        notes = []
        if counts.get("generated_summary"):
            notes.append(f"{counts['generated_summary']} 条是生成区汇总（每目录 <{BULK_MIN}，汇总层可追踪）")
        if counts.get("bulk_untracked"):
            notes.append(f"{counts['bulk_untracked']} 条成批未追踪（单个目录 >{BULK_UNTRACKED_MAX}，数量像生成或下载的，"
                         "按来源判断，确认是生成物再加忽略）")
        if counts.get("legacy"):
            notes.append(f"{counts['legacy']} 条在 _legacy/（按项目 legacy 约定：归档时已追踪的保持追踪，"
                         "新放入的旧物确认来源后再定）")
        extra = "；其中 " + "，".join(notes) if notes else ""
        parts.append(f"{counts['review']} 条需人工判断（小结果表/图/fixture/大文本/生成区脚本{extra}）")
    if counts["tracked_should_ignore"]:
        parts.append(f"{counts['tracked_should_ignore']} 个已追踪文件属于缓存/临时/凭证：按 tracked_should_ignore "
                     "的命令 git rm -r --cached（只建议，未执行）")
    return "；".join(parts) if parts else "工作区干净，没有需要分拣的文件"


def scan(repo: str | Path) -> dict[str, Any]:
    started = time.monotonic()
    base = {"schema_version": SCHEMA_VERSION, "tool": "track"}
    try:
        top_raw = _git(Path(repo), "rev-parse", "--show-toplevel")
        root = Path(top_raw.decode().strip())
        large = large_bytes_for(root)
        entries = _status_entries(root)
        tracked = _tracked_paths(root)
        structure = _structure(root, tracked, entries)
    except TrackError as exc:
        return {**base, "verdict": "error", "repo": str(repo), "error": str(exc),
                "next_hint": "确认路径是 Git 仓库；超时说明仓库过大或磁盘慢，可先 .gitignore 掉明显的缓存目录后重试"}
    tsi_groups, tsi_total, tracked_bad = _tracked_should_ignore(tracked)
    items = [[rel, *classify(rel, _sizer(root, rel), large), code != "??"] for code, rel in entries]
    resolve_bulk(items)
    classified: dict[str, list[tuple[str, str, bool]]] = {"commit": [], "ignore": [], "review": []}
    untracked: list[tuple[str, str, str, str | None]] = []
    for rel, action, reason, anchor, is_tracked in items:
        classified[action].append((rel, reason, is_tracked))
        if not is_tracked:
            untracked.append((rel, action, reason, anchor))
    suggestions = _suggestions(untracked, [rel for rel in tracked if rel not in tracked_bad])
    counts = {key: len(items) for key, items in classified.items()}
    counts["tracked_should_ignore"] = tsi_total
    counts["ignore_untracked"] = sum(1 for _, action, _, _ in untracked if action == "ignore")
    for key, reason_name in (("generated_summary", "generated-summary"), ("bulk_untracked", "bulk-untracked"),
                             ("legacy", "legacy")):
        counts[key] = sum(1 for _, reason, _ in classified["review"] if reason == reason_name)
    untracked_commit = sum(1 for _, action, _, _ in untracked if action == "commit")
    tracked_commit = sum(1 for _, _, t in classified["commit"] if t)
    groups, truncated = {}, {}
    for key, items in classified.items():
        groups[key], more = _groups(items)
        if more:
            truncated[key] = more
    busy = any(counts[k] for k in ("commit", "ignore", "review", "tracked_should_ignore"))
    result: dict[str, Any] = {
        **base, "verdict": "warn" if busy else "ok", "repo": str(root),
        "counts": counts, "untracked_commit": untracked_commit, "tracked_commit": tracked_commit,
        "groups": groups, "gitignore_suggestions": suggestions,
        "tracked_should_ignore": tsi_groups,
        "large_mb": round(large / MB, 3),
        "next_hint": _hint(counts, untracked_commit, tracked_commit, len(suggestions)),
        "structure": structure,
        "elapsed_s": round(time.monotonic() - started, 2),
        "note": "只读分拣；不 git add/commit/rm。进 Git ≠ 转正式（接入正式入口 + 登记 + plan complete）。",
    }
    loose, missing = structure["root_loose"]["count"], structure["dirs_without_readme"]["count"]
    if loose or missing:
        result["next_hint"] += f"；根目录散落 {loose} 个文件、{missing} 个顶层目录缺 README"
    if structure["unarchived"]["count"]:
        result["next_hint"] += f"；未归档 {structure['unarchived']['count']} 个文件（不在 `_` 目录或带 README 的目录里）"
    if truncated:
        result["groups_truncated"] = truncated
    return result


def write_gitignore(repo: str | Path, patterns: list[str]) -> dict[str, Any]:
    """Merge `patterns` into the marked auto block of <repo>/.gitignore (idempotent, block-local)."""
    path = Path(repo) / ".gitignore"
    text = path.read_bytes().decode("utf-8") if path.is_file() else ""
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    begin = lines.index(BLOCK_BEGIN) if BLOCK_BEGIN in lines else None
    end = None
    if begin is not None:
        end = next((i for i in range(begin + 1, len(lines)) if lines[i] == BLOCK_END), None)
        if end is None:
            raise TrackError(f"{path} 有 '{BLOCK_BEGIN}' 却缺结束标记 '{BLOCK_END}'，请手工修好再写")
    existing = lines[begin + 1:end] if begin is not None else []
    new = [p for p in dict.fromkeys(patterns) if p not in existing]
    if not new:
        return {"path": str(path), "written": [], "changed": False}
    block = [BLOCK_BEGIN, *existing, *new, BLOCK_END]
    if begin is None:
        prefix = lines + ([""] if lines and lines[-1].strip() else [])
        out = prefix + block
    else:
        out = lines[:begin] + block + lines[end + 1:]
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(newline.join(out) + newline)
    return {"path": str(path), "written": new, "changed": True}


def track(repo: str | Path, *, write: bool = False) -> dict[str, Any]:
    result = scan(repo)
    if write and result.get("verdict") != "error":
        try:
            result["gitignore_write"] = write_gitignore(
                result["repo"], [line for s in result["gitignore_suggestions"]
                                 for line in (s["pattern"], *s.get("except", []))])
        except (TrackError, OSError) as exc:
            result["verdict"] = "error"
            result["error"] = f"写 .gitignore 失败: {exc}"
    return result


def render_markdown(result: dict[str, Any]) -> str:
    if result.get("verdict") == "error":
        return f"# Git 追踪分拣：失败\n\n- 仓库：`{result.get('repo')}`\n- 原因：{result.get('error')}\n"
    c = result["counts"]
    out = [f"# Git 追踪分拣：`{result['repo']}`", "",
           f"verdict={result['verdict']} · 耗时 {result['elapsed_s']}s · 大文件阈值 {result['large_mb']}MB", "",
           "| 类 | 数量 |", "|---|---|",
           f"| commit（写出来的，应进 Git） | {c['commit']}（未追踪 {result['untracked_commit']}，已追踪待提交 {result['tracked_commit']}） |",
           f"| ignore（生成物/缓存/凭证） | {c['ignore']}（未追踪 {c['ignore_untracked']}） |",
           f"| review（需人工判断） | {c['review']}（生成区汇总 {c.get('generated_summary', 0)}，"
           f"成批未追踪 {c.get('bulk_untracked', 0)}，legacy {c.get('legacy', 0)}） |",
           f"| 已追踪但应忽略 | {c['tracked_should_ignore']} |", ""]
    titles = {"commit": "应进 Git", "ignore": "应忽略", "review": "需人工判断"}
    for key, title in titles.items():
        groups = result["groups"][key]
        if not groups:
            continue
        out += [f"## {title}（按前两级目录，前 10 组）", ""]
        for g in groups[:10]:
            reasons = ", ".join(f"{r}={n}" for r, n in sorted(g["reasons"].items(), key=lambda x: -x[1]))
            tracked = f"，已追踪 {g['tracked']}" if g["tracked"] else ""
            out.append(f"- `{g['dir']}` {g['count']}{tracked}（{reasons}）例：" + "、".join(f"`{s}`" for s in g["sample"]))
        out.append("")
    if result["gitignore_suggestions"]:
        out += ["## .gitignore 建议（--write-gitignore 写入标记块）", "", "```gitignore"]
        for s in result["gitignore_suggestions"][:30]:
            out.append(s["pattern"] + f"    # {s['count']}")
            out += s.get("except", [])
        out += ["```", ""]
        if len(result["gitignore_suggestions"]) > 30:
            out += [f"……另 {len(result['gitignore_suggestions']) - 30} 条见 JSON", ""]
    if result["tracked_should_ignore"]:
        out += ["## 已追踪但应忽略（只建议，未执行）", ""]
        for g in result["tracked_should_ignore"][:10]:
            note = f" — {g['note']}" if g.get("note") else ""
            out.append(f"- `{g['path']}` {g['count']} 个（{g['reason']}）：`{g['command']}`{note}")
        out.append("")
    if result.get("gitignore_write"):
        w = result["gitignore_write"]
        out += [f"已写入 {w['path']}：{len(w['written'])} 行", ""]
    st = result.get("structure")
    if st:
        out += ["## 目录结构", "",
                f"- 根目录散落文件：{st['root_loose']['count']}"
                + ("（例：" + "、".join(f"`{x}`" for x in st["root_loose"]["sample"]) + "）"
                   if st["root_loose"]["sample"] else ""),
                f"- 缺 README 的顶层目录：{st['dirs_without_readme']['count']}"
                + ("（" + "、".join(f"`{x}/`" for x in st["dirs_without_readme"]["dirs"]) + "）"
                   if st["dirs_without_readme"]["dirs"] else ""),
                f"- 未归档 {st['unarchived']['count']} 个文件（不在 `_` 目录或带 README 的目录里）"
                + ("（例：" + "、".join(f"`{x}`" for x in st["unarchived"]["sample"]) + "）"
                   if st["unarchived"]["sample"] else ""), ""]
    out += [f"**下一步**：{result['next_hint']}", ""]
    return "\n".join(out)
