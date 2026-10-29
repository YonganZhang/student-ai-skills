#!/usr/bin/env python3
"""
lint-fs.py — Five-Column FS layer health check

检查当前项目（或指定 --project）是否符合 share-top FS / legacy triplet 规范：
  (a) 每个启用三件套的资产目录必须有 LEDGER.md
  (b) 每条 LEDGER 条目至少一个 wiki 反链
  (c) directory-map.md 列出的每个目录，对应 wiki 页必须存在

用法：
    lint-fs.py --check              # 只报告问题，退出码 0/1
    lint-fs.py --fix                # 交互式补条目（尚未实现，占位）
    lint-fs.py --project <path>     # 指定项目根，默认 CWD
"""

from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path


def find_project_root(start: Path) -> Path:
    p = start.resolve()
    for parent in [p, *p.parents]:
        if (parent / "_wiki-methodology").is_dir() or (parent / "wiki-methodology").is_dir():
            return parent
    return p


def check_ledger_files(project: Path) -> list[str]:
    """R(a): 每个启用三件套的目录必须有 LEDGER.md。
    判据：目录下同时存在 current/ 和 archive/，则视为启用三件套。"""
    issues = []
    for current_dir in project.rglob("current"):
        if not current_dir.is_dir():
            continue
        if "legacy" in current_dir.parts or "_scratch" in current_dir.parts:
            continue
        asset_dir = current_dir.parent
        if not (asset_dir / "archive").is_dir():
            continue
        if not (asset_dir / "LEDGER.md").is_file():
            issues.append(f"[R-a] 缺 LEDGER.md：{asset_dir.relative_to(project)}")
    return issues


WIKI_LINK_RE = re.compile(r"\[\[(?:_?wiki(?:-methodology)?|wiki)[/ ][^\]]+\]\]")


def check_ledger_backlinks(project: Path) -> list[str]:
    """R(b): 每条 LEDGER 条目（以 `- ` 开头的块）至少一个 wiki 反链。"""
    issues = []
    for ledger in project.rglob("LEDGER.md"):
        if "legacy" in ledger.parts:
            continue
        text = ledger.read_text(encoding="utf-8", errors="ignore")
        # 粗拆条目：每条以 "- `" 开头到下一个 "- `" 或 "## " 或 EOF
        entries = re.split(r"(?m)^(?=- `)", text)
        for i, entry in enumerate(entries):
            if not entry.strip().startswith("- `"):
                continue
            # 废弃段跳过
            if "## 已废弃" in text[: text.index(entry)] and "- `" in entry:
                continue
            if not WIKI_LINK_RE.search(entry):
                first_line = entry.splitlines()[0][:80]
                issues.append(
                    f"[R-b] LEDGER 条目缺 wiki 反链：{ledger.relative_to(project)} → {first_line}"
                )
    return issues


def check_directory_map_wiki_targets(project: Path) -> list[str]:
    """R(c): directory-map.md 每个目录行引用的 wiki 页必须存在。"""
    issues = []
    if (project / "_wiki-methodology" / "_fs" / "directory-map.md").is_file():
        dmap = project / "_wiki-methodology" / "_fs" / "directory-map.md"
        wiki_root = project / "_wiki-methodology" / "_wiki"
    elif (project / "wiki-methodology" / "fs" / "directory-map.md").is_file():
        dmap = project / "wiki-methodology" / "fs" / "directory-map.md"
        wiki_root = project / "wiki-methodology" / "wiki"
    else:
        return []
    text = dmap.read_text(encoding="utf-8", errors="ignore")
    for match in WIKI_LINK_RE.finditer(text):
        link = match.group(0).strip("[]")
        # 形如 "wiki/topics/figures-governance" → *_wiki/topics/figures-governance.md
        parts = link.split("/", 1)
        if len(parts) < 2:
            continue
        rel = parts[1]
        rel = rel.lstrip("_")
        target = wiki_root / f"{rel}.md"
        if not target.is_file():
            issues.append(
                f"[R-c] directory-map 引用的 wiki 页不存在：[[{link}]] → 期望 {target.relative_to(project)}"
            )
    return issues


def parse_issue(s: str) -> tuple[str, str, str]:
    """从 issue 字符串提取 (rule, path, detail)。"""
    m = re.match(r"\[(R-[abc])\]\s*(.+)", s)
    if not m:
        return ("?", "", s)
    rule, body = m.group(1), m.group(2)
    parts = re.split(r"[：:]\s*", body, maxsplit=1)
    if len(parts) == 2:
        rest = parts[1]
        if " → " in rest:
            path, detail = rest.split(" → ", 1)
        else:
            path, detail = rest, ""
        return (rule, path.strip(), detail.strip())
    return (rule, "", body)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="只报告（默认）")
    ap.add_argument("--fix", action="store_true", help="交互式补条目（未实现）")
    ap.add_argument("--project", type=Path, default=Path.cwd(), help="项目根目录")
    ap.add_argument("--format", choices=["text", "tsv"], default="text",
                    help="输出格式;tsv 给下游脚本(tidy.sh)消费,字段: rule<TAB>path<TAB>detail")
    args = ap.parse_args()

    if args.fix:
        print("[lint-fs] --fix 模式尚未实现。先用 --check 定位问题，手动修复。", file=sys.stderr)
        return 2

    project = find_project_root(args.project)

    issues: list[str] = []
    issues.extend(check_ledger_files(project))
    issues.extend(check_ledger_backlinks(project))
    issues.extend(check_directory_map_wiki_targets(project))

    if args.format == "tsv":
        # TSV: 仅数据行,无表头/装饰;空 = 全部通过
        # 路径理论可能含 \t / \n,转义为字面字符防止下游 awk/read 错位
        def _esc(s: str) -> str:
            return s.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")
        for issue in issues:
            rule, path, detail = parse_issue(issue)
            print(f"{_esc(rule)}\t{_esc(path)}\t{_esc(detail)}")
        return 0 if not issues else 1

    print(f"[lint-fs] 项目根：{project}")
    if not issues:
        print("[lint-fs] ✅ 通过：FS 层规范健康")
        return 0
    print(f"[lint-fs] ❌ 发现 {len(issues)} 条问题：")
    for i in issues:
        print(f"  - {i}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
