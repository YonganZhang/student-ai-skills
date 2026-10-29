#!/usr/bin/env python3
"""把单文件的 design-taste-frontend SKILL.md 按章节拆成"核心 + references/"。

为什么: 上游是一个 87KB 的单文件, 调用一次就整份进上下文并一直跟着走。
拆开后核心只留每次都要用的章节, 其余按触发条件读取。原文逐字搬运, 不改写。

用法: python3 split_taste.py <上游单文件 SKILL.md> <输出目录>
      输出目录写 SKILL.md.template 和 references/*.md。从上游刷新模板后重跑即可。
上游新增章节时本脚本会报错退出, 在 REFS / CORE 里给新章节指定去处后再跑。
"""
import re
import sys
from pathlib import Path

DESCRIPTION = '"落地页、作品集、营销页与整体改版设计（landing/portfolio/redesign）。这些场景优先本技能，不与 frontend-design 同用；后台、数据表和多步业务界面不触发。"'
CORE = [0, 1, 2, 3, 13]
REFS = {
    "visual-directives.md": [4, 8],
    "ai-tells.md": [9],
    "motion-performance.md": [5, 6, 7],
    "redesign.md": [11],
    "vocabulary.md": [10],
    "block-library.md": [12],
    "appendices.md": ["appendices"],
    "preflight.md": [14],
}
ROUTING = """## 本地拆分：按需读取（原文逐字搬运，章节号与上游一致）

正文里的 "Section N" 在下表对应文件中。先读本文件，再按触发条件读对应文件，不要一次全读：

| 文件 | 上游章节 | 什么时候读 |
|---|---|---|
| `references/visual-directives.md` | 4 设计工程指令、8 深色模式 | 写任何页面样式前（排版、配色、布局硬规则、图片、信息密度） |
| `references/ai-tells.md` | 9 AI 味禁用清单 | 定稿文案与视觉前 |
| `references/motion-performance.md` | 5 动效骨架、6 性能与无障碍、7 旋钮定义 | 加动效或滚动效果，或要按数值理解三个旋钮时 |
| `references/redesign.md` | 11 重设计协议 | 改造已有页面时，第一步就读 |
| `references/vocabulary.md` | 10 模式词汇 | 给 hero、导航、卡片等选型或命名时 |
| `references/block-library.md` | 12 组件块库契约 | 往块库写组件时 |
| `references/appendices.md` | 附录 A–C | 要设计系统安装命令、官方来源或 Liquid Glass 近似实现时 |
| `references/preflight.md` | 14 交付前检查 | **每次交付前必读并逐条过** |

---

"""

HEADING = re.compile(r"^## (\d+)\. ")
FENCE = re.compile(r"^\s*(```|~~~)")


def split(text):
    assert text.startswith("---\n"), "缺 frontmatter"
    end = text.index("\n---\n", 4) + 5
    front, body = text[:end], text[end:]
    segments, key, buf, in_fence = [], "preamble", [], False
    for line in body.splitlines(keepends=True):
        if FENCE.match(line):
            in_fence = not in_fence
        m = None if in_fence else HEADING.match(line)
        if m or (not in_fence and line.startswith("# APPENDICES")):
            segments.append((key, "".join(buf)))
            key, buf = (int(m.group(1)) if m else "appendices"), []
        buf.append(line)
    segments.append((key, "".join(buf)))
    assert "".join(s for _, s in segments) == body, "拆分不无损"
    if "## 本地拆分" in body:
        sys.exit("输入已是拆分后的文件，请给上游单文件")
    return front, dict(segments), [k for k, _ in segments]


def main(src, out):
    front, seg, order = split(Path(src).read_text(encoding="utf-8"))
    mapped = {"preamble", *CORE, *(k for ks in REFS.values() for k in ks)}
    unmapped = [k for k in order if k not in mapped]
    if unmapped:
        sys.exit(f"上游出现未分配的章节: {unmapped}，先在 CORE/REFS 指定去处")
    front = re.sub(r"(?m)^description: .*$", lambda _: f"description: {DESCRIPTION}", front, count=1)
    out = Path(out)
    (out / "references").mkdir(parents=True, exist_ok=True)
    core = front + seg["preamble"] + ROUTING + "".join(seg[k] for k in order if k in CORE)
    (out / "SKILL.md.template").write_text(core, encoding="utf-8")
    for name, keys in REFS.items():
        label = "、".join("附录" if k == "appendices" else f"§{k}" for k in keys)
        head = f"<!-- 拆自 design-taste-frontend SKILL.md {label}，原文未改，拆分脚本见 share-project-provision/scripts/split_taste.py -->\n\n"
        (out / "references" / name).write_text(head + "".join(seg[k] for k in order if k in keys), encoding="utf-8")
    sizes = {p.name: p.stat().st_size for p in [out / "SKILL.md.template", *sorted((out / "references").glob("*.md"))]}
    for n, s in sizes.items():
        print(f"{s:7d}  {n}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
