#!/usr/bin/env python3
"""Workspace hygiene report: worktrees, branches, stashes and uncommitted work.

Read-only by default. For one repository (default: cwd) or `--all` (every
direct child of ~/projects whose `.git` is a directory; linked worktrees are
reported under their main repository) it lists:

- worktrees: path, branch, HEAD age, clean?, merged into base?, location
  category, and a class SAFE / REVIEW / KEEP;
- local branches: SAFE (merged, not checked out, not current/base/protected),
  REVIEW (unmerged and no commit for 30+ days), KEEP otherwise;
- stashes with age and message;
- uncommitted entries of the main worktree (top-level dirs, untracked files
  larger than 50 MB).

Task branches: a branch named `task/<TASK_ID>` (worktree usually at
`.worktrees/<TASK_ID>` under the main worktree) is matched against the TOP plan
of the main worktree (`_wiki-methodology/_top/_task_plan.md`, read-only via
top_plan.list_items). Plan state overrides the generic rules: pending /
in_progress / blocked -> KEEP; done + merged (+ clean, unoccupied) -> SAFE;
done + unmerged -> REVIEW with a `plan merge` hint; cancelled or an ID missing
from the plan -> REVIEW. Other branches keep the generic rules.

`--apply-safe --yes` removes SAFE worktrees with `git worktree remove` (no
--force) and then deletes branches that are SAFE on a fresh re-scan with
`git branch -d` (never -D). Git itself refuses dirty worktrees and unmerged
branches, so the destructive step stays behind git's own safety checks.

Stdlib plus the sibling top_plan/top_common modules; every git call has a timeout. A timed-out call is reported as
"超时" and the scan continues.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
import top_plan  # noqa: E402
from top_common import ANY_TASK_ID_RE as TASK_ID_RE  # noqa: E402

DAY = 86400
WT_STALE_DAYS = 14
BRANCH_STALE_DAYS = 30
BIG_FILE_BYTES = 50 * 1024 * 1024
PROTECTED = {"main", "master", "develop", "trunk"}
DEFAULT_ROOT = Path.home() / "projects"
TASK_BRANCH_PREFIX = "task/"
TASK_ACTIVE_STATES = {"pending", "in_progress", "blocked"}
PLAN_CANDIDATES = (("_wiki-methodology", "_top", "_task_plan.md"), ("wiki-methodology", "top", "task_plan.md"))


class GitTimeout(Exception):
    pass


def git(cwd, *args, timeout=30):
    """Run git; return (returncode, stdout, stderr). Raise GitTimeout on timeout."""
    try:
        p = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True,
                           text=True, timeout=timeout, stdin=subprocess.DEVNULL,
                           env={**os.environ, "GIT_OPTIONAL_LOCKS": "0", "LC_ALL": "C"})
    except subprocess.TimeoutExpired as e:
        raise GitTimeout(f"git {' '.join(args[:2])} >{timeout}s") from e
    return p.returncode, p.stdout, p.stderr


def git_out(cwd, *args, timeout=30):
    rc, out, _ = git(cwd, *args, timeout=timeout)
    return out if rc == 0 else None


def age_days(ts, now):
    return None if ts is None else round((now - ts) / DAY, 1)


def location_category(path: Path, root: Path) -> str:
    s = str(path)
    if "/.claude/worktrees/" in s:
        return ".claude/worktrees/"
    if "/.worktrees/" in s:
        return ".worktrees/(任务)"
    try:
        path.resolve().relative_to((root / "_worktrees").resolve())
        return "~/projects/_worktrees/"
    except (ValueError, OSError):
        return "其他"


def detect_base(repo):
    """Return (ref, reason). origin/HEAD > main/master > main worktree branch."""
    ref = git_out(repo, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
    if ref and ref.strip():
        return ref.strip(), "origin/HEAD"
    for name in ("main", "master"):
        rc, _, _ = git(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{name}")
        if rc == 0:
            return name, f"本地 {name}"
    cur = git_out(repo, "symbolic-ref", "-q", "--short", "HEAD")
    if cur and cur.strip():
        return cur.strip(), "主 worktree 当前分支"
    return None, "无法判定(游离 HEAD 且无 main/master/origin/HEAD)"


def task_id_of(branch):
    """`task/<TASK_ID>` -> TASK_ID; anything else -> None."""
    if isinstance(branch, str) and branch.startswith(TASK_BRANCH_PREFIX):
        tid = branch[len(TASK_BRANCH_PREFIX):]
        if TASK_ID_RE.fullmatch(tid):
            return tid
    return None


def load_plan_tasks(repo):
    """Return (tasks_by_id, error) from the main worktree's TOP plan (read-only)."""
    repo = Path(repo)
    if not any(repo.joinpath(*parts).is_file() for parts in PLAN_CANDIDATES):
        return None, f"计划文件缺失: {repo.joinpath(*PLAN_CANDIDATES[0])}"
    try:
        data = top_plan.list_items(str(repo))
    except Exception as e:  # reported in the scan result, never swallowed
        return None, f"计划解析失败: {type(e).__name__}: {e}"
    if "error" in data:
        return None, data["error"]
    return {it["id"]: it for it in data["items"]}, None


def task_fields(tid, plan):
    tasks = plan[0] if plan else None
    t = tasks.get(tid) if tid and tasks else None
    return {"task_id": tid, "task_title": t["title"] if t else None,
            "task_state": t["state"] if t else None, "task_reason": None, "action": None}


def merge_hint(repo, tid):
    return (f"python3 {shlex.quote(str(SCRIPTS_DIR / 'sixone-cli.py'))} plan merge "
            f"{shlex.quote(str(repo))} {shlex.quote(tid)}")


def task_verdict(tid, plan, repo, merged):
    """Plan-driven (class, reason, action) for a task branch.

    class "DONE_MERGED" means the task is done and merged; the caller still
    applies its own SAFE preconditions (clean, unoccupied, not current).
    """
    tasks, err = plan if plan else (None, "未加载计划")
    if tasks is None:
        return "REVIEW", f"无法读取计划({err})", None
    t = tasks.get(tid)
    if t is None:
        return "REVIEW", "孤儿任务分支(计划里没有该 ID)", None
    st = t["state"]
    if st in TASK_ACTIVE_STATES:
        return "KEEP", "任务进行中", None
    if st == "cancelled":
        return "REVIEW", "任务已取消，确认是否丢弃分支", None
    if st == "done":
        if merged is None:
            return "REVIEW", "任务已完成但并入状态未知", None
        if not merged:
            return "REVIEW", "任务已完成但分支未并入", merge_hint(repo, tid)
        return "DONE_MERGED", "任务已完成且已合并", None
    return "REVIEW", f"未知计划状态 {st}", None


def parse_worktrees(text):
    items, cur = [], {}
    for line in text.splitlines():
        if not line.strip():
            if cur:
                items.append(cur)
            cur = {}
            continue
        key, _, val = line.partition(" ")
        cur[key] = val if val else True
    if cur:
        items.append(cur)
    return items


def status_entries(path, timeout, untracked="all"):
    """Return list of (xy, path) from porcelain -z, or raise GitTimeout / return None on error."""
    rc, out, _ = git(path, "status", "--porcelain=v1", "-z", f"--untracked-files={untracked}",
                     timeout=timeout)
    if rc != 0:
        return None
    parts, entries, i = out.split("\0"), [], 0
    while i < len(parts):
        rec = parts[i]
        i += 1
        if len(rec) < 4:
            continue
        xy, p = rec[:2], rec[3:]
        if xy[0] in "RC":  # rename/copy: next field is the source path
            i += 1
        entries.append((xy, p))
    return entries


def commit_time(repo, rev):
    out = git_out(repo, "log", "-1", "--format=%ct", rev, "--")
    return int(out.strip()) if out and out.strip() else None


def is_ancestor(repo, rev, base):
    rc, _, _ = git(repo, "merge-base", "--is-ancestor", rev, base, timeout=60)
    return rc == 0


def scan_worktree(repo, wt, idx, base, current, root, now, status_timeout, plan=None):
    path = Path(wt["worktree"])
    branch = wt.get("branch", "")
    branch = branch[len("refs/heads/"):] if isinstance(branch, str) and branch.startswith("refs/heads/") else None
    head = wt.get("HEAD") if isinstance(wt.get("HEAD"), str) else None
    info = {"path": str(path), "branch": branch, "detached": "detached" in wt,
            "main": idx == 0, "location": location_category(path, root),
            "locked": "locked" in wt, "prunable": "prunable" in wt,
            "head_age_days": None, "clean": None, "dirty_count": None,
            "merged": None, "class": "KEEP", "notes": []}
    tid = task_id_of(branch)
    info.update(task_fields(tid, plan))
    try:
        if head:
            info["head_age_days"] = age_days(commit_time(repo, head), now)
        if base and head:
            info["merged"] = is_ancestor(repo, head, base)
    except GitTimeout:
        info["notes"].append("提交年龄/并入判定超时")
    if not path.is_dir():
        info["notes"].append("目录缺失(可 git worktree prune)")
    else:
        try:
            ent = status_entries(path, status_timeout, untracked="normal")
            if ent is None:
                info["notes"].append("git status 失败")
            else:
                info["dirty_count"] = len(ent)
                info["clean"] = not ent
        except GitTimeout:
            info["notes"].append("git status 超时")
    if info["locked"]:
        info["notes"].append("locked")
    # classification
    age = info["head_age_days"]
    blocked = info["clean"] is False or info["clean"] is None or info["locked"] or info["prunable"]
    if info["main"]:
        info["class"] = "KEEP"
    elif tid:
        cls, reason, action = task_verdict(tid, plan, repo, info["merged"])
        if cls == "DONE_MERGED":
            if blocked:
                cls, reason = "REVIEW", "任务已完成且已合并,但 worktree 非 clean/locked/缺失"
            elif branch == current:
                cls, reason = "KEEP", "任务已完成且已合并,但是当前分支"
            else:
                cls = "SAFE"
        info["class"], info["task_reason"], info["action"] = cls, reason, action
        info["notes"].append(reason)
    elif blocked:
        info["class"] = "REVIEW"
    elif info["merged"] and (branch is None or branch != current):
        info["class"] = "SAFE"
    elif not info["merged"] and age is not None and age > WT_STALE_DAYS:
        info["class"] = "REVIEW"
    else:
        info["class"] = "KEEP"
    return info


def scan_repo(repo: Path, root: Path, status_timeout=60, workers=8):
    t0 = time.time()
    now = int(t0)
    r = {"repo": str(repo), "name": repo.name, "base": None, "base_reason": "",
         "current_branch": None, "worktrees": [], "branches": [], "stashes": [],
         "task_summary": {"total": 0, "to_merge": 0, "cleanable": 0},
         "uncommitted": {"count": None, "tracked": None, "untracked": None,
                         "top_dirs": [], "big_untracked": [], "note": ""},
         "errors": [], "elapsed_s": None}
    try:
        base, reason = detect_base(repo)
        r["base"], r["base_reason"] = base, reason
        cur = git_out(repo, "symbolic-ref", "-q", "--short", "HEAD")
        current = cur.strip() if cur and cur.strip() else None
        r["current_branch"] = current

        plan = None  # read the plan only when task branches exist
        task_refs = git_out(repo, "for-each-ref", "--format=%(refname:short)",
                            f"refs/heads/{TASK_BRANCH_PREFIX}") or ""
        if any(task_id_of(n) for n in task_refs.split()):
            plan = load_plan_tasks(repo)
            if plan[0] is None:
                r["errors"].append(f"任务计划: {plan[1]}")

        wts = parse_worktrees(git_out(repo, "worktree", "list", "--porcelain") or "")
        with ThreadPoolExecutor(max_workers=workers) as ex:
            r["worktrees"] = list(ex.map(
                lambda a: scan_worktree(repo, a[1], a[0], base, current, root, now, status_timeout, plan),
                enumerate(wts)))
        occupied = {w["branch"] for w in r["worktrees"] if w["branch"]}

        merged = set()
        if base:
            out = git_out(repo, "for-each-ref", f"--merged={base}", "--format=%(refname:short)",
                          "refs/heads", timeout=60)
            merged = set((out or "").split())
        out = git_out(repo, "for-each-ref", "--format=%(refname:short)%09%(committerdate:unix)",
                      "refs/heads") or ""
        base_local = base.split("/", 1)[1] if base and base.startswith("origin/") else base
        for line in out.splitlines():
            name, _, ts = line.partition("\t")
            age = age_days(int(ts), now) if ts.strip().isdigit() else None
            b = {"name": name, "age_days": age, "merged": name in merged if base else None,
                 "worktree": name in occupied, "class": "KEEP", "notes": []}
            tid = task_id_of(name)
            b.update(task_fields(tid, plan))
            if name == current:
                b["notes"].append("当前分支")
            elif name == base_local or name in PROTECTED:
                b["notes"].append("基准/受保护分支")
            elif tid:
                cls, reason, action = task_verdict(tid, plan, repo, b["merged"])
                if cls == "DONE_MERGED":
                    cls = "KEEP" if b["worktree"] else "SAFE"
                    if b["worktree"]:
                        reason = "任务已完成且已合并,待移除 worktree"
                b["class"], b["task_reason"], b["action"] = cls, reason, action
                b["notes"].append(reason)
            elif b["merged"] and not b["worktree"]:
                b["class"] = "SAFE"
            elif b["merged"] is False and age is not None and age > BRANCH_STALE_DAYS:
                b["class"] = "REVIEW"
            if b["worktree"]:
                b["notes"].append("被 worktree 占用")
            r["branches"].append(b)
        r["task_summary"] = task_summary(r)

        out = git_out(repo, "stash", "list", "--format=%gd%x09%ct%x09%gs") or ""
        for line in out.splitlines():
            ref, _, rest = line.partition("\t")
            ts, _, msg = rest.partition("\t")
            r["stashes"].append({"ref": ref, "age_days": age_days(int(ts), now) if ts.isdigit() else None,
                                 "message": msg})

        u = r["uncommitted"]
        try:  # headline count = `git status --porcelain` entries (untracked dirs collapsed)
            ent = status_entries(repo, status_timeout, untracked="normal")
            if ent is None:
                u["note"] = "git status 失败"
            else:
                u["count"] = len(ent)
                u["untracked"] = sum(1 for xy, _ in ent if xy == "??")
                u["tracked"] = len(ent) - u["untracked"]
                agg = {}
                for _, p in ent:
                    top = p.split("/", 1)[0] + ("/" if "/" in p else "")
                    agg[top] = agg.get(top, 0) + 1
                u["top_dirs"] = sorted(agg.items(), key=lambda kv: -kv[1])[:5]
        except GitTimeout:
            u["note"] = "git status 超时"
        try:  # big single files among untracked (expanded per file)
            rc, out, _ = git(repo, "ls-files", "--others", "--exclude-standard", "-z", timeout=status_timeout)
            if rc == 0:
                files = [p for p in out.split("\0") if p]
                u["untracked_files"] = len(files)
                big = []
                for p in files:
                    try:
                        st = (repo / p).lstat()
                    except OSError:
                        continue
                    if st.st_size > BIG_FILE_BYTES:
                        big.append((p, round(st.st_size / 1048576, 1)))
                u["big_untracked"] = sorted(big, key=lambda x: -x[1])
        except GitTimeout:
            u["note"] = (u["note"] + "; " if u["note"] else "") + "大文件扫描超时"
    except GitTimeout as e:
        r["errors"].append(f"超时: {e}")
    r["elapsed_s"] = round(time.time() - t0, 1)
    return r


def task_summary(r):
    """Task branches: total, done-but-unmerged (to_merge), SAFE branch or worktree (cleanable)."""
    safe_wt = {w["branch"] for w in r["worktrees"] if w["class"] == "SAFE" and w["branch"]}
    tb = [b for b in r["branches"] if b["task_id"]]
    return {"total": len(tb),
            "to_merge": sum(1 for b in tb if b["task_state"] == "done" and b["merged"] is False),
            "cleanable": sum(1 for b in tb if b["class"] == "SAFE" or b["name"] in safe_wt)}


def fmt_tasks(t):
    return f"{t['total']}(待合并 {t['to_merge']},可清理 {t['cleanable']})"


def counts(items):
    c = {"SAFE": 0, "REVIEW": 0, "KEEP": 0}
    for it in items:
        c[it["class"]] += 1
    return c


def fmt_counts(c):
    return f"{c['SAFE']}/{c['REVIEW']}/{c['KEEP']}"


def fmt_age(a):
    return "?" if a is None else f"{a:g}d"


def yn(v):
    return "?" if v is None else ("是" if v else "否")


def render_md(r):
    L = [f"## {r['name']}", "", f"- 路径: `{r['repo']}`",
         f"- 基准分支: `{r['base']}`(依据: {r['base_reason']});当前分支: `{r['current_branch']}`",
         f"- worktree SAFE/REVIEW/KEEP: {fmt_counts(counts(r['worktrees']))};"
         f"分支 SAFE/REVIEW/KEEP: {fmt_counts(counts(r['branches']))};"
         f"stash: {len(r['stashes'])};任务分支 {fmt_tasks(r['task_summary'])};扫描耗时 {r['elapsed_s']}s"]
    for e in r["errors"]:
        L.append(f"- 错误: {e}")
    L += ["", f"### Worktrees ({len(r['worktrees'])})", "",
          "| 分类 | 路径 | 分支 | HEAD 年龄 | clean | 已并入 | 位置 | 备注 |", "|---|---|---|---|---|---|---|---|"]
    order = {"SAFE": 0, "REVIEW": 1, "KEEP": 2}
    for w in sorted(r["worktrees"], key=lambda w: (not w["main"], order[w["class"]], w["path"])):
        clean = "?" if w["clean"] is None else ("是" if w["clean"] else f"否({w['dirty_count']})")
        br = w["branch"] or "(detached)"
        notes = "; ".join((["主 worktree"] if w["main"] else []) + w["notes"])
        L.append(f"| {w['class']} | `{w['path']}` | `{br}` | {fmt_age(w['head_age_days'])} | {clean} | "
                 f"{yn(w['merged'])} | {w['location']} | {notes} |")
    nb = counts(r["branches"])
    L += ["", f"### 分支 ({len(r['branches'])};只列 SAFE/REVIEW,KEEP {nb['KEEP']} 条略)", ""]
    shown = [b for b in r["branches"] if b["class"] != "KEEP"]
    if shown:
        L += ["| 分类 | 分支 | 最近提交 | 已并入 | 备注 |", "|---|---|---|---|---|"]
        for b in sorted(shown, key=lambda b: (order[b["class"]], b["name"])):
            L.append(f"| {b['class']} | `{b['name']}` | {fmt_age(b['age_days'])} | {yn(b['merged'])} | "
                     f"{'; '.join(b['notes'])} |")
    else:
        L.append("(无)")
    tb = [b for b in r["branches"] if b["task_id"]]
    if tb:
        wt_of = {w["branch"]: w for w in r["worktrees"] if w["branch"]}
        L += ["", f"### 任务分支 ({len(tb)})", "",
              "| 分类 | 任务 | 标题 | 计划状态 | 已并入 | worktree | 原因 | 建议动作 |",
              "|---|---|---|---|---|---|---|---|"]
        for b in sorted(tb, key=lambda b: (order[b["class"]], b["name"])):
            w = wt_of.get(b["name"])
            wcell = f"`{w['path']}` ({w['class']})" if w else "-"
            act = f"`{b['action']}`" if b["action"] else "-"
            L.append(f"| {b['class']} | `{b['task_id']}` | {b['task_title'] or '-'} | {b['task_state'] or '-'} | "
                     f"{yn(b['merged'])} | {wcell} | {b['task_reason'] or '; '.join(b['notes'])} | {act} |")
    L += ["", f"### Stash ({len(r['stashes'])})", ""]
    L += [f"- `{s['ref']}` {fmt_age(s['age_days'])}: {s['message']}" for s in r["stashes"]] or ["(无)"]
    u = r["uncommitted"]
    L += ["", "### 未提交改动(主 worktree)", ""]
    if u["count"] is None:
        L.append(f"- {u['note'] or '未知'}")
    else:
        L.append(f"- 共 {u['count']} 条 status 条目(已跟踪改动 {u['tracked']},未跟踪条目 {u['untracked']};"
                 f"展开后未跟踪文件 {u.get('untracked_files', '?')})")
        if u["note"]:
            L.append(f"- 注: {u['note']}")
        if u["top_dirs"]:
            L.append("- 前 5 顶层: " + ", ".join(f"`{d}` {n}" for d, n in u["top_dirs"]))
        if u["big_untracked"]:
            L.append(f"- 未跟踪 >50MB 单文件({len(u['big_untracked'])}):")
            L += [f"  - `{p}` {mb} MB" for p, mb in u["big_untracked"][:20]]
            if len(u["big_untracked"]) > 20:
                L.append(f"  - ... 另 {len(u['big_untracked']) - 20} 个")
    L.append("")
    return "\n".join(L)


def summary_row(r):
    u = r["uncommitted"]
    unc = (u["note"] or "?") if u["count"] is None else str(u["count"])
    return (f"| {r['name']} | `{r['base']}` | {len(r['worktrees'])} | {fmt_counts(counts(r['worktrees']))} | "
            f"{len(r['branches'])} | {fmt_counts(counts(r['branches']))} | {len(r['stashes'])} | {unc} | "
            f"{len(u['big_untracked'])} | {fmt_tasks(r['task_summary'])} | {r['elapsed_s']}s |")


SUMMARY_HEADER = ("| 仓库 | 基准 | wt | wt S/R/K | 分支 | 分支 S/R/K | stash | 未提交 | >50MB 未跟踪 | 任务分支 | 耗时 |\n"
                  "|---|---|---|---|---|---|---|---|---|---|---|")


def discover(root: Path):
    return sorted(p for p in root.iterdir() if p.is_dir() and (p / ".git").is_dir())


def repo_root(path: Path):
    """Main repository root for a path (linked worktrees map to their main repo)."""
    out = git_out(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if not out:
        return None
    common = Path(out.strip())
    return common.parent if common.name == ".git" else common


def apply_safe(r, root, status_timeout):
    """Remove SAFE worktrees (no --force), then `branch -d` branches SAFE on a re-scan."""
    repo = Path(r["repo"])
    log = []
    for w in r["worktrees"]:
        if w["class"] != "SAFE":
            continue
        try:
            ent = status_entries(w["path"], status_timeout, untracked="normal")
        except GitTimeout:
            log.append(f"跳过 worktree {w['path']}: status 超时")
            continue
        if ent is None or ent:
            log.append(f"跳过 worktree {w['path']}: 复核时非 clean")
            continue
        rc, _, err = git(repo, "worktree", "remove", w["path"], timeout=120)
        log.append(f"{'已移除' if rc == 0 else '失败'} worktree {w['path']}" + ("" if rc == 0 else f": {err.strip()}"))
    fresh = scan_repo(repo, root, status_timeout)
    for b in fresh["branches"]:
        if b["class"] != "SAFE":
            continue
        rc, _, err = git(repo, "branch", "-d", b["name"], timeout=60)
        log.append(f"{'已删除' if rc == 0 else '失败'} 分支 {b['name']}" + ("" if rc == 0 else f": {err.strip()}"))
    return log


def main(argv=None):
    ap = argparse.ArgumentParser(description="工作区卫生报告(默认只读)")
    ap.add_argument("repo", nargs="?", default=".", help="仓库路径(默认当前目录)")
    ap.add_argument("--all", action="store_true", help="扫描 --root 下所有直接子目录中的 git 主仓")
    ap.add_argument("--root", default=str(DEFAULT_ROOT), help="--all 的扫描根(默认 ~/projects)")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--summary", action="store_true", help="每仓一行")
    ap.add_argument("--status-timeout", type=int, default=60, help="单次 git status 超时秒数")
    ap.add_argument("--apply-safe", action="store_true", help="移除 SAFE worktree 并 -d 删除 SAFE 分支")
    ap.add_argument("--yes", action="store_true", help="确认 --apply-safe")
    a = ap.parse_args(argv)
    if a.apply_safe and not a.yes:
        ap.error("--apply-safe 需要同时给 --yes(且须先经用户同意)")
    root = Path(a.root).expanduser()
    if a.all:
        repos = discover(root)
    else:
        rr = repo_root(Path(a.repo).expanduser().resolve())
        if rr is None:
            print(f"不是 git 仓库: {a.repo}", file=sys.stderr)
            return 2
        repos = [rr]
    t0 = time.time()
    reports = []
    for repo in repos:
        rep = scan_repo(repo, root, a.status_timeout)
        if a.apply_safe:
            rep["applied"] = apply_safe(rep, root, a.status_timeout)
        reports.append(rep)
        if a.all:
            print(f"[hygiene] {repo.name} {rep['elapsed_s']}s", file=sys.stderr, flush=True)
    total = round(time.time() - t0, 1)
    if a.json:
        print(json.dumps({"root": str(root), "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
                          "elapsed_s": total, "repos": reports}, ensure_ascii=False, indent=2))
        return 0
    out = [f"# 工作区卫生报告 {time.strftime('%Y-%m-%d %H:%M')}", "",
           f"仓库数 {len(reports)},总耗时 {total}s。分类口径: worktree SAFE=已并入基准+clean+非主+非当前分支;"
           f"REVIEW=有未提交改动/locked/缺失,或未并入且 HEAD >{WT_STALE_DAYS} 天;KEEP=其余。"
           f"分支 SAFE=已并入+无 worktree 占用+非当前/基准/{'/'.join(sorted(PROTECTED))};"
           f"REVIEW=未并入且 >{BRANCH_STALE_DAYS} 天无提交。任务分支 task/<ID> 按计划状态: "
           f"进行中/待办/阻塞=KEEP,完成且已并入=SAFE,完成未并入/已取消/计划无此 ID=REVIEW。"
           f"本报告只读,未删除任何内容。", "",
           SUMMARY_HEADER]
    out += [summary_row(r) for r in reports]
    if not a.summary:
        out.append("")
        out += [render_md(r) for r in reports]
    for r in reports:
        if "applied" in r:
            out += ["", f"### --apply-safe 执行记录: {r['name']}", ""]
            out += [f"- {x}" for x in r["applied"]] or ["- (无 SAFE 项)"]
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
