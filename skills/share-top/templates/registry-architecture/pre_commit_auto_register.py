#!/usr/bin/env python3
"""v8.11 pre-commit 自动补 registry (Gemini R15 反模式建议 — 替代 post-commit).

Gemini 原话: post-commit 改 _registry.yml 后留 dirty 工作区 = 反模式, 开发者会暴躁.
修: 改 pre-commit, 扫本次将 commit 的代码 → 填字段 → git add _registry.yml 进同次 commit.

跑法: .git/hooks/pre-commit 调用 (install_hooks.sh 安装)
"""
from __future__ import annotations
import re
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("⚠️  pre-commit hook 需要 pyyaml, 跳过 (pip install pyyaml)")
    sys.exit(0)

REPO = Path(__file__).resolve().parent.parent.parent
REGISTRY = REPO / "_meta" / "_registry.yml"


def run_git(*args) -> str:
    try:
        r = subprocess.run(["git", *args], capture_output=True, text=True, cwd=str(REPO), timeout=10)
        return r.stdout.strip()
    except Exception:
        return ""


def check_rm_violation() -> None:
    """v9.1 R-B 推: 阻塞 git rm staged 文件 (v9.0 红线 1: 删 = mv _legacy/).

    例外: _legacy/ 子树 / __pycache__/ / *.pyc / .gitignore 屏蔽的.
    """
    import sys
    deleted = run_git("diff", "--cached", "--name-only", "--diff-filter=D")
    if not deleted:
        return
    violations = []
    for f in deleted.splitlines():
        if not f:
            continue
        if f.startswith("_legacy/") or f.startswith("__pycache__/"):
            continue
        if f.endswith((".pyc", ".pyo")):
            continue
        violations.append(f)
    if violations:
        print("🔴 v9.0 红线 1 (删=mv _legacy/) — 当前 staged D 文件:", file=sys.stderr)
        for v in violations:
            print(f"   - {v}", file=sys.stderr)
        print(f"\n建议: git restore --staged <file> && mv <file> _legacy/{__import__('datetime').date.today().isoformat()}_<name>/", file=sys.stderr)
        print("(临时真不要 = git rm 不阻塞 _legacy/ 子树 / __pycache__/ / *.pyc)", file=sys.stderr)
        sys.exit(1)


def get_staged_new_funcs() -> set[tuple[str, str]]:
    """扫 staged (将 commit) 代码找新 +def. 返 (module_path, func_name)."""
    diff = run_git("diff", "--cached", "--name-only")
    if not diff:
        return set()
    py_files = [f for f in diff.splitlines() if f.endswith(".py") and not f.startswith(".git/")]
    if not py_files:
        return set()
    new_funcs = set()
    for f in py_files:
        out = run_git("diff", "--cached", "--", f)
        for line in out.splitlines():
            # v8.11 R16 修: 支持 async def + class method 缩进
            m = re.match(r"^\+\s*(async\s+)?def ([a-z_][a-z0-9_]*)\s*\(", line)
            if m:
                new_funcs.add((f, m.group(2)))
    return new_funcs


def get_commit_msg() -> str:
    """pre-commit 时 commit message 在 .git/COMMIT_EDITMSG."""
    msg_file = REPO / ".git" / "COMMIT_EDITMSG"
    if msg_file.exists():
        try:
            return msg_file.read_text(encoding="utf-8").strip().split("\n")[0]
        except Exception:
            pass
    return "(commit message 未取到)"


def main() -> int:
    # v9.1 R-B 推: rm 检测先跑 (即使 _registry.yml 不存在也要挡 rm 红线)
    check_rm_violation()

    if not REGISTRY.exists():
        return 0

    new_funcs = get_staged_new_funcs()
    if not new_funcs:
        return 0

    msg = get_commit_msg()

    # 跑 register.py --scan 让新函数入 registry
    register_py = REPO / "_code" / "register.py"
    if register_py.exists():
        try:
            subprocess.run(["python3", str(register_py), "--scan"],
                          capture_output=True, text=True, cwd=str(REPO), timeout=30)
        except Exception:
            pass

    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    funcs = data.get("functions", [])

    updated = 0
    promoted = 0
    for entry in funcs:
        n = entry.get("name")
        mod = entry.get("module")
        if (mod, n) not in new_funcs:
            continue
        cur_why = entry.get("why") or entry.get("description") or ""
        if not cur_why or cur_why.startswith("TODO") or "TODO" in cur_why[:10]:
            entry["why"] = msg[:150]
            updated += 1
        # pre-commit 还没 commit, wired_up_in 留待 post-commit 回填
        # (或玩家手动: git log -1 --pretty=%h)
        if entry.get("status") == "stub":
            entry["status"] = "wip"
            promoted += 1
        if any(kw in msg.lower() for kw in ["接入", "wire", "integrate", "落地", "wired"]):
            if entry.get("status") in ("stub", "wip", None):
                entry["status"] = "active"
                promoted += 1

    if updated or promoted:
        with open(REGISTRY, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False, width=200)
        # v8.11 Gemini P0: 自动 git add 让 registry 改动进同次 commit, 不留 dirty
        subprocess.run(["git", "add", str(REGISTRY)], cwd=str(REPO), timeout=10)
        print(f"[hook] pre-commit auto-register: 补 {updated} 字段 / promote {promoted} status, 已 git add 进本次 commit")

    # v8.12 R15+R16 P0: 主动推 cc 看健康状态 (不靠 CLAUDE.md hint cc 主动查 — 推 > 拉)
    total = len(funcs)
    if total > 0:
        active = sum(1 for f in funcs if f.get("status") == "active")
        stub = sum(1 for f in funcs if f.get("status") in ("stub", None))
        with_why = sum(1 for f in funcs if f.get("why") and not str(f.get("why", "")).startswith("TODO"))
        print(f"[registry] {total} 函数 · active={active} stub={stub} · why 填充={with_why*100//total}% · 跑 `python3 _code/_query_registry.py --report` 看详情")
    return 0


if __name__ == "__main__":
    sys.exit(main())


def pre_commit_test_v811():
    """v8.11 测 pre-commit 真起作用 — 期望本次 commit 自动带上 _registry.yml 改动."""
    return "v8.11 pre-commit test"


def pre_commit_test_v811_pure():
    """v8.11 卸 post-commit 后纯 pre-commit 真测 — 期望 git add 进同次 commit, 0 dirty."""
    return "纯 pre-commit"


async def async_test_v811():
    """v8.11 R16 修后测 — async def 应该被新 regex 捕获."""
    return "async"


async def v811_2_async_full_test():
    """v8.11.2 完整链测 — register.py + hook regex 都修后, async def 期望自动填全."""
    return "v8.11.2"
