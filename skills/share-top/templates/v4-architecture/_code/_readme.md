# _code/ — 正式代码

> Git：全部追踪（写出来的代码）。

## 放什么

主流程会调用的、已验证的项目代码与复用工具，可按领域建子目录（`_code/<domain>/`）。

## 不放什么

- 试验中的代码 → `_sandbox/<日期>-<主题>/`，有优于 baseline 的证据再移进来。
- 按版本号复制的副本（`v2/`、`model_v3.py`、`_final`、`_backup`）→ 不建；版本 = Git 提交和 tag。
- 一次性临时脚本 → `_tmp/`；旧代码 → `_legacy/`。

## 入口

项目入口与跑法写在 `_codemap.md`（或项目 AGENTS.md 的验证命令）；函数、调用关系用 CodeGraph 查（`codegraph explore "<符号>"`）。

## 文件角色

主流程入口、复用工具、对外 API 登记到 `_meta/_registry.yml`；不做函数级账本。

## 改动原因去哪查

`python3 ~/.claude/skills/share-top/scripts/sixone-cli.py record for-file <文件>`，或 `git log -- <文件>`。
