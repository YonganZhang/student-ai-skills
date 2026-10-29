# AGENTS.md 项目入口规范

适用:使用 share-top / 六合一架构的项目级 agent 入口文件。

## 定位

**`AGENTS.md` 是唯一项目说明**，Claude 与 Codex 共读。新项目只生成它；同目录没有 `CLAUDE.md` 时，当前 Claude Code 原生读取 `AGENTS.md`。平台特有内容在同一文件中标明适用平台。

`AGENTS.md` 只写项目身份、不变约束和真源入口指针。它会被模型优先加载,所以必须短、稳定、低漂移。

已有项目按本文「迁移旧入口」合并有效指令并退役 `CLAUDE.md`。初始化器不迁移旧说明，也不覆盖用户文件。

它不承载:

- 当前进展记录:归 `task_plan.md`
- 代码地图:归 `_codemap.md` / `_meta/_registry.yml`
- 数据手册:归 `_meta/_data_registry.yml`
- 知识库:归 `_wiki-methodology/_wiki/`
- 测试协议:归 `_wiki-methodology/_tests/`
- 历史事故展开:归 `_wiki-methodology/_top/_findings/`

## 推荐模板

`AGENTS.md`（≤60 行；模板即 `templates/minimal/AGENTS.md`，`init-research.sh` 默认生成）:

```markdown
# <项目名>

<一句话：项目目标与交付物>

## 模式
- 类型：<research | software>
- 我在哪：`python3 ~/.claude/skills/share-top/scripts/sixone-cli.py plan show .`

## 不变量
1. <永不过期约束>
2. <永不过期约束>

## 真源入口
- 计划与当前任务：`_wiki-methodology/_top/_task_plan.md`
- 时间线、笔记与交接：`_wiki-methodology/_top/_logs/`
- 仅列已启用的可选模块：`_codemap.md`、`_meta/_registry.yml`、`_meta/_data_registry.yml`、`_wiki-methodology/_top/_decisions/`、`_wiki-methodology/_wiki/`、`_wiki-methodology/_tests/`

## 验证
- <主验证命令>
```

旧入口项目不要在本规范里替换路径；先走 `share-top-upgrade-old` 识别和升级。

## 写作规则

1. 不写 current/latest/active 状态,只链接 task_plan。总长 ≤60 行。
2. 不写版本路径、具体数据路径、运行命令流水账。
3. 不复制 codemap、registry、tests、wiki 正文。
4. 反面教材只索引,不展开。
5. 入口可以厚到“足够找真源”,但不能厚到“替代真源”。
6. 如果一条信息会随本周工作变化,它不属于 agent 入口。

## Lint 检查

脚本:

```bash
~/.claude/skills/share-top/scripts/lint-claude-md.sh [<project-root>]
```

检查重点:

| 项 | 判据 |
|---|---|
| L0 | 项目入口为 `AGENTS.md`；存在旧 `CLAUDE.md` 时提示合并并退役，不能以 wrapper 通过检查 |
| L1 | 入口过长会提示 |
| L2 | 状态型版本断言禁止 |
| L3 | 硬编码版本路径禁止 |
| L4 | 必须指向 `_codemap.md` 或 task_plan |
| L5 | 反面教材展开过长会警告 |
| L6 | 代码/库版本细节会警告 |
| L7 | 流水线步骤展开会警告 |

## 迁移旧入口

1. 核对 `AGENTS.md` 与旧 `CLAUDE.md` 的独有内容、冲突和引用；旧原文保存在 Git 历史或项目 `_legacy/`。
2. 把有效指令合并到 `AGENTS.md`；有冲突按当前项目事实和用户约定判断，不直接用一份覆盖另一份。确认保留完整后退役 `CLAUDE.md`，不再保留 wrapper。
3. 把当前状态迁到 task_plan。
4. 把代码路径迁到 `_codemap.md` / `_meta/_registry.yml`。
5. 把数据路径迁到 `_meta/_data_registry.yml`。
6. 把知识正文迁到 wiki。
7. 跑 lint,再提交。
