# _paper/ — 论文源文件与审稿往来

> Git：.tex/.md/.bib、审稿意见与回复全部追踪；编译产物（`*.aux`、`*.log`、`*.synctex.gz`）不追踪；大 PDF（约 >10MB）不追踪。

## 放什么

论文主文件、章节、参考文献、各轮审稿意见与 rebuttal（扁平结构，不分 current/revisions）。

## 不放什么

- 图 → `_figures/`；结果表的数据 → `_outputs/`。
- 按版本号复制的稿件（`main_v2.tex`、`_final`）→ 不建；版本用 Git 提交和 tag。

## 入口

`main.tex`（英文源头）；中文稿若有，写明由谁生成。

## 文件角色

`reviews/round_<NN>_<阶段>/` 放每轮审稿意见与回复；`bib/` 放参考文献。

## 改动原因去哪查

`python3 ~/.claude/skills/share-top/scripts/sixone-cli.py record for-file <文件>`，或 `git log -- <文件>`。
