# _refs/ — 参考资料

> Git：自己写的阅读笔记追踪；下载的大文件（约 >10MB，能重新下载的）不追踪，记下来源；小而来源可能消失的资料可追踪。

## 放什么

外来的原始资料：论文 PDF、网页存档、标准、准则、截图等，不强制分类。

## 不放什么

- 清洗后给流程用的数据 → `_data/`；只用一次的临时下载 → `_tmp/`。
- 从资料里提炼的知识 → `_wiki-methodology/_wiki/`；引用条目 → `_paper/bib/`。

## 入口

按文件名找；资料多了可按类建子目录（`papers/`、`standards/`），不强制。

## 文件角色

精读完的资料可移到 `_refs/_processed/`（可选）。

## 改动原因去哪查

`python3 ~/.claude/skills/share-top/scripts/sixone-cli.py record for-file <文件>`，或 `git log -- <文件>`。
