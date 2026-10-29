#!/usr/bin/env python3
"""rename_wiki_to_underscore.py — upgrade old wiki directory names to v4 underscore paths

把 wiki 目录里所有 .md 文件 + 子目录改名加 `_` 前缀.
同步修改所有 [[wikilink]] / [link](path/xxx.md) / 外部代码引用.

用法:
  python rename_wiki_to_underscore.py --root <project> [--dry-run] [--mode A|B|C]
    --root:     项目根 (默认 cwd)
    --dry-run:  只看会改啥, 不实际改 (默认 false)
    --mode:
      A: 只改 wiki 内部文件/子目录 + wikilink(不改顶级目录名,不改外部引用)
      B: A + 顶级目录 wiki-method... → _wiki-method... + 100+ 外部引用同步(默认)
      C: 只改 6 个顶级 index 文件(轻量版)

设计:
- 文件名只加 `_` 前缀, 不改大小写, 不改 hyphen
- [[xxx]] → [[_xxx]] (xxx 已 _ 开头的跳过)
- [text](path/xxx.md) → [text](_path/_xxx.md)
- 外部引用 (mode B): grep replace 所有项目里其他 .py / .md / .yml / .json / .sh 文件

复用:
- 本脚本设计为「跨项目通用」, 不依赖本项目结构
- 沉淀到 share-top 技能的 references/sub-skills/share-top-upgrade-old/references/migration-tools/
"""
import argparse
import re
import sys
from pathlib import Path
from typing import Iterable

# 字符串常量用 chr() 拼接, 防自己跑时被外部引用扫描扫到自己源码而串改
_W = chr(0x77) + chr(0x69) + chr(0x6B) + chr(0x69)  # "wiki"
WIKI_DIR_NAME = _W + "-methodology"        # 旧顶级目录名(默认值,可改)
NEW_WIKI_DIR_NAME = "_" + WIKI_DIR_NAME    # 新顶级目录名 (mode B)

# Mode C 的 6 个顶级 index 文件
INDEX_FILES_FOR_MODE_C = [
    "CATALOG.md",
    "code-index.md",
    "wiki-index.md",
    "top-index.md",
    "tests-index.md",
    "index.md",
]

# 外部引用扫描:文件扩展名白名单
EXTERNAL_SCAN_EXTS = {".py", ".md", ".yml", ".yaml", ".json", ".sh", ".tex", ".txt"}
# 排除目录(防扫到自己的源码 + 大数据目录)
EXCLUDE_DIRS = {
    ".git", "__pycache__", "node_modules", "_legacy", ".claude/worktrees", ".codex/worktrees",
    "_tmp", ".obsidian", "历史文件", "数据下载",
    "migration",  # ← 关键: 不扫 migration tools 自己 (防字符串常量被串改)
}


def _add_underscore(name: str) -> str:
    """加 _ 前缀.
    - 已 _ 开头 → 不变
    - . 开头(隐藏文件) → 去 . 加 _ (例 .foo → _foo, 不要 _.foo)
    - 其他 → 直接加 _ 前缀
    """
    if name.startswith("_"):
        return name
    if name.startswith("."):
        return "_" + name[1:]
    return "_" + name


# 改名扫描的扩展名 (除 .md, 还要改这些)
RENAMEABLE_EXTS = {".md", ".yml", ".yaml", ".json", ".sh", ".py", ".txt", ".tex"}


def collect_wiki_entries(wiki_root: Path) -> tuple[list[Path], list[Path]]:
    """收集 _wiki-methodology 下所有可改名文件 + 子目录(不含顶级)."""
    files = []
    for p in wiki_root.rglob("*"):
        if p.is_file() and p.suffix in RENAMEABLE_EXTS:
            files.append(p)
    files.sort(key=lambda p: (-len(p.parts), str(p)))

    dirs = []
    for p in sorted(wiki_root.rglob("*"), key=lambda p: -len(p.parts)):
        if p.is_dir() and p != wiki_root:
            dirs.append(p)
    return files, dirs


def build_rename_map(wiki_root: Path) -> dict[Path, Path]:
    """规划所有改名: old_path → new_path. 深的先改 (rglob 从下往上)."""
    rename_map: dict[Path, Path] = {}
    files, dirs = collect_wiki_entries(wiki_root)

    # 先文件 (深的先)
    for old in files:
        new_name = _add_underscore(old.name)
        if new_name != old.name:
            rename_map[old] = old.parent / new_name

    # 再目录 (深的先, 因为子目录里的文件已经规划好了 new_path 是相对老父目录的)
    for old in dirs:
        new_name = _add_underscore(old.name)
        if new_name != old.name:
            rename_map[old] = old.parent / new_name

    return rename_map


def apply_renames(rename_map: dict[Path, Path], dry_run: bool) -> None:
    """实际执行改名 (深优先, 自底向上)."""
    for old, new in rename_map.items():
        if dry_run:
            print(f"  [dry-run] mv {old.relative_to(old.parents[len(old.parts)-2])} → {new.name}")
        else:
            old.rename(new)


def update_wikilinks_in_file(file_path: Path, rename_basenames: set[str], dry_run: bool) -> int:
    """更新单个文件里的 [[wikilink]] 引用.

    rename_basenames: 改过名的文件 basename (不带 .md) 集合.
    Returns: 改了多少处.
    """
    text = file_path.read_text(encoding="utf-8")
    original = text

    def replace_wikilink(match: re.Match) -> str:
        inner = match.group(1).strip()
        # 处理别名: [[xxx|alias]] / [[xxx#section]]
        if "|" in inner:
            target, alias = inner.split("|", 1)
        else:
            target, alias = inner, None
        if "#" in target:
            base, section = target.split("#", 1)
        else:
            base, section = target, None

        base = base.strip()
        if base.startswith("_"):  # 已经 _ 开头, 跳过
            return match.group(0)

        # 改名: 只改 basename
        new_base = "_" + base

        # 重组
        target_part = new_base
        if section:
            target_part += "#" + section
        if alias:
            return f"[[{target_part}|{alias}]]"
        return f"[[{target_part}]]"

    text = re.sub(r"\[\[([^\]]+)\]\]", replace_wikilink, text)

    # 处理 markdown 相对路径 [text](path/xxx.md)
    def replace_md_path(match: re.Match) -> str:
        full = match.group(0)
        text_part = match.group(1)
        path = match.group(2)
        # 路径中每个段都加 _ (跳过已 _ 开头的)
        parts = path.split("/")
        new_parts = []
        for p in parts:
            if p in ("", ".", "..") or p.startswith("_"):
                new_parts.append(p)
            else:
                # 文件 (有扩展名) or 目录都加 _
                new_parts.append("_" + p)
        new_path = "/".join(new_parts)
        return f"[{text_part}]({new_path})"

    text = re.sub(r"\[([^\]]*)\]\(([^)]+\.md)\)", replace_md_path, text)

    if text != original:
        if not dry_run:
            file_path.write_text(text, encoding="utf-8")
        diff_count = sum(1 for a, b in zip(original, text) if a != b)
        return diff_count
    return 0


def update_external_references(
    project_root: Path,
    wiki_dir_old: str,
    wiki_dir_new: str,
    sub_renames: dict[str, str],  # 老子名 → 新子名 (e.g. "wiki" → "_wiki")
    dry_run: bool,
) -> int:
    """扫项目内非 _wiki-methodology 的代码/skill 文件, 批量改外部引用.

    _wiki-methodology/<sub>/ → __wiki-methodology/_<sub>/
    _wiki-methodology → __wiki-methodology

    Returns: 改了多少文件.
    """
    changed_files = 0
    new_wiki_dir = project_root / wiki_dir_new

    for f in project_root.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix not in EXTERNAL_SCAN_EXTS:
            continue
        # 跳过 wiki 内部 (已经在前面处理过)
        try:
            f.relative_to(new_wiki_dir)
            continue
        except ValueError:
            pass
        try:
            f.relative_to(project_root / wiki_dir_old)
            continue
        except ValueError:
            pass

        # 跳过排除目录
        if any(ex in f.parts for ex in EXCLUDE_DIRS):
            continue

        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue
        original = text

        # 替换 _wiki-methodology/<sub>/ 模式 (较长的先)
        for old_sub, new_sub in sorted(sub_renames.items(), key=lambda x: -len(x[0])):
            text = text.replace(f"{wiki_dir_old}/{old_sub}", f"{wiki_dir_new}/{new_sub}")
        # 然后替换裸 _wiki-methodology
        text = text.replace(wiki_dir_old, wiki_dir_new)

        if text != original:
            if not dry_run:
                f.write_text(text, encoding="utf-8")
            changed_files += 1

    return changed_files


def run_mode_A_or_B(project_root: Path, mode: str, dry_run: bool) -> None:
    """Mode A: 改内部. Mode B: A + 顶级 + 外部. """
    wiki_root = project_root / WIKI_DIR_NAME
    if not wiki_root.is_dir():
        print(f"❌ wiki 目录不存在: {wiki_root}", file=sys.stderr)
        sys.exit(1)

    print(f"📂 wiki 根: {wiki_root}")
    print(f"🔧 模式: {mode}, dry-run: {dry_run}\n")

    # Phase 1: 规划改名
    rename_map = build_rename_map(wiki_root)
    print(f"📋 Phase 1: 规划 {len(rename_map)} 个改名")

    md_count = sum(1 for k in rename_map if k.suffix == ".md")
    dir_count = len(rename_map) - md_count
    print(f"  - .md 文件: {md_count}")
    print(f"  - 子目录: {dir_count}\n")

    # 收集所有改名前后的 basename 映射 (不带 .md)
    rename_basenames: set[str] = set()
    sub_renames: dict[str, str] = {}
    for old_path, new_path in rename_map.items():
        if old_path.suffix == ".md":
            rename_basenames.add(old_path.stem)
        elif old_path.is_dir() and old_path.parent == wiki_root:
            # 顶级子目录, 记录给外部引用同步用
            sub_renames[old_path.name] = new_path.name

    # Phase 2: 更新所有 wiki 内 .md 的 wikilink (在改名之前做!)
    print(f"📝 Phase 2: 更新 wiki 内 [[link]] / [path](xxx.md)")
    total_changes = 0
    for f in wiki_root.rglob("*.md"):
        changes = update_wikilinks_in_file(f, rename_basenames, dry_run)
        total_changes += changes
    print(f"  → 改了 {total_changes} 处 link\n")

    # Phase 3: 实际改文件名 / 目录名
    print(f"🔄 Phase 3: 改文件名 / 目录名 ({len(rename_map)} 个)")
    apply_renames(rename_map, dry_run)
    print()

    # Phase 4 (mode B only): 顶级目录改名 + 外部引用
    if mode == "B":
        print(f"🌐 Phase 4 (mode B): 顶级目录改名 + 外部引用同步")
        # 4a: 顶级目录改名 _wiki-methodology → __wiki-methodology
        new_top = project_root / NEW_WIKI_DIR_NAME
        if dry_run:
            print(f"  [dry-run] mv {WIKI_DIR_NAME}/ → {NEW_WIKI_DIR_NAME}/")
        else:
            wiki_root.rename(new_top)
            print(f"  ✓ mv {WIKI_DIR_NAME}/ → {NEW_WIKI_DIR_NAME}/")

        # 4b: 外部引用同步
        # 注意:此时改名已完成, wiki_root 已不存在, 用 new_top 跳过
        if dry_run:
            ext_root = wiki_root  # dry-run 顶级目录还没真改名
        else:
            ext_root = new_top
        changed_files = update_external_references(
            project_root,
            WIKI_DIR_NAME,
            NEW_WIKI_DIR_NAME,
            sub_renames,
            dry_run,
        )
        print(f"  → 改了 {changed_files} 个外部文件\n")

    # Phase 5: 验证
    print(f"✅ 完成 ({'dry-run' if dry_run else '实际改了'})\n")
    print(f"建议下一步验证:")
    if mode == "B":
        target = NEW_WIKI_DIR_NAME
    else:
        target = WIKI_DIR_NAME
    print(f"  1. grep -rE '\\[\\[[^_]' {target}/ | head -5   (找漏掉的非 _ 开头 link)")
    print(f"  2. ls {target}/ | head -5                     (验证文件名)")


def run_mode_C(project_root: Path, dry_run: bool) -> None:
    """Mode C: 只改 6 个顶级 index 文件."""
    wiki_root = project_root / WIKI_DIR_NAME
    if not wiki_root.is_dir():
        print(f"❌ wiki 目录不存在: {wiki_root}", file=sys.stderr)
        sys.exit(1)

    print(f"📂 wiki 根: {wiki_root}")
    print(f"🔧 模式 C (轻量), dry-run: {dry_run}\n")

    rename_map = {}
    rename_basenames = set()
    for idx_name in INDEX_FILES_FOR_MODE_C:
        old = wiki_root / idx_name
        if old.exists():
            new = wiki_root / _add_underscore(idx_name)
            rename_map[old] = new
            rename_basenames.add(old.stem)

    print(f"📋 Mode C: 改 {len(rename_map)} 个 index 文件")
    for old, new in rename_map.items():
        print(f"  {old.name} → {new.name}")
    print()

    # 改 wiki 内所有 link
    total_changes = 0
    for f in wiki_root.rglob("*.md"):
        changes = update_wikilinks_in_file(f, rename_basenames, dry_run)
        total_changes += changes
    print(f"📝 改了 {total_changes} 处 link")

    # 改外部引用 (只对这 6 个文件名)
    changed_files = 0
    for f in project_root.rglob("*"):
        if not f.is_file() or f.suffix not in EXTERNAL_SCAN_EXTS:
            continue
        try:
            f.relative_to(wiki_root)
            continue
        except ValueError:
            pass
        if any(ex in f.parts for ex in EXCLUDE_DIRS):
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue
        original = text
        for idx_name in INDEX_FILES_FOR_MODE_C:
            text = text.replace(idx_name, _add_underscore(idx_name))
        if text != original:
            if not dry_run:
                f.write_text(text, encoding="utf-8")
            changed_files += 1
    print(f"🌐 改了 {changed_files} 个外部文件\n")

    # 实际改文件名
    print(f"🔄 改文件名")
    apply_renames(rename_map, dry_run)
    print(f"\n✅ 完成 ({'dry-run' if dry_run else '实际改了'})")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".", help="项目根 (默认 cwd)")
    p.add_argument("--dry-run", action="store_true", help="只看会改啥, 不实际改")
    p.add_argument("--mode", default="B", choices=["A", "B", "C"], help="A/B/C")
    args = p.parse_args()

    project_root = Path(args.root).resolve()
    if not project_root.is_dir():
        print(f"❌ 项目根不存在: {project_root}", file=sys.stderr)
        return 1

    if args.mode == "C":
        run_mode_C(project_root, args.dry_run)
    else:
        run_mode_A_or_B(project_root, args.mode, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
