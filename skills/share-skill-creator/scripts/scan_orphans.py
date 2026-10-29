#!/usr/bin/env python
"""扫描 skill 的 scripts/ 里的孤儿脚本：没被本 skill 的 .md 引用，也没被已引用脚本 import / 调用。

用法：
  python scan_orphans.py                      # 全扫 ~/.claude/skills/*（SKILLS_DIR 可改，如 ~/.agents/skills）
  python scan_orphans.py <skill目录或名称> ...  # 只扫指定 skill
输出：按 skill 分组列出疑似孤儿，每条给出 size 和候选动作建议。
识别 `from scripts.x import`、`from x import`、`from .x import`、`import scripts.x`、`import x`
以及 shell/JS 里按文件名调用；被已引用脚本间接使用的辅助模块不算孤儿。
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

SKILLS = Path(os.environ.get("SKILLS_DIR", Path.home() / ".claude" / "skills")).expanduser()
SCRIPT_GLOBS = ("*.py", "*.mjs", "*.js", "*.sh")


def uses(text: str, stem: str) -> bool:
    s = re.escape(stem)
    patterns = (
        rf"^\s*from\s+(?:scripts\.|\.)?{s}\s+import\b",
        rf"^\s*import\s+(?:scripts\.)?{s}\b",
        rf"^\s*from\s+(?:scripts|\.)\s+import\s+[^\n]*\b{s}\b",
        rf"require\(\s*['\"]\./{s}",
        rf"\b{s}\.(?:py|mjs|js|sh)\b",
    )
    return any(re.search(p, text, re.MULTILINE) for p in patterns)


def find_imports(scripts_dir: Path, target_stem: str) -> list[str]:
    callers = []
    for pattern in SCRIPT_GLOBS:
        for s in sorted(scripts_dir.glob(pattern)):
            if s.stem == target_stem:
                continue
            try:
                text = s.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if uses(text, target_stem):
                callers.append(s.name)
    return callers


def scan_skill(skill: Path) -> list[tuple[str, int, list[str]]]:
    """Return orphans as (name, size, unreachable callers)."""
    scripts_dir = skill / "scripts"
    if not scripts_dir.is_dir():
        return []
    md_text = ""
    for md in skill.rglob("*.md"):
        try:
            md_text += md.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            pass
    scripts = [
        p for p in sorted(scripts_dir.iterdir())
        if p.is_file() and not p.name.startswith(".") and p.name != "__init__.py"
    ]
    reachable = {
        p.name for p in scripts
        if p.name in md_text or (len(p.stem) > 3 and p.stem in md_text)
    }
    callers = {p.name: find_imports(scripts_dir, p.stem) for p in scripts}
    changed = True
    while changed:  # a helper used by a referenced script is reachable too
        changed = False
        for p in scripts:
            if p.name not in reachable and any(c in reachable for c in callers[p.name]):
                reachable.add(p.name)
                changed = True
    return [(p.name, p.stat().st_size, callers[p.name]) for p in scripts if p.name not in reachable]


def resolve(arg: str) -> Path:
    path = Path(arg).expanduser()
    if path.is_dir():
        return path
    if (SKILLS / arg).is_dir():
        return SKILLS / arg
    raise SystemExit(f"[ERROR] skill not found: {arg}")


def scan(targets: list[Path]) -> int:
    total_orphans = 0
    for skill in targets:
        if not skill.is_dir():
            continue
        orphans = scan_skill(skill)
        if orphans:
            print(f"\n=== {skill.name} ({len(orphans)} 个孤儿) ===")
            for name, size, who in orphans:
                tag = f"只被未引用的 {who} 调用" if who else "无人调用 → 候选死代码"
                print(f"  [{size:>6}B] {name}  — {tag}")
            total_orphans += len(orphans)
    if total_orphans == 0:
        print("✅ 没有孤儿脚本。")
    else:
        print(f"\n共 {total_orphans} 个需要处理。建议：(1) 在 SKILL.md 补引用  (2) 移入 scripts/_archive/  (3) 删除")
    return total_orphans


def main(argv: list[str]) -> int:
    targets = [resolve(a) for a in argv] if argv else sorted(SKILLS.iterdir())
    scan(targets)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
