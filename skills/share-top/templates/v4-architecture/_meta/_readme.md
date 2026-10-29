# _meta/ — 项目账本

> Git：全部追踪（写出来的登记与说明）。

## 放什么

按需启用的登记：`_registry.yml`（主流程入口、复用工具、对外 API）、`_data_registry.yml`（数据与外部资产）、`_runs.yml`（跑次）、`_naming.md`（命名约定）。

## 不放什么

- 当前进度与任务 → `_wiki-methodology/_top/_task_plan.md`；长知识正文 → `_wiki-methodology/_wiki/`。
- 改动历史 → Git；调用关系 → CodeGraph。不在这里手抄。

## 入口

找代码/工具看 `_registry.yml`，找数据看 `_data_registry.yml`。

## 文件角色

各登记之间只用 key 互相指（`code:<id>`、`data:<id>`），不复制正文。

## 改动原因去哪查

`python3 ~/.claude/skills/share-top/scripts/sixone-cli.py record for-file <文件>`，或 `git log -- <文件>`。
