# _sandbox/ — 试验区

> Git：试验代码与配置追踪（防丢）；试验跑出来的输出目录（`outputs/`、`_outputs/`）不追踪。

## 放什么

改算法、换参数、试替代做法：每个试验一个子目录 `_sandbox/<YYYY-MM-DD>-<主题>/`。

## 不放什么

- 主流程代码 → `_code/`、`_pipelines/`；沙盒不改主流程和 `_outputs/`。
- 按版本号复制的主流程副本 → 不建，要改就在这里建试验子目录。

## 入口

进对应日期主题子目录，看它自己的说明或脚本。

## 文件角色

有优于 baseline 的证据 → 代码移到 `_code/` 或 `_pipelines/`，登记并写 finding；没用 → 移到 `_legacy/`。结论写进 TOP 记录。

## 改动原因去哪查

`python3 ~/.claude/skills/share-top/scripts/sixone-cli.py record for-file <文件>`，或 `git log -- <文件>`。
