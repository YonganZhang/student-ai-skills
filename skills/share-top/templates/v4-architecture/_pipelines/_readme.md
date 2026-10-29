# _pipelines/ — 主流程

> Git：全部追踪（写出来的代码与配置）。

## 放什么

跑得通的正式流程，一条流程一个子目录（`01_<动词_名词>/`），每步一个文件（`step_<NN>_<动词>_<名词>.py`）。

## 不放什么

- 运行结果 → `_outputs/<运行>/`。
- 试验中的改法 → `_sandbox/<日期>-<主题>/`，有证据再并入。
- 按版本号复制的流程目录 → 不建；版本 = Git 提交和 tag。

## 入口

每条流程子目录的 README 写怎么跑；主流程入口同时登记到 `_meta/_registry.yml` 和 `_codemap.md`。

## 文件角色

设计理由写 `_wiki-methodology/_wiki/` 或决策记录，这里只链接。

## 改动原因去哪查

`python3 ~/.claude/skills/share-top/scripts/sixone-cli.py record for-file <文件>`，或 `git log -- <文件>`。
