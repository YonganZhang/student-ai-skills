#!/usr/bin/env python3
"""_code/register.py — 函数注册工具

用法:
  python _code/register.py --scan
      扫 _code/ + _pipelines/ 下所有 .py,自动 refresh _meta/_registry.yml
      (每次 commit / lint 时跑)

  python _code/register.py --add <func_name> --module _code/<path>
      AI 写完新函数后调,手动追加单条

  python _code/register.py --list
      列出当前 registry 所有 active 函数

设计:
- AST 解析,无 import runtime,安全
- 跳过 @transient 装饰的函数(临时/测试)
- 保留现有 _registry.yml 里的人工字段(method/tests/phases/description),
  只 refresh 函数清单(name/module/callers)
- 报告漏注册的 + 注册了但代码已删的
"""
import argparse
import ast
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("ERROR: 装 pyyaml: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY = REPO_ROOT / "_meta" / "_registry.yml"
SCAN_DIRS = ["_code", "_pipelines"]
# CI 工具自身 (meta-level),内部 helper 函数不进 registry
# (跟 _code/lint.py 的 CI_TOOL_FILES 保持一致)
CI_TOOL_FILES = {
    "_code/register.py",
    "_code/lint.py",
    "_code/sync_wiki.py",
    "_code/init_pipeline.py",
    "_code/init_domain.py",
}


def has_transient_decorator(node: ast.FunctionDef) -> bool:
    """检查函数是否有 @transient 装饰器(跳过注册)."""
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name) and dec.id == "transient":
            return True
        if isinstance(dec, ast.Attribute) and dec.attr == "transient":
            return True
    return False


def scan_module(py_path: Path) -> list[dict[str, Any]]:
    """AST 扫一个 .py 文件,返回顶层 def 清单(跳过 @transient).

    临时跳过 (按 artifact-lifecycle.md 协议):
    - 在 _sandbox/ 或 _tmp/ 目录的文件 → 整文件跳过
    - 函数名以 _test_ / _demo_ / scratch_ 开头 → 临时跳过
    - docstring 含 @tmp 或 @scratch marker → 临时跳过
    """
    # v9.0 临时文件跳过: _sandbox/ 或 _tmp/ 目录整文件不入 registry
    # v9.0.1 Codex R22 P0: skip 时输出 reason 让 AI 看见 (不再静默)
    py_str = str(py_path)
    if "/_sandbox/" in py_str:
        print(f"[register skip] {py_path.name}: 在 _sandbox/ 临时区 (v9.0)", file=sys.stderr)
        return []
    if "/_tmp/" in py_str:
        print(f"[register skip] {py_path.name}: 在 _tmp/ 临时区 (v9.0)", file=sys.stderr)
        return []
    try:
        tree = ast.parse(py_path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    funcs = []
    for node in tree.body:
        # 顶层 def(忽略类方法,因为 lint 主要关心独立函数)
        # v8.11.2 R16 修: 支持 async def (ast.AsyncFunctionDef 跟 FunctionDef 是不同类)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_"):  # _private 不强制注册
                continue
            # 临时函数名跳过 (按 artifact-lifecycle 协议)
            if node.name.startswith(("test_", "demo_", "scratch_")):
                continue
            if has_transient_decorator(node):
                continue
            # v9.0 docstring @tmp / @scratch marker 跳过
            ds = ast.get_docstring(node) or ""
            if "@tmp" in ds[:200] or "@scratch" in ds[:200]:
                continue
            # v8.13 用户原话: "代码内联注释" 真意 — 扫 docstring 里的 @marker
            # 让 cc Read 文件就看到完整 why/status/wired_up_in 不用查 yaml
            docstring = ast.get_docstring(node) or ""
            entry = {
                "name": node.name,
                "module": str(py_path.relative_to(REPO_ROOT)),
                "line": node.lineno,
                "has_docstring": bool(docstring),
                "docstring_first_line": docstring.split("\n")[0].strip()[:120],
            }
            # v8.13 扫 docstring @marker → 填 yaml (yaml 变派生视图, 不是真源)
            for line in docstring.split("\n"):
                line = line.strip()
                # lifecycle/wiring 标记 + pipeline-membership 标记 (扣子与线: @role/@pipeline/@needs/@produces)
                for marker in ("@status:", "@introduced_in:", "@wired_up_in:", "@why:", "@tags:", "@consumed_by:",
                               "@role:", "@pipeline:", "@needs:", "@produces:"):
                    if line.startswith(marker):
                        key = marker[1:-1]  # @status: → status
                        val = line[len(marker):].strip()
                        if key in ("tags", "needs", "produces"):
                            entry[key] = [t.strip() for t in val.split(",") if t.strip()]
                        else:
                            entry[key] = val
            # v8.14 Codex R17 Q3: active 自动 promote — 有 @consumed_by 即 active
            # 不靠 commit message 关键词 (95% 命中不到), 靠真接线证据
            if entry.get("consumed_by") and entry.get("status") in (None, "stub", "wip"):
                entry["status"] = "active"
            funcs.append(entry)
    return funcs


def scan_all() -> list[dict[str, Any]]:
    """扫所有 _code/ + _pipelines/ 下的 .py (跳过 CI 工具自身)."""
    all_funcs = []
    for top in SCAN_DIRS:
        top_dir = REPO_ROOT / top
        if not top_dir.exists():
            continue
        for py in top_dir.rglob("*.py"):
            if "/__pycache__/" in str(py) or "/_legacy/" in str(py):
                continue
            rel = str(py.relative_to(REPO_ROOT))
            if rel in CI_TOOL_FILES:
                continue
            all_funcs.extend(scan_module(py))
    return all_funcs


def load_registry() -> dict[str, Any]:
    """读现有 _registry.yml."""
    if not REGISTRY.exists():
        return {"functions": []}
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    if "functions" not in data:
        data["functions"] = []
    return data


def save_registry(data: dict[str, Any]) -> None:
    """写 _registry.yml,保持人工字段."""
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# _meta/_registry.yml — 代码/工具资产注册表\n"
        "#\n"
        "# 可由 _code/register.py --scan 辅助刷新 (函数清单 + module + line + docstring).\n"
        "# 人工字段(description / method / tests / phases / version / empirical_evidence) 保留.\n"
        "#\n"
        "# Schema: _meta/_schema/_registry_entry.yml\n\n"
    )
    REGISTRY.write_text(
        header + yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def merge_scan_with_registry(scanned: list[dict], registry: dict) -> tuple[dict, list, list]:
    """合并:保留人工字段,refresh AST 字段.

    v8.4-S7 升级 (R12 P0 — 0% → 60% 填充率): 写新 entry 时填 v2 默认字段
    (status=stub / introduced_in=current_phase / tags=[<module 派生>]).
    用 module:name 复合键 (R10 盲点 B1 — 同名函数冲突).

    Returns:
        (new_registry, newly_added, orphaned)
    """
    # v8.4 R10 B1: 复合键 module:name 防同名覆盖
    existing = {f"{f.get('module','')}:{f['name']}": f for f in registry.get("functions", [])}
    scanned_keys = {f"{f['module']}:{f['name']}" for f in scanned}

    # 当前 phase (从 _top/_task_plan.md stamp 抽, fallback "unknown")
    current_phase = _infer_current_phase()

    new_functions = []
    newly_added = []
    orphaned = []

    for s in scanned:
        key = f"{s['module']}:{s['name']}"
        if key in existing:
            # 更新 AST 字段,保留人工字段
            merged = dict(existing[key])
            merged["module"] = s["module"]
            merged["line"] = s["line"]
            if not merged.get("description") and s["docstring_first_line"]:
                merged["description"] = s["docstring_first_line"]
            # v8.16 Codex R19 修: scan_module 提取的 v2 字段优先于老 entry 字段
            # (修 v8.14 active 自动 promote 跟 merge 冲突: scan 返回 status=active 被
            #  老 entry status=stub 覆盖. 真因 — merged 复制老 entry 没用 scan 新值.)
            for v2_key in ("status", "why", "consumed_by", "tags", "introduced_in", "wired_up_in"):
                if s.get(v2_key) and (not merged.get(v2_key) or merged.get(v2_key) in ("stub", "legacy", "")):
                    merged[v2_key] = s[v2_key]
            if not merged.get("status"):
                merged["status"] = "stub"
            if not merged.get("introduced_in"):
                merged["introduced_in"] = "legacy"
            # 写时 pipeline 标记 (扣子与线): 完全由当前 docstring 派生, 标记删了即清, 不黏旧值
            for _tk in ("role", "pipeline", "needs", "produces"):
                if s.get(_tk):
                    merged[_tk] = s[_tk]
                else:
                    merged.pop(_tk, None)
            merged.setdefault("role", "unmarked")
            new_functions.append(merged)
        else:
            # 新函数,加 v2 默认字段 (scan_module 提取的 @marker 字段优先)
            entry = {
                "name": s["name"],
                "type": "TODO",
                "module": s["module"],
                "line": s["line"],
                # v8.16 Codex R19 修: scan 提取的 @marker 字段优先, 没有才用默认
                "why": s.get("why") or s["docstring_first_line"] or "TODO: 一句话 motivation",
                "status": s.get("status") or "stub",  # scan 解析 @status: active → 用 active
                "introduced_in": s.get("introduced_in") or current_phase,
                "wired_up_in": s.get("wired_up_in"),
                "tags": s.get("tags") or _infer_tags_from_module(s["module"]),
                "consumed_by": s.get("consumed_by"),
                "role": s.get("role") or "unmarked",   # 写时 pipeline 标记 (扣子与线)
                "description": s["docstring_first_line"] or "TODO: cc 补充描述",
                "method": None,
                "tests": [],
                "phases": [current_phase] if current_phase != "unknown" else [],
            }
            for _tk in ("pipeline", "needs", "produces"):
                if s.get(_tk):
                    entry[_tk] = s[_tk]
            new_functions.append(entry)
            newly_added.append(entry)

    # v8.16 Codex R19 修: orphans 不丢, 标 archived 留 entry 保 why 历史
    # (用户原话: "删老代码标 legacy 而不是删 entry")
    # 旧版: orphans return 出来但 registry['functions'] 直接覆盖 → orphans 丢
    # 新版: orphans 加 status=archived + archived_at, 保留在 new_functions
    from datetime import date as _date
    today = _date.today().isoformat()
    for key, entry in existing.items():
        if key not in scanned_keys:
            if entry.get("status") != "archived":
                entry["status"] = "archived"
                entry.setdefault("archived_at", today)
                entry.setdefault("legacy_note", f"代码已删 (scan 未扫到), 自动 archived")
            orphaned.append(entry)
            new_functions.append(entry)  # 保留 entry 在 yaml, 不丢

    registry["functions"] = new_functions
    return registry, newly_added, orphaned


def _infer_current_phase() -> str:
    """从 _top/_task_plan.md stamp 抽当前 phase. fallback 'unknown'."""
    plan = REPO_ROOT / "_top" / "_task_plan.md"
    if not plan.exists():
        return "unknown"
    import re as _re
    txt = plan.read_text(encoding="utf-8")[:500]
    m = _re.search(r"\[([Pv][\d.][\w.-]*)", txt)  # 抓 [P5.3-E] / [v8.4] 类
    return m.group(1) if m else "unknown"


def _infer_tags_from_module(module: str) -> list[str]:
    """从 module 路径派生默认 tags (v8.4-S7 R12 减字段填写门槛)."""
    tags = []
    if "_handlers/" in module:
        tags.append("async-handler")
    if "_engines/" in module:
        tags.append("engine")
    if "_schema/" in module:
        tags.append("schema")
    if "_test_report/" in module:
        tags.append("e2e-demo")
    if "_async/" in module:
        tags.append("async")
    if "_server/" in module:
        tags.append("server")
    if "01_ingest" in module:
        tags.append("ingest")
    if "_04_build" in module:
        tags.append("build")
    return tags


def cmd_scan() -> int:
    scanned = scan_all()
    registry = load_registry()
    new_registry, added, orphaned = merge_scan_with_registry(scanned, registry)
    save_registry(new_registry)

    print(f"✓ 扫了 {len(scanned)} 个函数")
    if added:
        print(f"\n🆕 {len(added)} 个新函数(待人工补 method/tests/phases):")
        for f in added[:10]:
            print(f"  + {f['name']} @ {f['module']}:{f['line']}")
        if len(added) > 10:
            print(f"  ... (共 {len(added)} 个)")
    if orphaned:
        print(f"\n⚠️  {len(orphaned)} 个 orphan(代码已删,registry 里还有):")
        for f in orphaned[:10]:
            print(f"  - {f['name']} @ {f.get('module', '?')}")
    print(f"\n📋 总计 active: {len(new_registry['functions'])}")
    return 0


def cmd_add(name: str, module: str) -> int:
    registry = load_registry()
    if any(f["name"] == name for f in registry["functions"]):
        print(f"⚠️  {name} 已在 registry,跳过")
        return 0
    entry = {
        "name": name,
        "module": module,
        "description": "TODO: 补充",
        "type": "TODO",
        "method": None,
        "tests": [],
        "phases": [],
    }
    registry["functions"].append(entry)
    save_registry(registry)
    print(f"✓ 加 {name} @ {module}")
    print("⚠️  请补充 description / method / tests / phases 字段")
    return 0


def cmd_list() -> int:
    registry = load_registry()
    funcs = registry.get("functions", [])
    print(f"📋 Registry: {len(funcs)} 个 active 函数\n")
    by_module: dict[str, list] = {}
    for f in funcs:
        by_module.setdefault(f["module"], []).append(f)
    for mod, fs in sorted(by_module.items()):
        print(f"  {mod}:")
        for f in fs:
            phase = f.get("phases") or []
            method = f.get("method") or "—"
            print(f"    {f['name']:<40s}  phase={phase}  method={method}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("scan", help="扫 _code/+_pipelines/ refresh registry")
    add = sub.add_parser("add", help="手动加一条")
    add.add_argument("--name", required=True)
    add.add_argument("--module", required=True)
    sub.add_parser("list", help="列出 active 函数")

    # 兼容旧 --scan / --add 写法
    p.add_argument("--scan", action="store_true")
    p.add_argument("--add", dest="add_name")
    p.add_argument("--module", dest="add_module")
    p.add_argument("--list", action="store_true")

    args = p.parse_args()
    if args.scan or args.cmd == "scan":
        return cmd_scan()
    if args.add_name or args.cmd == "add":
        nm = args.add_name or getattr(args, "name", None)
        md = args.add_module or getattr(args, "module", None)
        if not nm or not md:
            print("ERROR: --add 需要 --module", file=sys.stderr)
            return 1
        return cmd_add(nm, md)
    if args.list or args.cmd == "list":
        return cmd_list()
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
