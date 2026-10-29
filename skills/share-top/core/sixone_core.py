"""sixone CLI core — share-top 脚本 JSON envelope 的复用逻辑。

设计:
- 不造第二真源: 状态真源 = 现有 TOP 文件; 本层只 shell out 脚本 --json + 读 registry。
- 逻辑写一次: 本文件纯函数(可直接单测),日常入口是 scripts/sixone-cli.py。
- describe/project_list/topic_status/topic_map 仅保留为 CLI/单测函数;
  扣子视图的语义落点 = brief 的 pipelines 字段 + Read manifest。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
# 项目注册表(id → path); 不收 raw path 当权威(跨 cwd + 防误指)。
REGISTRY_FILE = Path.home() / ".claude" / "_sixone-projects.yml"

VERDICT_ENUM = ("ok", "warn", "block", "stale")  # 'stale' 由聚合层补(P2/closeout)
CONTRACT_VERSION = "sixone-cli/v1"


def _run_json(script: str, project: Path, *extra: str) -> dict[str, Any]:
    """跑 share-top 脚本的 --json, 解析 envelope。失败 fail-loud 成 {error}。"""
    try:
        out = subprocess.run(
            [sys.executable, str(SCRIPTS / script), str(project), "--json", *extra],
            capture_output=True, text=True, timeout=60,
        )
        if out.returncode not in (0, 1):  # doctor 用 1 表示 block, 仍是合法输出
            return {"error": f"{script} exit {out.returncode}", "stderr": out.stderr[:500]}
        return json.loads(out.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
        return {"error": f"{script} failed: {type(e).__name__}: {e}"}


def load_registry() -> dict[str, dict]:
    """读 id→{path,...} 注册表。无文件 → 空(project_list 会提示如何注册)。"""
    if not REGISTRY_FILE.is_file():
        return {}
    data = yaml.safe_load(REGISTRY_FILE.read_text(encoding="utf-8")) or {}
    return data.get("projects", {})


def resolve(id_or_path: str) -> Path | None:
    """id → 注册路径; 否则当本地 path 解析(本地同信任边界, 可接受)。"""
    reg = load_registry()
    if id_or_path in reg:
        return Path(reg[id_or_path]["path"])
    p = Path(id_or_path).expanduser()
    return p if p.is_dir() else None


def project_list() -> dict[str, Any]:
    """列已知六合一项目 + 各自 phase/profile/bootstrap 状态。"""
    reg = load_registry()
    projects = []
    for pid, meta in reg.items():
        path = Path(meta["path"])
        brief = _run_json("topic-brief.py", path) if path.is_dir() else {"error": "path missing"}
        projects.append({
            "id": pid,
            "path": str(path),
            "profile": brief.get("profile"),
            "bootstrap_needed": brief.get("bootstrap_needed", True),
        })
    return {"schema_version": CONTRACT_VERSION, "tool": "project_list",
            "registry_file": str(REGISTRY_FILE), "projects": projects,
            "hint": None if reg else f"无项目登记; 在 {REGISTRY_FILE} 写 projects:{{<id>:{{path:...}}}}"}


def _codebook_scan(path: Path) -> list[dict[str, str]]:
    """扫 _codebook/ 节点 + 实时派生 trust(brief/doctor 共用, 一份逻辑防漂)。
    跳 _ 前缀(_index.md/_schema.md 是导航/模板, 不是盖章节点)。"""
    cb_dir = path / "_codebook"
    nodes: list[dict[str, str]] = []
    if cb_dir.is_dir():
        for node in sorted(cb_dir.rglob("*.md")):
            if node.name.startswith("_"):
                continue
            nodes.append({"node": str(node.relative_to(path)), "trust": codebook_trust(node, path)})
    return nodes


def _gates_manifest(path: Path) -> Path:
    return path / "_wiki-methodology" / "_tests" / "_gates.yml"


def _gates_ids(path: Path) -> list[str] | None:
    """读 COL3 gates manifest 的 gate id 清单; 无 manifest → None(区别于空清单)。"""
    f = _gates_manifest(path)
    if not f.is_file():
        return None
    try:
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return []
    return [str(g.get("id")) for g in (data.get("gates") or []) if isinstance(g, dict) and g.get("id")]


def topic_brief(id_or_path: str) -> dict[str, Any]:
    """冷启动握手工具: 脚本 brief envelope + codebook/pipelines/gates 摘要 + next_hint。
    提示长在返回里(six-in-one-philosophy.md §3 第 2 条), 不靠 AI 记外部规矩。"""
    path = resolve(id_or_path)
    if path is None:
        return {"error": f"unknown project: {id_or_path}"}
    env = _run_json("topic-brief.py", path)
    if "error" in env:
        return env
    nodes = _codebook_scan(path)
    bad = [n for n in nodes if n["trust"] != "fresh"]
    env["codebook"] = {"total": len(nodes), "needs_attention": len(bad), "entry": "_codebook/"}
    pls = _pipeline_scan(path)  # 印记健康度: 每条 live trust(2026-06-15)
    pl_stale = [p for p in pls if p["trust"] in ("stale", "broken")]
    env["pipelines"] = {"total": len(pls), "stale": len(pl_stale),
                        "entry": "_pipelines/", "items": pls}
    gates = _gates_ids(path)
    env["gates"] = {"manifest": str(_gates_manifest(path).relative_to(path)),
                    "declared": gates if gates is not None else "missing"}
    ver, latest = env.get("sixone_version"), env.get("sixone_latest")
    env["codebook"]["retired"] = True  # 2026-09-24: 只读参考, 不再要求 deposit 盖章
    if pl_stale:
        env["next_hint"] = (f"{len(pl_stale)} 条 pipeline 印记失效(step 代码改过)"
                            " → 对照 step 代码复核, 改完 verify-pipeline 盖章")
    elif ver and latest and ver != latest:
        env["next_hint"] = (f"架构版本 {ver} < 最新 {latest} → 走 share-top references/upgrades/ 阶梯升级"
                            "(判定版本→逐级 delta 清单→doctor 验收)")
    else:
        env["next_hint"] = ("写码前用 CodeGraph(codegraph explore)+ _codemap.md 找现成代码; "
                            "改文件前 record for-file 查相关决策; 完成用 plan complete --commit")
    return env


def topic_status(id_or_path: str) -> dict[str, Any]:
    path = resolve(id_or_path)
    if path is None:
        return {"error": f"unknown project: {id_or_path}"}
    return _run_json("top-status.py", path)


def topic_doctor(id_or_path: str, links: bool = True, full: bool = False) -> dict[str, Any]:
    """ledger_doctor: 账本可信 verdict + **CodeBook 节点新鲜度(实时派生)**(templates/codebook/_node_schema.md「doctor 派生 trust」)。
    聚合 topic-doctor.py(registry/SSOT 悬空边)+ _codebook/ 每节点 trust。"""
    path = resolve(id_or_path)
    if path is None:
        return {"error": f"unknown project: {id_or_path}"}
    env = _run_json("topic-doctor.py", path, *(["--links"] if links else []), *([] if full else ["--core"]))
    if "error" in env:  # 子进程崩 → fail-loud, 不静默返回 ok
        return {**env, "verdict": "block", "next_hint": "topic-doctor 跑挂了, 先修工具"}
    if not full:
        # 默认 doctor 不查 CodeBook 新鲜度与 pipeline 印记(2026-09-24 机主决定移出):
        # 它们在老项目上长期报 stale 却无人处理, 只会淹没真问题; 需要时用 --full。
        return {**env, "codebook": {"skipped": "only with --full"}, "pipelines": {"skipped": "only with --full"}}
    # CodeBook 新鲜度(三方共识最高 ROI: 守最易漂移层)
    nodes = _codebook_scan(path)
    bad = [n for n in nodes if n["trust"] in ("stale", "broken", "unverified")]
    # Pipeline 印记(2026-06-15): stale(代码改过)→gate; broken(ref 解析不了)→warn;
    # unverified(没盖过)不计 → 不破坏没 opt-in 的项目/新线。
    pls = _pipeline_scan(path)
    pl_stale = [p for p in pls if p["trust"] == "stale"]
    # 审查修(MED 向后兼容): broken 只在"曾盖过章后变 broken"才 warn; 从未盖过的 broken
    # = WIP/骨架(ref 指向未登记 id), 跟 unverified 一样豁免, 不让老项目 ok→warn。
    pl_broken = [p for p in pls if p["trust"] == "broken" and p.get("stamped")]
    # _index.md(TOC, 不盖章)双向检查: 死链→warn(把 AI 导进墙), 漏列/缺 TOC→info。
    # 注入 env["issues"] 时同步 summary 计数, 保 envelope 自洽(verdict/summary/issues 三者一致)。
    index_issues: list[dict[str, str]] = []
    index_file = path / "_codebook" / "_index.md"
    node_rels = {n["node"] for n in nodes}
    if index_file.is_file():
        listed = set()
        for m in re.finditer(r"\]\(([^)#]+)", index_file.read_text(encoding="utf-8")):
            rel = m.group(1).strip()
            if not rel or rel.startswith(("http://", "https://", "mailto:")):
                continue
            listed.add(str((Path("_codebook") / rel)) if not rel.startswith("_codebook/") else rel)
        for rel in sorted(listed - node_rels):
            if not (path / rel).exists():
                index_issues.append({"severity": "warn", "code": "CODEBOOK_INDEX_DEAD_LINK",
                                     "path": "_codebook/_index.md", "message": f"TOC 指向不存在的节点: {rel}"})
        for rel in sorted(node_rels - listed):
            index_issues.append({"severity": "info", "code": "CODEBOOK_INDEX_MISSING_ENTRY",
                                 "path": "_codebook/_index.md", "message": f"节点未列入 TOC: {rel}"})
    elif len(nodes) >= 2:
        index_issues.append({"severity": "info", "code": "CODEBOOK_INDEX_ABSENT",
                             "path": "_codebook/", "message": f"{len(nodes)} 个节点但无 _index.md TOC"})
    if index_issues:
        env["issues"] = list(env.get("issues", [])) + index_issues
        summary = dict(env.get("summary", {}))
        for issue in index_issues:
            summary[issue["severity"]] = summary.get(issue["severity"], 0) + 1
        env["summary"] = summary
    # verdict 聚合: doctor 自身 + codebook(broken→block, stale/unverified→至少 stale)+ index 死链→至少 warn
    base = env.get("verdict", "ok")
    order = {"ok": 0, "warn": 1, "stale": 2, "block": 3, "broken": 3}
    cb_verdict = "ok"
    if any(n["trust"] == "broken" for n in bad):
        cb_verdict = "block"
    elif bad:
        cb_verdict = "stale"
    elif any(i["severity"] == "warn" for i in index_issues):
        cb_verdict = "warn"
    # pipeline verdict: stale→stale(gate), broken→warn
    pl_verdict = "stale" if pl_stale else ("warn" if pl_broken else "ok")
    verdict = base
    for v in (cb_verdict, pl_verdict):
        if order.get(v, 0) > order.get(verdict, 0):
            verdict = v
    # next_hint: CodeBook 优先, 其次 pipeline 印记, 否则保留 doctor 自身 hint
    next_hint = env.get("next_hint")
    if bad:
        next_hint = f"{len(bad)} 个 CodeBook 节点 stale/broken → 读节点对照 tracked 文件复核, 改完调 deposit_validate"
    elif pl_stale:
        names = ", ".join(p["pipeline"] for p in pl_stale[:3])
        next_hint = f"{len(pl_stale)} 条 pipeline 印记失效(step 代码改过): {names} → verify-pipeline 重核盖章"
    elif any(i["code"] == "CODEBOOK_INDEX_DEAD_LINK" for i in index_issues):
        next_hint = "_codebook/_index.md 有死链 → 修 TOC 行(节点改名/删除后 TOC 没跟上)"
    return {**env, "verdict": verdict,
            "codebook": {"total": len(nodes), "needs_attention": bad},
            "pipelines": {"total": len(pls), "stale": len(pl_stale), "broken": len(pl_broken), "items": pls},
            "next_hint": next_hint}


def topic_map(id_or_path: str) -> dict[str, Any]:
    """扣子视图: registry 里 role∈{step,entry} 的函数(pipeline-registration-paradigm.md §11 默认只露扣子, 非完整目录)。"""
    path = resolve(id_or_path)
    if path is None:
        return {"error": f"unknown project: {id_or_path}"}
    reg_file = path / "_meta" / "_registry.yml"
    if not reg_file.is_file():
        return {"schema_version": CONTRACT_VERSION, "tool": "topic_map",
                "buttons": [], "note": "no _meta/_registry.yml"}
    data = yaml.safe_load(reg_file.read_text(encoding="utf-8")) or {}
    buttons = [
        {"id": f.get("id"), "role": f.get("role"), "pipeline": f.get("pipeline"),
         "needs": f.get("needs"), "produces": f.get("produces"), "module": f.get("module")}
        for f in data.get("functions", [])
        if f.get("role") in ("step", "entry")
    ]
    return {"schema_version": CONTRACT_VERSION, "tool": "topic_map",
            "total_functions": len(data.get("functions", [])), "buttons": buttons}


# ───────────────────── CodeBook: deposit_validate + hash-trust 引擎 (契约: templates/codebook/_node_schema.md) ─────────────────────
import hashlib
import re

VALIDATOR_VERSION = 1
_NODE_TEMPLATE = """---
title: <一句话: 这个系统/模块是什么>
user_workflow: <用户视角它怎么被用>
owner_refs:
  - code:<function_id>
tracked_paths_hint:
  - <relative/path.py>
---
<正文: 自顶而下, 每节"干嘛 + owner 路径">
"""


def _as_list(v: Any) -> list[str]:
    """容错: None→[]; 标量→[标量]; list→list。修"忘了写 - 导致逐字符遍历"(三方共识)。"""
    if v is None:
        return []
    if isinstance(v, (str, int, float)):
        return [str(v)]
    if isinstance(v, list):
        return [str(x) for x in v]
    return []


def _split_frontmatter(text: str) -> tuple[dict, str, str]:
    """返回 (frontmatter_dict, frontmatter_raw, body)。无 frontmatter → ({}, '', text)。
    body 只剥**一个**分隔换行(不 lstrip 全部, 防吞用户空行 — 三方共识数据丢失修)。"""
    if not text.startswith("---\n"):
        return {}, "", text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, "", text
    raw = text[4:end]
    body = text[end + 4:]
    if body.startswith("\n"):
        body = body[1:]
    try:
        fm = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        fm = {"__unreadable__": True}
    return (fm if isinstance(fm, dict) else {}), raw, body


def _safe_tracked(rel: str, root: Path) -> tuple[Path | None, str | None]:
    """校验 tracked 路径: 必须相对、不越界、是文件。返回 (path|None, error|None)。
    堵"目录/绝对路径/.. → 不进 hash → 假 fresh"(Codex+Gemini 共识 forgery 洞)。"""
    if not rel or not isinstance(rel, str):
        return None, "tracked 路径必须是非空字符串"
    if Path(rel).is_absolute() or ".." in Path(rel).parts:
        return None, f"tracked 路径必须相对且不含 ..: {rel}"
    p = (root / rel)
    try:
        p.resolve().relative_to(root.resolve())
    except ValueError:
        return None, f"tracked 路径越出项目根: {rel}"
    if not p.is_file():
        return None, f"tracked 必须是存在的文件(非目录): {rel}"
    return p, None


def _node_hash(fm: dict, body: str, root: Path) -> str:
    """sha256(已校验 frontmatter 子集 + 正文 + 各 tracked 文件内容)。
    **绑 frontmatter**: 改 owner_refs/title 后 hash 变→stale(修 Codex"戳未绑校验元数据")。
    只 hash 合法 is_file 的 tracked → 目录/越界不贡献字节但已被 _safe_tracked 在校验层挡掉。"""
    import json
    h = hashlib.sha256()
    subset = {k: fm.get(k) for k in ("title", "user_workflow", "owner_refs", "tracked_paths_hint")}
    h.update(json.dumps(subset, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    h.update(b"\0body\0")
    h.update(body.encode("utf-8"))
    for rel in sorted(_as_list(fm.get("tracked_paths_hint"))):
        p, err = _safe_tracked(rel, root)
        if p is not None:
            h.update(b"\0")
            h.update(p.read_bytes())
    return h.hexdigest()


def _resolve_owner_ref(ref: str, root: Path) -> bool:
    """code:<id>→registry(只按 id, 不按 name 防歧义) / pipeline:<id> / test:<id>。
    🔴 解析键集必须与 topic-doctor.collect_resource_decls 一致(两套解析器打架 = bug):
    code 认 registry 全部 code 键(entries/functions/...);pipeline 认 canonical `pipeline:`
    字段 + `id` + 文件名(老式 `_<id>.yml` 兼容)。"""
    if ":" not in ref:
        return False
    kind, val = ref.split(":", 1)
    if kind == "code":
        reg = root / "_meta" / "_registry.yml"
        if not reg.is_file():
            return False
        data = yaml.safe_load(reg.read_text(encoding="utf-8")) or {}
        # 对齐 topic-doctor 的 code 键集(单一命名空间,不能 deposit/doctor 各认一套)
        for key in ("entries", "functions", "entrypoints", "plugin_tools",
                    "scenarios", "contract_tests", "code_domains"):
            items = data.get(key)
            if isinstance(items, list) and any(
                    isinstance(it, dict) and it.get("id") == val for it in items):
                return True
        return False
    if kind == "pipeline":
        pdir = root / "_pipelines"
        if pdir.is_dir():
            # 对齐 doctor:canonical `pipeline:` 字段 + `id` + 文件名 stem 任一命中即可
            for path in sorted(pdir.glob("*.yml")) + sorted(pdir.glob("*.yaml")):
                try:
                    d = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                except Exception:
                    d = {}
                if val in (d.get("pipeline"), d.get("id"), path.stem.lstrip("_")):
                    return True
        return (root / "_pipelines" / f"_{val}.yml").is_file() or (root / "_pipelines" / f"{val}.yml").is_file()
    if kind == "test":
        # 统一命名空间: test:<id> = COL3 gates manifest 的 gate id(单一真源,
        # 三套测试 id 空间打架是审查实锤)。旧 _tests/_monitor/<id>.py 兼容保留。
        ids = _gates_ids(root)
        if ids and val in ids:
            return True
        return (root / "_tests" / "_monitor" / f"{val}.py").is_file()
    return False


_FENCE_RE = re.compile(r"```.*?```|`[^`]*`", re.DOTALL)


def _closed_set_checks(fm: dict, body: str, root: Path, node_dir: Path) -> list[dict]:
    """闭集校验(_node_schema.md「deposit_validate 闭集校验」)。severity: a/b=block, c=broken, d=warn。明确不做散文匹配代码。"""
    errors = []
    # a) schema: 必填 + 类型(owner_refs/tracked 必须是 list 或可强转)
    for field in ("title", "user_workflow", "owner_refs", "tracked_paths_hint"):
        if not fm.get(field):
            errors.append({"check": "a_schema", "field": field, "detail": f"缺必填字段 {field}"})
    for field in ("owner_refs", "tracked_paths_hint"):
        v = fm.get(field)
        if v is not None and not isinstance(v, list):
            errors.append({"check": "a_schema", "field": field, "detail": f"{field} 必须是 YAML 列表(每行 - 开头), 现是 {type(v).__name__}"})
    # b) owner_refs 可解析
    for ref in _as_list(fm.get("owner_refs")):
        if not _resolve_owner_ref(ref, root):
            errors.append({"check": "b_owner_ref", "field": ref, "detail": f"owner_ref 解析不了(code 按 id): {ref}"})
    # c) tracked 必须是相对、不越界、存在的文件
    for rel in _as_list(fm.get("tracked_paths_hint")):
        _, err = _safe_tracked(rel, root)
        if err:
            errors.append({"check": "c_tracked_missing", "field": rel, "detail": err})
    # d) markdown 本地断链(node 相对; 去 code fence/title/fragment; warn 不挡盖章)
    stripped = _FENCE_RE.sub("", body)
    for m in re.finditer(r"\]\(([^)]+)\)", stripped):
        target = m.group(1).strip()
        if target.startswith("<") and target.endswith(">"):
            target = target[1:-1]
        target = target.split()[0] if target.split() else target  # 去 "title"
        target = target.split("#", 1)[0]                            # 去 #fragment
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        from urllib.parse import unquote
        link = unquote(target)
        if not (node_dir / link).exists() and not (root / link).exists():
            errors.append({"check": "d_dead_link", "field": link, "detail": f"断链: {link}"})
    return errors


def deposit_validate(id_or_path: str, node_rel: str) -> dict[str, Any]:
    """[已退役 2026-09-24] CLI `deposit` 不再调用本函数(只输出退役提示); 仅保留给旧测试/库调用。
    原语义: AI 正常 Edit 完 CodeBook 节点后调它: 闭集校验 → 唯一写 last_verified_hash。
    失败返回模板 + 哪条错(actionable)。是唯一能写 last_verified_hash 的工具(防伪造)。"""
    root = resolve(id_or_path)
    if root is None:
        return {"error": f"unknown project: {id_or_path}"}
    node = root / node_rel
    if not node.is_file():
        return {"verdict": "block", "errors": [{"check": "exists", "detail": f"节点不存在: {node_rel}"}],
                "template": _NODE_TEMPLATE}
    text = node.read_text(encoding="utf-8")
    fm, raw, body = _split_frontmatter(text)
    if fm.get("__unreadable__") or not raw:
        return {"verdict": "block", "errors": [{"check": "a_schema", "detail": "frontmatter 缺失/不可读"}],
                "template": _NODE_TEMPLATE}
    errors = _closed_set_checks(fm, body, root, node.parent)
    blocking = [e for e in errors if e["check"] in ("a_schema", "b_owner_ref", "c_tracked_missing")]
    if blocking:
        # 阻断级失败: 不盖章 + 剥除手写的 last_verified_hash(防伪造存活)
        fm.pop("last_verified_hash", None)
        fm.pop("validator_version", None)
        _write_node(node, fm, body)
        worst = "broken" if any(e["check"] == "c_tracked_missing" for e in blocking) else "block"
        return {"verdict": worst, "errors": errors, "template": _NODE_TEMPLATE,
                "next_hint": "按 errors 逐条修(模板见 template), 再调 deposit_validate"}
    # 通过(warn 级断链不挡盖章): 工具唯一盖章(底层 I/O, 不走 Edit 工具)
    sha = _node_hash(fm, body, root)
    fm["last_verified_hash"] = sha
    fm["validator_version"] = VALIDATOR_VERSION
    _write_node(node, fm, body)
    return {"verdict": "warn" if errors else "ok", "stamped": sha, "node": node_rel,
            "errors": errors, "next_hint": "已盖章; 该节点 doctor 现为 fresh" + ("(有断链 warn)" if errors else "")}


def _write_node(node: Path, fm: dict, body: str) -> None:
    """底层 I/O 写回节点(frontmatter + body)。不走 Edit 工具 → 不自触发 PostToolUse。"""
    fm_yaml = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).rstrip()
    node.write_text(f"---\n{fm_yaml}\n---\n{body}", encoding="utf-8")


def codebook_trust(node: Path, root: Path) -> str:
    """doctor 用: 实时派生 trust(不读存盘 trust)。见 _node_schema.md「doctor 派生 trust」。"""
    if not node.is_file():
        return "broken"
    fm, raw, body = _split_frontmatter(node.read_text(encoding="utf-8"))
    if fm.get("__unreadable__") or not raw:
        return "broken"
    for rel in _as_list(fm.get("tracked_paths_hint")):
        if _safe_tracked(rel, root)[0] is None:   # is_file + 越界检查
            return "broken"
    for ref in _as_list(fm.get("owner_refs")):
        if not _resolve_owner_ref(ref, root):
            return "broken"
    stamped = fm.get("last_verified_hash")
    if not stamped:
        return "unverified"
    return "fresh" if _node_hash(fm, body, root) == stamped else "stale"


# ───────── Pipeline: 印记 hash-trust 引擎(2026-06-15 · CodeBook 引擎横向移植)─────────
# why: CodeBook 早有"代码变→自动 stale"(_node_hash 含 tracked 文件内容 + live 重算),
# 但 pipeline 的 verified_at 是裸日期不绑代码 → 改 step 代码不会自动失效。这里把同款
# hash-trust 横移给 pipeline:tracked 集合 = 各 step ref 解析到的代码文件。现无项目用真
# manifest(只 _readme 骨架)→ 纯附加。codegraph 不进本引擎(它会 stale);核心印记只用
# git + 内容 hash 保持 robust,codegraph 仅在 affected() 当顾问。
_PIPELINE_CODE_KEYS = ("entries", "functions", "entrypoints", "plugin_tools",
                       "scenarios", "contract_tests", "code_domains")
# 契约 hash 用黑名单(2026-06-15 审查修): 排除人读字段, 其余 wiring 字段(含
# condition/optional/entry_role/未来新增)全纳入 → 改接线语义即失效, 不漏。
_STEP_HUMAN_FIELDS = frozenset({"desc", "comment", "note", "title"})


def _load_registry_dict(root: Path) -> dict:
    reg = root / "_meta" / "_registry.yml"
    if not reg.is_file():
        return {}
    try:
        return yaml.safe_load(reg.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _registry_path_for(ref: Any, registry: dict) -> str | None:
    """pipeline step ref → 代码文件相对路径(按 registry id 反查;对齐 _resolve_owner_ref 键集)。
    ref 形如 'code:<id>' / 'cmd:<id>' / 'fn:<id>' / 裸 '<id>';取冒号后值再比 id。"""
    if not isinstance(ref, str) or not ref:
        return None
    val = ref
    if ":" in ref:
        prefix, rest = ref.split(":", 1)
        if prefix in ("code", "cmd", "fn") and rest:
            val = rest
    for key in _PIPELINE_CODE_KEYS:
        for it in (registry.get(key) or []):
            if isinstance(it, dict) and it.get("id") == val:
                p = it.get("path")
                return p if isinstance(p, str) and p else None
    return None


def _pipeline_step_files(manifest: dict, registry: dict) -> tuple[list[str], list[str]]:
    """(可解析的代码文件相对路径, 解析不了的 ref)。"""
    files: list[str] = []
    unresolved: list[str] = []
    for step in (manifest.get("steps") or []):
        if not isinstance(step, dict):
            continue
        ref = step.get("ref")
        if not ref:
            continue
        p = _registry_path_for(ref, registry)
        if p:
            files.append(p)
        else:
            unresolved.append(str(ref))
    return files, unresolved


def _pipeline_hash(manifest: dict, root: Path, registry: dict) -> str:
    """sha256(线契约子集 + 各 step 代码文件内容)。改 step 代码 / 改接线 → hash 变。
    契约子集只含 identity+wiring,不含 verified_*/desc 等人读字段(改注释不误判 stale)。"""
    h = hashlib.sha256()
    subset = {
        "pipeline": manifest.get("pipeline") or manifest.get("id"),
        "steps": [
            {k: v for k, v in s.items() if k not in _STEP_HUMAN_FIELDS}
            for s in (manifest.get("steps") or []) if isinstance(s, dict)
        ],
    }
    h.update(json.dumps(subset, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    h.update(b"\0steps\0")
    files, _ = _pipeline_step_files(manifest, registry)
    for rel in sorted(set(files)):
        p, _err = _safe_tracked(rel, root)
        if p is not None:
            h.update(b"\0")
            h.update(p.read_bytes())
    return h.hexdigest()


def _find_pipeline(root: Path, name: str) -> Path | None:
    pdir = root / "_pipelines"
    if not pdir.is_dir():
        return None
    for path in sorted(pdir.glob("*.yml")) + sorted(pdir.glob("*.yaml")):
        try:
            d = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            d = {}
        if isinstance(d, dict) and name in (d.get("pipeline"), d.get("id"), path.stem.lstrip("_")):
            return path
    return None


def pipeline_trust(manifest_path: Path, root: Path) -> str:
    """live 派生 pipeline 印记(不读存盘),与 codebook_trust 同心智:
    broken=ref/代码文件解析不了 · unverified=没盖过 · fresh=指纹匹配 ·
    stale=指纹不匹配(step 代码或接线改过)。"""
    if not manifest_path.is_file():
        return "broken"
    try:
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return "broken"
    if not isinstance(manifest, dict):
        return "broken"
    registry = _load_registry_dict(root)
    files, unresolved = _pipeline_step_files(manifest, registry)
    if unresolved:
        return "broken"
    for rel in files:
        if _safe_tracked(rel, root)[0] is None:
            return "broken"
    stamped = manifest.get("verified_steps_hash")
    if not stamped:
        return "unverified"
    return "fresh" if _pipeline_hash(manifest, root, registry) == stamped else "stale"


def _pipeline_scan(root: Path) -> list[dict]:
    """扫 _pipelines/*.yml,每条 live 派生 trust;只收有 steps 的真 manifest(骨架/_readme 不算)。"""
    pdir = root / "_pipelines"
    if not pdir.is_dir():
        return []
    out = []
    for path in sorted(pdir.glob("*.yml")) + sorted(pdir.glob("*.yaml")):
        try:
            d = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            d = {}
        if not isinstance(d, dict) or not d.get("steps"):
            continue
        out.append({
            "pipeline": d.get("pipeline") or d.get("id") or path.stem,
            "manifest": str(path.relative_to(root)),
            "trust": pipeline_trust(path, root),
            "stamped": bool(d.get("verified_steps_hash")),  # 区分 WIP-broken vs 盖过章后变 broken
        })
    return out


def _git_head(root: Path) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def _git_rev_exists(root: Path, rev: str) -> bool:
    try:
        r = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "-q", rev],
                           capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def _yaml_set_scalar(text: str, key: str, value: str) -> str:
    """顶层标量 key 外科式更新(保留注释/结构/行尾,不 reformat 整 YAML)。
    存在→只替换值部分(保 \\r 行尾, CRLF 不被吃);不存在→末尾追加。只动行首无缩进顶层键。
    限制(审查记):不处理"多行双引号值里恰好顶格出现 key:"的极端情形——机器键名
    (verified_steps_hash/verified_at_commit)不会出现在人写多行值里,实践安全。"""
    pat = re.compile(rf"(?m)^({re.escape(key)}:)[^\r\n]*")
    if pat.search(text):
        return pat.sub(lambda m: f"{m.group(1)} {value}", text, count=1)
    return text.rstrip("\n") + f"\n{key}: {value}\n"


def _yaml_del_scalar(text: str, key: str) -> str:
    """删顶层标量 key 整行(含 \\r\\n 行尾)。无 count → 删全部(防伪:剥任何手写印记/去重复键)。"""
    return re.sub(rf"(?m)^{re.escape(key)}:[^\r\n]*\r?\n?", "", text)


def verify_pipeline(id_or_path: str, name: str) -> dict[str, Any]:
    """改完 step 代码/接线后调它:校验 ref/代码文件可解析 → 唯一盖 verified_steps_hash +
    verified_at_commit。是唯一能写印记的工具(手填一律剥除,防伪同 deposit)。"""
    root = resolve(id_or_path)
    if root is None:
        return {"error": f"unknown project: {id_or_path}"}
    mpath = _find_pipeline(root, name)
    if mpath is None:
        return {"verdict": "block",
                "errors": [{"check": "exists", "detail": f"找不到 pipeline manifest: {name}(查 _pipelines/)"}]}
    text = mpath.read_text(encoding="utf-8")
    try:
        manifest = yaml.safe_load(text) or {}
    except Exception as e:
        return {"verdict": "broken", "errors": [{"check": "yaml", "detail": f"manifest YAML 不可读: {e}"}]}
    if not isinstance(manifest, dict):
        manifest = {}
    registry = _load_registry_dict(root)
    files, unresolved = _pipeline_step_files(manifest, registry)
    errors = []
    if not manifest.get("steps"):
        errors.append({"check": "schema", "detail": "manifest 无 steps,不是可印记的线"})
    for ref in unresolved:
        errors.append({"check": "ref", "field": ref, "detail": f"step ref 在 registry 解析不到(按 id): {ref}"})
    for rel in files:
        _, err = _safe_tracked(rel, root)
        if err:
            errors.append({"check": "tracked", "field": rel, "detail": err})
    # 审查修(MED): 有 steps 但没一个绑到 registry 代码 → 拒绝盖章(否则空 hash 假 fresh,
    # 印记永不随代码失效, 是最危险的假阳性)。
    if manifest.get("steps") and not files and not unresolved:
        errors.append({"check": "no_code",
                       "detail": "所有 step 都没绑到 registry 代码文件(无 ref),印记不会随代码失效 → 给 step 加 ref 指向 registry 代码 id"})
    if errors:
        stripped = _yaml_del_scalar(_yaml_del_scalar(text, "verified_steps_hash"), "verified_at_commit")
        if stripped != text:
            mpath.write_text(stripped, encoding="utf-8")
        return {"verdict": "broken", "errors": errors,
                "next_hint": "按 errors 修 step ref/代码路径,再调 verify-pipeline"}
    sha = _pipeline_hash(manifest, root, registry)
    # 审查修(HIGH): 先 del 两键(防 PyYAML 重复键"取最后一个"与盖章口"改第一处"打架 →
    # 刚盖完就 stale),再追加唯一一行; head=None 时不留旧 commit(已 del),状态自洽。
    new = _yaml_del_scalar(_yaml_del_scalar(text, "verified_steps_hash"), "verified_at_commit")
    new = _yaml_set_scalar(new, "verified_steps_hash", sha)
    head = _git_head(root)
    if head:
        new = _yaml_set_scalar(new, "verified_at_commit", head)
    mpath.write_text(new, encoding="utf-8")
    return {"verdict": "ok", "stamped": sha, "pipeline": name,
            "next_hint": "已盖 pipeline 印记; step 代码一改即自动 stale,doctor 会拦"}


def _codegraph_status(root: Path) -> dict[str, Any]:
    """Machine-readable CodeGraph health. Missing/stale is advisory, never forged fresh."""
    result: dict[str, Any] = {
        "available": False,
        "fresh": False,
        "note": "codegraph unavailable; using direct owner matching",
    }
    try:
        run = subprocess.run(
            ["codegraph", "status", "-j", str(root)],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        result["note"] = f"codegraph status failed: {type(exc).__name__}"
        return result
    if run.returncode != 0:
        result["note"] = f"codegraph status exit {run.returncode}; using direct owner matching"
        return result
    try:
        data = json.loads(run.stdout)
    except json.JSONDecodeError:
        result["note"] = "codegraph status returned invalid JSON; using direct owner matching"
        return result
    pending = data.get("pendingChanges") or {}
    pending_total = sum(int(pending.get(key) or 0) for key in ("added", "modified", "removed"))
    reindex = bool((data.get("index") or {}).get("reindexRecommended"))
    mismatch = data.get("worktreeMismatch")
    fresh = bool(data.get("initialized")) and pending_total == 0 and not mismatch and not reindex
    result.update({
        "available": True,
        "fresh": fresh,
        "version": data.get("version"),
        "last_indexed": data.get("lastIndexed"),
        "pending_changes": pending,
        "worktree_mismatch": mismatch,
        "reindex_recommended": reindex,
        "note": (
            "codegraph JSON health is fresh"
            if fresh else
            "codegraph has pending/mismatched/reindex state; graph results are clues only"
        ),
    })
    return result


def _path_class(rel: str) -> str:
    normalized = rel.lstrip("./")
    if normalized.startswith(("_outputs/", "_figures/")):
        return "evidence"
    if normalized.startswith(("_legacy/", "_tmp/", "_sandbox/")):
        return "legacy_or_temp"
    if normalized.startswith(("external/", "vendor/", "vendors/", "third_party/")):
        return "external_or_vendor"
    return "active"


def _codegraph_affected_tests(root: Path, files: list[str]) -> list[str]:
    if not files:
        return []
    try:
        run = subprocess.run(
            ["codegraph", "affected", "-j", "-p", str(root), "--stdin"],
            input="\n".join(files) + "\n", capture_output=True, text=True, timeout=20,
        )
        if run.returncode != 0:
            return []
        data = json.loads(run.stdout)
        return sorted({str(path) for path in (data.get("affectedTests") or [])})
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return []


def _codegraph_impacts(root: Path, symbols: list[str], depth: int = 2) -> dict[str, list[dict[str, Any]]]:
    partitions: dict[str, list[dict[str, Any]]] = {
        "active": [], "evidence": [], "legacy_or_temp": [], "external_or_vendor": [],
    }
    seen: set[tuple[str, str, int]] = set()
    for symbol in symbols:
        try:
            run = subprocess.run(
                ["codegraph", "impact", "-j", "-p", str(root), "-d", str(depth), symbol],
                capture_output=True, text=True, timeout=20,
            )
            if run.returncode != 0:
                continue
            data = json.loads(run.stdout)
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            continue
        for entry in data.get("affected") or []:
            rel = str(entry.get("filePath") or "")
            if not rel:
                continue
            key = (rel, str(entry.get("name") or ""), int(entry.get("startLine") or 0))
            if key in seen:
                continue
            seen.add(key)
            partitions[_path_class(rel)].append({
                "symbol": symbol,
                "name": entry.get("name"),
                "kind": entry.get("kind"),
                "path": rel,
                "line": entry.get("startLine"),
            })
    return partitions


def _registry_hits_for_paths(registry: dict, paths: set[str]) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for key in _PIPELINE_CODE_KEYS:
        for entry in registry.get(key) or []:
            if not isinstance(entry, dict):
                continue
            path = entry.get("path") or entry.get("module")
            item_id = entry.get("id")
            if isinstance(path, str) and path in paths and item_id:
                marker = (str(item_id), path)
                if marker not in seen:
                    seen.add(marker)
                    hits.append({"id": str(item_id), "path": path, "registry_key": key})
    return hits


def _registry_entries_for_ids(registry: dict, item_ids: set[str]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for key in _PIPELINE_CODE_KEYS:
        for entry in registry.get(key) or []:
            if isinstance(entry, dict) and str(entry.get("id")) in item_ids:
                hits.append({"registry_key": key, "entry": entry})
    return hits


def _pipeline_manifests_for_ids(root: Path, pipeline_ids: set[str]) -> list[tuple[Path, dict]]:
    hits: list[tuple[Path, dict]] = []
    pdir = root / "_pipelines"
    if not pdir.is_dir():
        return hits
    for path in sorted(pdir.glob("*.yml")) + sorted(pdir.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
        if not isinstance(data, dict):
            continue
        identities = {str(data.get("pipeline") or ""), str(data.get("id") or ""), path.stem.lstrip("_")}
        if identities & pipeline_ids:
            hits.append((path, data))
    return hits


def _gate_entries_for_refs(root: Path, gate_refs: list[str]) -> list[dict[str, Any]]:
    wanted = {
        value.split(":", 1)[1] if ":" in value and value.split(":", 1)[0] in {"gate", "test"} else value
        for value in gate_refs
    }
    path = root / "_wiki-methodology" / "_tests" / "_gates.yml"
    if not path.is_file():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    return [entry for entry in data.get("gates") or [] if isinstance(entry, dict) and str(entry.get("id")) in wanted]


def affected(
    id_or_path: str,
    since: str | None = None,
    *,
    task_id: str | None = None,
    task_scopes: list[str] | None = None,
    task_gates: list[str] | None = None,
) -> dict[str, Any]:
    """Diff/task scope → owner, pipeline, test, and CodeGraph advisory impact."""
    root = resolve(id_or_path)
    if root is None:
        return {"error": f"unknown project: {id_or_path}"}
    # 审查修(HIGH): 默认 HEAD~1 而非 HEAD —— diff HEAD 只看工作树, 漏掉"刚提交"的改动
    # (AI 常先 commit 再问 affected → 空清单把"忘回写"伪装成"没啥要写")。HEAD~1 = HEAD~1
    # vs 工作树, 覆盖"最近一次提交 + 未提交"。无 HEAD~1(首个 commit)退回 HEAD。
    if since:
        base = since
    else:
        base = "HEAD~1" if _git_rev_exists(root, "HEAD~1") else "HEAD"
    try:
        r = subprocess.run(["git", "-C", str(root), "diff", "--name-only", base],
                           capture_output=True, text=True, timeout=10)
        changed = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()] if r.returncode == 0 else []
    except Exception as e:
        return {"error": f"git diff 失败: {e}"}
    changed_set = set(changed)
    declared_paths: list[str] = []
    declared_symbols: list[str] = []
    declared_registry_ids: set[str] = set()
    declared_pipeline_ids: set[str] = set()
    for scope in task_scopes or []:
        if scope.startswith("path:"):
            value = scope.split(":", 1)[1]
            if value and not Path(value).is_absolute() and ".." not in Path(value).parts:
                declared_paths.append(value)
        elif scope.startswith("symbol:"):
            value = scope.split(":", 1)[1]
            if value:
                declared_symbols.append(value)
        elif scope.startswith("registry:") or scope.startswith("code:"):
            value = scope.split(":", 1)[1]
            if value:
                declared_registry_ids.add(value)
        elif scope.startswith("pipeline:"):
            value = scope.split(":", 1)[1]
            if value:
                declared_pipeline_ids.add(value)

    registry = _load_registry_dict(root)
    direct_registry = _registry_entries_for_ids(registry, declared_registry_ids)
    declared_tests: set[str] = set()
    for hit in direct_registry:
        entry = hit["entry"]
        path = entry.get("path") or entry.get("module")
        if isinstance(path, str) and path not in declared_paths:
            declared_paths.append(path)
        declared_tests.update(str(value) for value in _as_list(entry.get("tests")))
    direct_pipelines = _pipeline_manifests_for_ids(root, declared_pipeline_ids)
    for path, manifest in direct_pipelines:
        rel_path = str(path.relative_to(root))
        if rel_path not in declared_paths:
            declared_paths.append(rel_path)
    resolved_gates = _gate_entries_for_refs(root, list(task_gates or []))
    for gate in resolved_gates:
        command = str(gate.get("cmd") or "")
        declared_tests.update(re.findall(r"(?:^|\s)([\w./-]*test[\w./-]*\.py)(?=\s|$)", command))

    cg = _codegraph_status(root)
    impacts = {
        "active": [], "evidence": [], "legacy_or_temp": [], "external_or_vendor": [],
    }
    if cg["fresh"] and declared_symbols:
        impacts = _codegraph_impacts(root, declared_symbols)
    active_impact_paths = {entry["path"] for entry in impacts["active"]}

    def overlaps_scope(path: str, scopes: set[str]) -> bool:
        return any(path == scope or path.startswith(scope.rstrip("/") + "/") or scope.startswith(path.rstrip("/") + "/") for scope in scopes)

    scope_paths = set(declared_paths) | active_impact_paths
    scope_bound = bool(task_id and (task_scopes or task_gates))
    task_relevant_changed = {path for path in changed_set if overlaps_scope(path, scope_paths)} if scope_bound else changed_set
    candidate_paths = task_relevant_changed | scope_paths

    # 直接反查:CodeBook 节点 tracked_paths_hint / pipeline step 代码文件 命中候选影响面
    cb_hits, pl_hits = [], []
    cb_dir = root / "_codebook"
    if cb_dir.is_dir():
        for node in sorted(cb_dir.rglob("*.md")):
            if node.name.startswith("_"):
                continue
            fm, raw, _body = _split_frontmatter(node.read_text(encoding="utf-8"))
            tracked = set(_as_list(fm.get("tracked_paths_hint")))
            if tracked & candidate_paths:
                cb_hits.append(str(node.relative_to(root)))
    pdir = root / "_pipelines"
    if pdir.is_dir():
        for path in sorted(pdir.glob("*.yml")) + sorted(pdir.glob("*.yaml")):
            try:
                d = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except Exception:
                d = {}
            if not isinstance(d, dict) or not d.get("steps"):
                continue
            sfiles, _ = _pipeline_step_files(d, registry)
            if set(sfiles) & candidate_paths:
                pl_hits.append({"pipeline": d.get("pipeline") or d.get("id") or path.stem,
                                "trust": pipeline_trust(path, root)})
    for path, manifest in direct_pipelines:
        pipeline_id = manifest.get("pipeline") or manifest.get("id") or path.stem.lstrip("_")
        if not any(str(entry.get("pipeline")) == str(pipeline_id) for entry in pl_hits):
            pl_hits.append({"pipeline": pipeline_id, "trust": pipeline_trust(path, root)})
    active_seed_files = sorted({path for path in candidate_paths if _path_class(path) == "active"})
    affected_tests = _codegraph_affected_tests(root, active_seed_files) if cg["fresh"] else []
    affected_tests = sorted(set(affected_tests) | declared_tests)
    registry_hits = _registry_hits_for_paths(registry, candidate_paths)
    for hit in direct_registry:
        entry = hit["entry"]
        path = entry.get("path") or entry.get("module")
        marker = (str(entry.get("id")), str(path or ""))
        if path and not any((str(row.get("id")), str(row.get("path"))) == marker for row in registry_hits):
            registry_hits.append({"id": str(entry.get("id")), "path": str(path), "registry_key": hit["registry_key"]})
    cg["declared_symbols"] = declared_symbols
    cg["impacts"] = impacts
    cg["affected_tests"] = affected_tests
    return {
        "changed_files": changed, "since": base,
        "task_relevant_changed_files": sorted(task_relevant_changed),
        "task_id": task_id,
        "declared_paths": declared_paths,
        "declared_registry_ids": sorted(declared_registry_ids),
        "declared_pipeline_ids": sorted(declared_pipeline_ids),
        "declared_gates": list(task_gates or []),
        "gates_resolved": resolved_gates,
        "codebook_nodes_to_rewrite": cb_hits,
        "pipelines_affected": pl_hits,
        "registry_entries_affected": registry_hits,
        "tests_suggested": affected_tests,
        "codegraph": cg,
        "codebook_retired": True,  # 命中的旧 CodeBook 节点只作只读参考, 不必回写/盖章
        "next_hint": (
            f"影响面命中 pipeline={len(pl_hits)} registry={len(registry_hits)} tests={len(affected_tests)}"
            + (f" (旧 CodeBook 节点 {len(cb_hits)} 个, 已退役只读)" if cb_hits else "")
            + " → 回写 owner 并验证"
            if (cb_hits or pl_hits or registry_hits or affected_tests)
            else "未命中已登记 owner; 若是新代码先登记，图谱结果仍需源码复核"),
    }


def describe() -> dict[str, Any]:
    """live help(CLI/单测用): 工具契约 + verdict 语义。"""
    tools = {
        "topic_brief": {"purpose": "冷启动握手: 30s whole picture + codebook/pipelines/gates + next_hint",
                        "inputs": {"id": "project id/path"}, "side_effects": "none", "registered": True},
        "topic_doctor": {"purpose": "账本+CodeBook 可信度 verdict + drift + TOC 检查",
                         "inputs": {"id": "...", "links": "bool"}, "side_effects": "none", "registered": True},
        "deposit_validate": {"purpose": "CodeBook 节点闭集校验 + 唯一盖 last_verified_hash",
                             "inputs": {"id": "...", "node": "_codebook/<x>.md"},
                             "side_effects": "写节点 frontmatter(唯一合法写入方)", "registered": True},
        "plan": {"purpose": "Active Work 恢复、校验和原子 CRUD",
                 "inputs": {"id": "project id/path", "task_id": "P<N>.<leaf>"},
                 "side_effects": "CAS 更新 _task_plan.md", "registered": True},
        "record": {"purpose": "finding/decision/review/log 结构化增查",
                   "inputs": {"id": "...", "kind": "..."},
                   "side_effects": "add 写对应 TOP owner；list/show 只读", "registered": True},
        "owner": {"purpose": "六列 owner 和 typed-ref 只读定位",
                  "inputs": {"id": "...", "ref": "typed ref"},
                  "side_effects": "none", "registered": True},
        "affected": {"purpose": "git/task scope + CodeGraph + owner 影响分析",
                     "inputs": {"id": "...", "task": "optional task id"},
                     "side_effects": "none", "registered": True},
        "project_list": {"purpose": "列已知六合一项目", "inputs": {}, "side_effects": "none", "registered": False},
        "topic_status": {"purpose": "当前 phase(brief 已覆盖)", "inputs": {"id": "..."}, "side_effects": "none", "registered": False},
        "topic_map": {"purpose": "扣子视图(语义落点=brief.pipelines + Read manifest)", "inputs": {"id": "..."}, "side_effects": "none", "registered": False},
        "sixone_describe": {"purpose": "本帮助(读 SKILL.md 即可)", "inputs": {}, "side_effects": "none", "registered": False},
    }
    return {
        "schema_version": CONTRACT_VERSION,
        "help": {
            "schema_version": "sixone-help/v1",
            "refresh_policy": "启动 / 部署后 / schema mismatch 后重读",
            "verdict_semantics": {
                "enum": list(VERDICT_ENUM),
                "gate": "stale|block 时写/操作工具拒绝(remediation 豁免: 修账本本身的写放行)",
            },
            "tools": tools,
            "scope": "LOCAL CLI only; 状态真源=现有 TOP 文件",
            "phase": "plan=当前任务控制面；brief/doctor=六列可信度；deposit/verify-pipeline=防伪盖章",
        },
    }
