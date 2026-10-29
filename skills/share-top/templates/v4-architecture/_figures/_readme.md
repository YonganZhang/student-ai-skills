# _figures/ — 论文 / 汇报用图

> Git：绘图脚本全部追踪；小的终稿图追踪；大图（约 >10MB）不追踪，由脚本重新生成。

## 放什么

论文、PPT 用的图，以及生成每张图的脚本（图和脚本同名，如 `fig_01_map.png` + `fig_01_map.py`）。

## 不放什么

- 调试中随手画的图 → `_sandbox/` 或 `_tmp/`。
- 画图用的数据 → `_outputs/`（脚本从那里读）。

## 入口

要重画某张图：运行同名 `.py`。

## 文件角色

脚本开头注明读哪个结果文件、图出现在论文/PPT 的哪里；其余一眼能看懂的不写。

## 改动原因去哪查

`python3 ~/.claude/skills/share-top/scripts/sixone-cli.py record for-file <文件>`，或 `git log -- <文件>`。
