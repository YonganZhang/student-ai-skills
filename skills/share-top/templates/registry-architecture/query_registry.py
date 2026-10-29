#!/usr/bin/env python3
"""v8.4 注册架构 CLI — 让 cc 进项目不读全 YAML.

实施 v9 注册架构哲学规范原则 2 (渐进披露) + 原则 5 (可索引).
规范源: _top/_external_reviews/_unified_fixes/v9_registry_architecture_philosophy.md
反哺路径: 本项目实战验证后反哺 ~/.claude/skills/share-top/templates/registry-architecture/

5 模式查询:
    python3 _code/_query_registry.py --by-status active          # 列状态=active 函数
    python3 _code/_query_registry.py --by-tag rag                # 列 tag 含 rag 的
    python3 _code/_query_registry.py --orphans                   # 列无 caller 可疑函数
    python3 _code/_query_registry.py --module step_03            # 列某模块全 entries
    python3 _code/_query_registry.py --report                    # 出人读 markdown 报告

cc 进项目第一动作 (AGENTS.md 加 hint):
    python3 _code/_query_registry.py --report  # 30s 浏览, 不读 1500 行 YAML
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
REGISTRY = REPO / "_meta" / "_registry.yml"
RESOLVED = REPO / "_meta" / "_registry_resolved.yml"
INDEX_FILE = REPO / "_meta" / "_registry_index.yml"


def load_registry() -> list[dict]:
    if not REGISTRY.exists():
        return []
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    return data.get("functions", [])


def load_resolved() -> dict:
    """加载机器派生视图. 不存在则跑 register.py --infer 生成."""
    if not RESOLVED.exists():
        return {}
    data = yaml.safe_load(RESOLVED.read_text(encoding="utf-8")) or {}
    return {f["name"]: f for f in data.get("functions", []) if f.get("name")}


def load_index() -> dict:
    """加载倒排索引 (原则 5 可索引). 不存在则即时构建."""
    if INDEX_FILE.exists():
        return yaml.safe_load(INDEX_FILE.read_text(encoding="utf-8")) or {}
    return _build_index(load_registry())


def _build_index(funcs: list[dict]) -> dict:
    """构建倒排索引: by_status / by_tag / by_module / orphans."""
    by_status = defaultdict(list)
    by_tag = defaultdict(list)
    by_module = defaultdict(list)
    orphans = []
    for f in funcs:
        name = f.get("name")
        if not name:
            continue
        # status (v2 新字段, 兼容老 entry 缺字段 → unknown)
        status = f.get("status", "unknown")
        by_status[status].append(name)
        # tags
        for t in (f.get("tags") or []):
            by_tag[t].append(name)
        # module 简化 (去 prefix)
        mod = f.get("module", "")
        if mod:
            by_module[mod].append(name)
        # orphan: status=active 但 wired_up_in 空 (违反原则 3)
        if status == "active" and not f.get("wired_up_in"):
            orphans.append(name)
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "by_status": dict(by_status),
        "by_tag": dict(by_tag),
        "by_module": dict(by_module),
        "orphans": orphans,
    }


def cmd_by_status(status: str) -> int:
    funcs = load_registry()
    matches = [f for f in funcs if f.get("status", "unknown") == status]
    print(f"=== status={status}: {len(matches)} 函数 ===")
    for f in matches[:30]:
        why = f.get("why", "(无 why — 老 entry 缺字段)")
        print(f"  {f['name']:40s} ({f.get('type', '?')}, {f.get('module', '?').split('/')[-1]}:{f.get('line', '?')})")
        print(f"    why: {why[:100]}")
    if len(matches) > 30:
        print(f"  ... 共 {len(matches)} (显示前 30)")
    return 0


def cmd_by_tag(tag: str) -> int:
    funcs = load_registry()
    matches = [f for f in funcs if tag in (f.get("tags") or [])]
    print(f"=== tag={tag}: {len(matches)} 函数 ===")
    for f in matches:
        print(f"  {f['name']:40s} ({f.get('status', 'unknown')}, {f.get('module', '?').split('/')[-1]})")
    return 0


def cmd_prune(dry_run: bool = True) -> int:
    """v8.15 完整 CRUD: --prune 真比对 scan vs registry 差集 → 标 archived.

    流程:
    1. 跑 register.py --scan 取代码当前真实函数清单
    2. 对比 registry yaml 现存 entries
    3. 差集 (registry 有 代码没) = dead entry → 候选 archived
    4. dry-run: 只列, --apply 才真改 status=archived (保 why 历史, 不删 entry)

    Codex R17 原话: "默认 archived 而不是删除, 保留 why 和历史. hook 自动改
    太魔法易误伤 rename, 走 CLI 手动确认".
    """
    import ast
    # v8.16 Codex R19 修: dry-run 不再跑 register.py --scan (有副作用会写 registry)
    # 直接 ast 扫代码取真实清单, 跟 registry 比对. apply 模式才改 registry.

    # Step 2: 扫代码 AST 拿真实清单 (跟 register.py scan_all 同款逻辑)
    SCAN_DIRS = ["_code", "_pipelines", "_tests"]
    real_funcs = set()  # (module, name)
    for top in SCAN_DIRS:
        top_dir = REPO / top
        if not top_dir.exists():
            continue
        for py in top_dir.rglob("*.py"):
            if "__pycache__" in str(py) or "/_legacy/" in str(py):
                continue
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except Exception:
                continue
            mod = str(py.relative_to(REPO))
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name.startswith("_"):
                        continue
                    real_funcs.add((mod, node.name))

    # Step 3: registry 现 entries vs 代码真实清单 差集
    funcs = load_registry()
    dead = []
    for entry in funcs:
        n = entry.get("name")
        mod = entry.get("module")
        if not n or not mod:
            continue
        if entry.get("status") == "archived":
            continue  # 已 archived 跳过
        if (mod, n) not in real_funcs:
            dead.append(entry)

    print(f"=== --prune (dry_run={dry_run}) ===\n")
    print(f"代码真实函数: {len(real_funcs)} 个")
    print(f"registry 现 entries: {len(funcs)} 个")
    print(f"已 archived: {sum(1 for f in funcs if f.get('status') == 'archived')} 个")
    print(f"🔴 候选 archived (代码已删 yaml 留): {len(dead)} 个\n")

    for d in dead[:15]:
        print(f"  - {d.get('name'):40s} @ {d.get('module', '?').split('/')[-1]}:{d.get('line', '?')}")
        why = d.get("why") or d.get("description") or ""
        if why:
            print(f"      why: {why[:80]}")
    if len(dead) > 15:
        print(f"  ... 共 {len(dead)} (显示前 15)")

    if not dry_run and dead:
        # --apply: 真改 status=archived (不删, 保 why 历史)
        from datetime import date
        today = date.today().isoformat()
        for entry in funcs:
            n = entry.get("name")
            mod = entry.get("module")
            if (mod, n) not in real_funcs and entry.get("status") != "archived":
                entry["status"] = "archived"
                entry["archived_at"] = today
                entry.setdefault("legacy_note", f"代码已删, 自动 archived ({today})")

        with open(REGISTRY, "w", encoding="utf-8") as f:
            yaml.dump({"functions": funcs, **{k: v for k, v in load_raw_registry().items() if k != "functions"}},
                      f, allow_unicode=True, sort_keys=False, default_flow_style=False, width=200)
        print(f"\n✅ {len(dead)} 个 entry 真改 status=archived (保 why 历史, 不删)")
    elif dry_run and dead:
        print(f"\nℹ️  dry-run 模式只列, 不动 yaml. 真改跑: --prune --apply")
    return 0


def load_raw_registry() -> dict:
    """load_registry 返 functions list, 本函数返完整 dict 含 schema_version 等"""
    if not REGISTRY.exists():
        return {}
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}


def cmd_orphans() -> int:
    """列违反原则 3 接线证据的函数 (status=active 但 wired_up_in 空)."""
    funcs = load_registry()
    orphans = [f for f in funcs if f.get("status") == "active" and not f.get("wired_up_in")]
    print(f"=== orphans (status=active && wired_up_in=null): {len(orphans)} 函数 ===")
    print("(这些是 status=active 但没接入主流程证据的可疑函数, 违反 v9 原则 3)\n")
    for f in orphans[:20]:
        print(f"  {f['name']:40s} ({f.get('module', '?').split('/')[-1]})")
        print(f"    why: {f.get('why', '(无 why)')[:80]}")
    return 0 if not orphans else 1


def cmd_module(mod_substr: str) -> int:
    funcs = load_registry()
    matches = [f for f in funcs if mod_substr in (f.get("module") or "")]
    print(f"=== module 含 '{mod_substr}': {len(matches)} 函数 ===")
    for f in matches[:30]:
        status = f.get("status", "unknown")
        status_icon = {"active": "✅", "wip": "🟡", "stub": "⚪", "deprecated": "⚠️", "archived": "📦", "unknown": "❓"}.get(status, "?")
        print(f"  {status_icon} {f['name']:40s} {status:12s} line={f.get('line', '?')}")
        why = f.get("why")
        if why:
            print(f"     why: {why[:100]}")
    return 0


def cmd_report() -> int:
    """人读 markdown 报告 (cc 进项目必跑 30s 浏览)."""
    funcs = load_registry()
    total = len(funcs)
    status_count = Counter(f.get("status", "unknown") for f in funcs)
    has_why = sum(1 for f in funcs if f.get("why"))
    has_wired_up = sum(1 for f in funcs if f.get("wired_up_in"))
    has_tags = sum(1 for f in funcs if f.get("tags"))
    by_type = Counter(f.get("type", "unknown") for f in funcs)

    # v8.10 跨项目兼容: 规范源用相对路径, 不写死本项目内路径 (Codex R14 真核暴露)
    philosophy_path = REPO / "_top" / "_external_reviews" / "_unified_fixes" / "v9_registry_architecture_philosophy.md"
    philosophy_line = f"> 规范源: {philosophy_path.relative_to(REPO)}" if philosophy_path.exists() else "> 规范: share-top/templates/registry-architecture/README.md (5 核心原则)"
    print(f"""# 📋 Registry 健康报告 (cc 30s 浏览)

> 生成: {datetime.now().strftime("%Y-%m-%d %H:%M")}
{philosophy_line}
> 实施 v8.10 注册架构 5 核心原则 (卡片化 / 接线证据 / 状态机 / 可索引 / 自动补)

## 总览
- 函数总数: **{total}**
- 含 why 字段 (原则 1 卡片化): **{has_why}** / {total} = {has_why*100//max(total,1)}%
- 含 wired_up_in 字段 (原则 2 接线证据): **{has_wired_up}** / {total} = {has_wired_up*100//max(total,1)}%
- 含 tags 字段 (原则 4 可索引): **{has_tags}** / {total} = {has_tags*100//max(total,1)}%

## status 分布 (原则 4 状态机)
""")
    for status, count in status_count.most_common():
        icon = {"active": "✅", "wip": "🟡", "stub": "⚪", "deprecated": "⚠️", "archived": "📦", "unknown": "❓"}.get(status, "?")
        print(f"- {icon} {status:12s}: {count}")

    print(f"\n## type 分布")
    for t, count in by_type.most_common():
        print(f"- {t:15s}: {count}")

    # 可疑函数
    orphans = [f for f in funcs if f.get("status") == "active" and not f.get("wired_up_in")]
    if orphans:
        print(f"\n## 🔴 可疑 (status=active 但无 wired_up_in 接入证据)")
        print(f"违反原则 3, 共 {len(orphans)} 函数 (显示前 5):")
        for f in orphans[:5]:
            print(f"- `{f['name']}` ({f.get('module', '?').split('/')[-1]})")
        print(f"\n修法: 加 wired_up_in commit hash, 或改 status=wip/archived")

    # 老 schema (无 why)
    old_schema = [f for f in funcs if not f.get("why") and not f.get("status")]
    if old_schema:
        print(f"\n## ⚪ 老 schema entry (无 why + 无 status)")
        print(f"共 {len(old_schema)} 函数, Boy Scout Rule 增量升级 (原则 8)")

    print(f"\n## CLI 子命令")
    print("- `query_registry.py --by-status active` 列状态=active 函数")
    print("- `query_registry.py --by-tag rag` 列 RAG 相关")
    print("- `query_registry.py --orphans` 列可疑")
    print("- `query_registry.py --module step_03` 列模块函数")
    print("- `query_registry.py --report` 本报告")
    return 0


def cmd_build_index() -> int:
    """构建倒排索引 → _registry_index.yml (原则 5 可索引)."""
    funcs = load_registry()
    index = _build_index(funcs)
    INDEX_FILE.write_text(yaml.dump(index, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"✅ 索引落 {INDEX_FILE.name}")
    print(f"   by_status: {len(index['by_status'])} 状态值")
    print(f"   by_tag: {len(index['by_tag'])} 标签")
    print(f"   by_module: {len(index['by_module'])} 模块")
    print(f"   orphans: {len(index['orphans'])}")
    return 0


# === R10+R11 审议共识新加 4 模式 ===
def cmd_by_phase(phase: str) -> int:
    """R10 提: 按 introduced_in (phase) 查 — 跟踪某 phase 加了什么."""
    funcs = load_registry()
    matches = [f for f in funcs if phase in (f.get("introduced_in") or f.get("phases", []) or [])]
    print(f"=== introduced_in 含 '{phase}': {len(matches)} 函数 ===")
    for f in matches:
        print(f"  {f['name']:40s} ({f.get('status', '?')}) — {f.get('why', '(无 why)')[:60]}")
    return 0


def cmd_consumed_by(name: str) -> int:
    """R10+R11 共识: 反查依赖 — 删该函数会影响谁."""
    resolved = load_resolved()
    impacted = []
    # 扫所有 entry 的 consumed_by_resolved / consumed_by_auto / depends_on, 找谁引用 name
    for fname, fdata in resolved.items():
        callers = (fdata.get("consumed_by_auto") or []) + (
            [c.get("path") if isinstance(c, dict) else c for c in (fdata.get("consumed_by_manual") or [])]
        )
        if any(name in str(c) for c in callers):
            impacted.append(fname)
    print(f"=== 反查 '{name}' 的消费者: {len(impacted)} 函数依赖它 ===")
    print(f"删/改 {name} 会影响以上函数 (爆炸半径评估)\n")
    for n in impacted[:20]:
        print(f"  {n}")
    return 0


def cmd_missing(field: str) -> int:
    """R10 提: 列缺指定字段的 entry → 补账任务清单."""
    funcs = load_registry()
    missing = [f for f in funcs if not f.get(field)]
    print(f"=== 缺字段 '{field}': {len(missing)} / {len(funcs)} ({len(missing)*100//max(len(funcs),1)}%) ===")
    print(f"补账清单 (前 20):\n")
    for f in missing[:20]:
        print(f"  {f['name']:40s} ({f.get('module', '?').split('/')[-1]}:{f.get('line', '?')})")
    return 0


def cmd_verify_active() -> int:
    """R12 cc subagent P0: 真核 status=active 的接线证据 — lint 从 doc 变可执行.

    跑遍所有 active entry, 真去代码里 grep 验证 wired_up_in 指向的 commit/path 真存在
    + 至少 1 个 caller. 输出 false_positive 清单 (status 写 active 但物理已断).
    """
    import subprocess
    funcs = load_registry()
    active = [f for f in funcs if f.get("status") == "active"]
    print(f"=== --verify-active: 真核 {len(active)} 个 status=active 的接线证据 ===\n")
    false_positives = []
    for f in active:
        name = f.get("name", "")
        wired_up = f.get("wired_up_in")
        # 1. wired_up_in 非空检查
        if not wired_up:
            false_positives.append({"name": name, "issue": "status=active 但 wired_up_in 空"})
            continue
        # 2. wired_up_in 真在 git log? (commit hash 验证)
        if len(wired_up) == 7 or len(wired_up) >= 40:
            try:
                r = subprocess.run(["git", "log", "--oneline", "-1", wired_up],
                                    capture_output=True, text=True, timeout=5, cwd=str(REPO))
                if r.returncode != 0:
                    false_positives.append({"name": name, "issue": f"wired_up_in={wired_up} 不在 git log"})
                    continue
            except Exception:
                pass
        # 3. 至少 1 个 caller 真存在? (v8.4-S7 R12 lint 白名单)
        # cmd_* / handler_* / _internal_* 是 CLI dispatch / 框架内部, 不期望外部 caller
        WHITELIST_PATTERNS = ("cmd_", "handler_", "do_get", "do_post", "run")
        if name.startswith(WHITELIST_PATTERNS):
            continue  # 跳过 — 它们是 dispatch 内调用, 不该走 caller grep 判定
        try:
            r = subprocess.run(
                ["grep", "-rln", "--include=*.py", "--include=*.js", "--include=*.mjs",
                 rf"\b{name}\b", str(REPO / "_code"), str(REPO / "_pipelines")],
                capture_output=True, text=True, timeout=8,
            )
            callers = [l for l in r.stdout.splitlines() if "__pycache__" not in l]
            own_module = f.get("module", "")
            external = [c for c in callers if not c.endswith(own_module)]
            if not external:
                false_positives.append({"name": name, "issue": "无外部 caller (物理断联)"})
        except Exception:
            pass

    if false_positives:
        print(f"🔴 发现 {len(false_positives)} 个 false_positive (status=active 但接线证据不全):\n")
        for fp in false_positives[:20]:
            print(f"  - {fp['name']:40s}: {fp['issue']}")
        return 1
    else:
        print(f"✅ {len(active)} 个 active 全部物理对齐, 0 false_positive")
        return 0


def cmd_diff(old_index_file: str) -> int:
    """R10+R11 共识: 跟上次 index 对比变化 → PR review 入口."""
    if not Path(old_index_file).exists():
        print(f"🔴 旧 index 不存在: {old_index_file}")
        return 1
    old = yaml.safe_load(Path(old_index_file).read_text(encoding="utf-8")) or {}
    new = load_index()
    old_active = set(old.get("by_status", {}).get("active", []))
    new_active = set(new.get("by_status", {}).get("active", []))
    print(f"=== Registry 变化 (vs {old_index_file}) ===")
    print(f"\n新增 active ({len(new_active - old_active)}):")
    for n in sorted(new_active - old_active)[:15]:
        print(f"  + {n}")
    print(f"\n从 active 掉出 ({len(old_active - new_active)}):")
    for n in sorted(old_active - new_active)[:15]:
        print(f"  - {n}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="v8.4 Registry CLI — 渐进披露 + 可索引 (R10+R11 共识扩展)")
    p.add_argument("--by-status", help="按 status 查 (stub/wip/active/deprecated/archived/unknown)")
    p.add_argument("--by-tag", help="按 tag 查")
    p.add_argument("--by-phase", help="按 introduced_in (phase) 查 R10 提")
    p.add_argument("--consumed-by", help="反查谁依赖此函数 (R10+R11 共识, 爆炸半径评估)")
    p.add_argument("--missing", help="列缺指定字段的 entry (e.g. why/wired_up_in/tags) R10 提")
    p.add_argument("--diff", help="跟旧 index 对比变化 (R10+R11 共识, PR review)")
    p.add_argument("--verify-active", action="store_true", help="真核 active 接线证据 (R12 P0 lint 可执行)")
    p.add_argument("--orphans", action="store_true", help="列可疑函数 (status=active 但无 wired_up_in)")
    p.add_argument("--prune", action="store_true", help="v8.13+ 列将 archived 的 dead entry (默认 dry-run)")
    p.add_argument("--apply", action="store_true", help="跟 --prune 配合, 真改 status=archived (保 why 历史)")
    p.add_argument("--module", help="按 module 子串查")
    p.add_argument("--report", action="store_true", help="人读 markdown 报告 (cc 进项目必跑)")
    p.add_argument("--build-index", action="store_true", help="构建倒排索引 → _registry_index.yml")
    p.add_argument("--format", default="text", choices=["text", "json"], help="输出格式 (R10 提)")
    args = p.parse_args()

    if args.by_status:
        return cmd_by_status(args.by_status)
    if args.by_tag:
        return cmd_by_tag(args.by_tag)
    if args.by_phase:
        return cmd_by_phase(args.by_phase)
    if args.consumed_by:
        return cmd_consumed_by(args.consumed_by)
    if args.missing:
        return cmd_missing(args.missing)
    if args.diff:
        return cmd_diff(args.diff)
    if args.verify_active:
        return cmd_verify_active()
    if args.prune:
        return cmd_prune(dry_run=not args.apply)
    if args.orphans:
        return cmd_orphans()
    if args.module:
        return cmd_module(args.module)
    if args.report:
        return cmd_report()
    if args.build_index:
        return cmd_build_index()
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
