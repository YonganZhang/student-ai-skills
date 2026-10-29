#!/usr/bin/env python3
"""scan_reachability.py — registry-driven dead-code guard (六合一注册架构 · 三阶段可达性版).

WHY (跨项目通用 pattern, 2026-05-27 起):
  注册账本 (_meta/_registry.yml) 记了"有哪些模块",但传统上没记"谁调用谁"。于是
  "登记了 entry: 怎么单跑" 被误当成 "已接入主流程",死代码混进去没人发现
  (实战: 一个 pipeline 项目曾因此积了 6 个死模块)。

  本扫描器补上缺失的 pipeline 调用图模型: registry 顶部按**生命周期三阶段**声明入口,
  扫描器顺着真实 import + subprocess 调用闭包判活死。

三阶段 (registry 顶部声明, 每类可多个入口):
  pre_processing:   接入主 pipeline 之前可做的 (改输入 / 预处理 / 注入提示词)
  pipeline:         主流程入口 (核心多 stage 流水线)
  post_processing:  主 pipeline 跑完之后做的 (导出 / 渲染 / 发布 / 产物后处理)

判据: tracked _code/*.py (+可配) 从三阶段任一入口的调用闭包走得到 = 活;
      三类都走不到 = 死代码 → 非 --list 模式 exit 1 (pre-commit 阻断 commit)。
      "其他都不用" — 不在三阶段调用链里的就是死代码。

与现有 status 字段的关系 (不另起炉灶): 可达性是 status 的机器证据 ——
  可达 → 应为 active; 声明了阶段入口但走不到 → wip (未接线); 啥都不是 → dead。

用法:
  python3 scan_reachability.py          # 报告; 有死代码 exit 1 (hook 用)
  python3 scan_reachability.py --list   # 只报告, 永远 exit 0
  python3 scan_reachability.py --json    # 机器可读 (喂 register.py 派生 status)

放置 + 接线 (init.sh 会做):
  - 脚本放 _meta/scan_reachability.py
  - registry 顶部加 pre_processing/pipeline/post_processing 三个 list
  - 装 pre-commit: cp 到 .git/hooks/pre-commit 或被现有 hook 委托
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(subprocess.run(
    ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True
).stdout.strip() or ".")
REGISTRY = REPO / "_meta" / "_registry.yml"

# 哪些目录算"pipeline 域代码"(被扫)。tooling/tests 放 _meta//_tests/ 天然不在内。
SCAN_GLOBS = ["_code/*.py", "_pipelines/*.py"]
PHASES = ["pre_processing", "pipeline", "post_processing"]
PY_STRING_RE = re.compile(r"""["']([A-Za-z_][\w]*)\.py["']""")  # subprocess "foo.py" refs


def _tracked_modules() -> dict[str, Path]:
    """basename(no .py) -> path, for every git-tracked pipeline-domain *.py (excl __init__)."""
    mods: dict[str, Path] = {}
    for glob in SCAN_GLOBS:
        out = subprocess.run(["git", "ls-files", glob], cwd=REPO,
                             capture_output=True, text=True)
        for line in out.stdout.splitlines():
            line = line.strip()
            if not line or line.endswith("__init__.py"):
                continue
            p = REPO / line
            mods[p.stem] = p
    return mods


def _edges_from(path: Path, known: set[str]) -> set[str]:
    """Module basenames this file references via import OR subprocess "<name>.py" string."""
    try:
        src = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return set()
    refs: set[str] = set()
    try:
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Import):
                for a in node.names:
                    refs.add(a.name.split(".")[-1])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    refs.add(node.module.split(".")[-1])
                for a in node.names:
                    refs.add(a.name.split(".")[-1])
    except SyntaxError:
        pass
    refs.update(PY_STRING_RE.findall(src))
    return refs & known


def reachable_closure(graph: dict[str, set[str]], roots: list[str]) -> set[str]:
    """BFS the call graph from roots -> reachable node set. Pure (unit-testable)."""
    seen: set[str] = set()
    frontier = list(roots)
    while frontier:
        cur = frontier.pop()
        if cur in seen:
            continue
        seen.add(cur)
        frontier.extend(graph.get(cur, set()) - seen)
    return seen


def _registry_list(key: str) -> list[str]:
    """Extract ONE top-level `key:` block of `  - <item>` lines (targeted, not full YAML —
    the functions: catalog below is human pseudo-YAML no loader accepts)."""
    if not REGISTRY.exists():
        return []
    items, in_block = [], False
    for raw in REGISTRY.read_text(encoding="utf-8").splitlines():
        if not in_block:
            if re.match(rf"^{re.escape(key)}\s*:", raw):
                in_block = True
                if re.search(r":\s*\[\s*\]", raw):
                    break
            continue
        m = re.match(r"^\s+-\s+(\S+)", raw)
        if m:
            items.append(m.group(1).strip())
        elif raw.strip() == "" or raw.lstrip().startswith("#"):
            continue
        else:
            break
    return items


def scan() -> dict:
    mods = _tracked_modules()
    known = set(mods)
    graph = {b: _edges_from(p, known) for b, p in mods.items()}

    phase_roots = {ph: [Path(x).stem for x in _registry_list(ph)] for ph in PHASES}
    all_roots = [r for rs in phase_roots.values() for r in rs]
    missing = sorted({r for r in all_roots if r not in known})

    # per-phase reachable (so each live module shows WHICH phase owns it)
    phase_reach = {ph: reachable_closure(graph, [r for r in rs if r in known])
                   for ph, rs in phase_roots.items()}
    reachable = set().union(*phase_reach.values()) if phase_reach else set()
    dead = sorted(known - reachable)

    owner = {}
    for b in reachable:
        owner[b] = next((ph for ph in PHASES if b in phase_reach[ph]), "?")
    return {
        "dead": dead, "reachable": sorted(reachable), "owner": owner,
        "phase_roots": phase_roots, "missing_roots": missing,
        "paths": {b: str(p.relative_to(REPO)) for b, p in mods.items()},
    }


def main() -> int:
    list_only = "--list" in sys.argv
    r = scan()
    if "--json" in sys.argv:
        print(json.dumps(r, indent=2, ensure_ascii=False))
        return 0 if (list_only or not r["dead"]) else 1
    nroots = sum(len(v) for v in r["phase_roots"].values())
    print(f"[reachability] phase-entries={nroots} reachable={len(r['reachable'])} "
          f"dead={len(r['dead'])}")
    if not nroots:
        print("⚠️  registry 顶部未声明 pre_processing/pipeline/post_processing 入口 — "
              "无法判可达性。先声明三阶段入口。")
    if r["missing_roots"]:
        print("⚠️  声明的入口在磁盘上不存在: " + ", ".join(r["missing_roots"]))
    if r["dead"]:
        print("\n🔴 死代码 (三阶段调用链都走不到):")
        for b in r["dead"]:
            print(f"   • {r['paths'][b]}")
        print("\n👉 修法: 接进 pre_processing/pipeline/post_processing 某入口的调用链,\n"
              "   或归档到 _legacy/。'其他都不用' — 不在三阶段里的就是死代码。")
    else:
        print("✅ 无死代码 — 每个 pipeline-域模块都能从某阶段入口走到")
    return 0 if (list_only or not r["dead"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
