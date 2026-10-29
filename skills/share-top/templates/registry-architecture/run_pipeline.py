#!/usr/bin/env python3
"""_code/run_pipeline.py — 瘦 pipeline 运行器 (线的执行器 · 跨项目模板)。

补 pipeline-registration-paradigm.md 承诺过、却一直没造的"线执行器"。
一根线 = `_pipelines/_<name>.yml` manifest 里的有序扣子串; 扣子真源 = `_meta/_registry.yml`
(函数 + docstring 写时标记 @role/@pipeline/@needs/@produces 派生)。本运行器只做三件事:
  - validate: ref 在 registry / 入口文件在 / needs 与上游 produces 一致 (fail-loud)
  - run: 按声明顺序跑, 每步先查 needs 文件存在(缺了停, 不静默跳过), trace 落 _outputs/_runs/
  - LOCK 写保护: manifest 声明 `lock_dirs:` 的目录, 任何步骤改写即中止 (护数据真源)

设计纪律: **不自建 DAG 引擎**(科研/小项目近线性)。要 freshness/并行/真 DAG 再上 Snakemake。

manifest 约定字段:
    pipeline: <name>
    lock_dirs: [<相对路径>...]      # 可选: 禁止被改写的数据真源目录 (LOCK)
    data_roots: [<相对路径>...]     # 可选: needs/produces 文件搜索根 (默认 _outputs/_figures)
    steps:
      - id: <local>
        ref: <registry id>          # 指向 _meta/_registry.yml 的扣子 id
        needs: [<file>...]
        success: { outputs_exist: [<file>...] }

用法:
    python _code/run_pipeline.py <name> --validate    # 只校验(安全)
    python _code/run_pipeline.py <name>               # 一键跑全线
    python _code/run_pipeline.py <name> --from <step> # 断点续跑
"""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "_meta" / "_registry.yml"
DEFAULT_DATA_ROOTS = ["_outputs", "_figures", "derived"]


def load_registry() -> dict[str, dict]:
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    out = {}
    for f in data.get("functions", []):
        key = f.get("id") or f"{f.get('module','')}:{f.get('name','')}"
        out[key] = f
    return out


def load_manifest(name: str) -> dict:
    path = ROOT / "_pipelines" / f"_{name}.yml"
    if not path.is_file():
        path = ROOT / "_pipelines" / f"{name}.yml"
    if not path.is_file():
        sys.exit(f"❌ 没有这条线: _pipelines/_{name}.yml")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def data_roots(manifest: dict) -> list[Path]:
    rels = manifest.get("data_roots") or DEFAULT_DATA_ROOTS
    return [ROOT / r for r in rels]


def find_file(rel: str, roots: list[Path]) -> Path | None:
    """在声明的数据根里找文件 (不扫整个 repo, 避免按文件名乱匹配旧文件)。"""
    for root in roots:
        hit = root / rel
        if hit.exists():
            return hit
        matches = list(root.rglob(rel)) if root.is_dir() else []
        if matches:
            return matches[0]
    return None


def _lock_snapshot(manifest: dict) -> dict[str, tuple]:
    snap: dict[str, tuple] = {}
    for d in (ROOT / r for r in manifest.get("lock_dirs", [])):
        if d.is_dir():
            for p in d.rglob("*"):
                if p.is_file():
                    st = p.stat()
                    snap[str(p)] = (st.st_mtime_ns, st.st_size)
    return snap


def validate(manifest: dict, registry: dict[str, dict]) -> int:
    name = manifest.get("pipeline", "?")
    roots = data_roots(manifest)
    issues, produced = [], set()
    for step in manifest.get("steps", []):
        sid, ref = step.get("id"), step.get("ref")
        entry = registry.get(ref)
        if entry is None:
            issues.append(f"[{sid}] ref '{ref}' 不在 registry (非已注册扣子)")
        else:
            if not (ROOT / entry["module"]).is_file():
                issues.append(f"[{sid}] 入口文件不存在: {entry['module']}")
            if entry.get("status") in {"deprecated", "archived"}:
                issues.append(f"[{sid}] 引用了 {entry['status']} 扣子 {ref}")
            if entry.get("role") in {"helper", "unmarked"}:
                issues.append(f"[{sid}] 引用的 '{ref}' role={entry.get('role')} (非扣子; 应 @role: step/entry)")
        for need in step.get("needs", []):
            if need not in produced and find_file(need, roots) is None:
                issues.append(f"[{sid}] needs '{need}' 既非上游产出、当前也不存在 (断链?)")
        produced.update(step.get("success", {}).get("outputs_exist", []))
    if issues:
        print(f"❌ pipeline '{name}' 校验失败 ({len(issues)}):")
        for i in issues:
            print("   -", i)
        return 1
    print(f"✅ pipeline '{name}' 校验通过: {len(manifest.get('steps', []))} 扣子, ref/入口/DAG 一致")
    return 0


def run(manifest: dict, registry: dict[str, dict], from_step: str | None,
        allow_locked_write: bool = False) -> int:
    name = manifest.get("pipeline", "pipeline")
    steps = manifest.get("steps", [])
    roots = data_roots(manifest)
    if from_step is not None and not any(s.get("id") == from_step for s in steps):
        sys.exit(f"❌ --from '{from_step}' 不是 '{name}' 线里的 step id")
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = ROOT / "_outputs" / "_runs" / f"{name}-{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    record = {"pipeline": name, "run_id": run_id, "steps": []}
    lock0 = _lock_snapshot(manifest)
    started = from_step is None
    ran = 0
    for step in steps:
        sid, ref = step.get("id"), step.get("ref")
        if not started:
            if sid == from_step:
                started = True
            else:
                continue
        entry = registry.get(ref)
        if entry is None:
            sys.exit(f"❌ [{sid}] ref '{ref}' 不在 registry — 先跑 --validate")
        missing = [n for n in step.get("needs", []) if find_file(n, roots) is None]
        if missing:
            sys.exit(f"❌ [{sid}] 缺少输入 {missing} — 上游扣子没跑? 停。(不静默跳过)")
        log = run_dir / f"{sid}.log"
        step_start = time.time()
        print(f"▶ [{sid}] {entry['module']} ...")
        with log.open("w") as lf:
            proc = subprocess.run([sys.executable, str(ROOT / entry["module"])],
                                  cwd=str(ROOT), stdout=lf, stderr=subprocess.STDOUT)
        ran += 1
        if not allow_locked_write:
            now = _lock_snapshot(manifest)
            changed = [p for p in (set(lock0) | set(now)) if lock0.get(p) != now.get(p)]  # 含增/删/改
            if changed:
                sys.exit(f"❌ [{sid}] 改写了 LOCK 数据真源 {changed[:3]}...({len(changed)} 个)! "
                         f"已中止。加 --allow-locked-write 显式放行(危险), 或把脚本输出改道。")
        if proc.returncode != 0:
            sys.exit(f"❌ [{sid}] 退出码 {proc.returncode} — 见 {log}")
        produced = step.get("success", {}).get("outputs_exist", [])
        fresh = []
        for p in produced:
            hit = find_file(p, roots)
            fresh.append(hit is not None and hit.stat().st_mtime >= step_start)
        if not all(fresh):
            stale = [p for p, f in zip(produced, fresh) if not f]
            sys.exit(f"❌ [{sid}] 跑完但声明产物未刷新/缺失 {stale} — 见 {log}")
        record["steps"].append({"id": sid, "ref": ref, "exit": 0, "log": str(log.relative_to(ROOT))})
        print(f"  ✓ [{sid}] done, 产物已刷新")
    if ran == 0:
        sys.exit("❌ 没跑任何 step (--from 之后无步骤?)")
    (run_dir / "run.json").write_text(json.dumps(record, indent=2, ensure_ascii=False))
    print(f"=== '{name}' 完成 {ran} 步, trace: {run_dir.relative_to(ROOT)} ===")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="瘦 pipeline 运行器 (线执行器)")
    ap.add_argument("pipeline", help="线名 (对应 _pipelines/_<name>.yml)")
    ap.add_argument("--validate", action="store_true", help="只校验, 不执行")
    ap.add_argument("--from", dest="from_step", default=None, help="从某 step id 续跑")
    ap.add_argument("--allow-locked-write", action="store_true",
                    help="危险: 放行写回 manifest 声明的 LOCK 目录 (默认禁止)")
    args = ap.parse_args()
    manifest = load_manifest(args.pipeline)
    registry = load_registry()
    if args.validate:
        return validate(manifest, registry)
    if validate(manifest, registry) != 0:
        sys.exit("校验未过, 拒绝执行。")
    return run(manifest, registry, args.from_step, args.allow_locked_write)


if __name__ == "__main__":
    raise SystemExit(main())
