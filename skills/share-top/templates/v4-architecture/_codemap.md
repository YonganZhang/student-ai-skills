# Code Map — <PROJECT_NAME>

更新: YYYY-MM-DD

本文是一页纸：项目用途与入口（≤5KB，入口变了才更新）。代码结构、调用关系交给 CodeGraph（`codegraph explore`，实时、零维护），不在这里手抄；为什么这样写看决策记录（`sixone-cli.py record for-file <项目> <文件>`）。当前 phase、下一步、运行态、最近测试结果只写 `_wiki-methodology/_top/_task_plan.md`。

## 冷启动读法

1. 当前状态: `sixone-cli.py plan show .`（真源 `_wiki-methodology/_top/_task_plan.md`）
2. 代码注册: `_meta/_registry.yml`（若启用）
3. 数据注册: `_meta/_data_registry.yml`（若启用）
4. 测试地图: `_wiki-methodology/_tests/`（若启用）

## 项目身份

| 字段 | 值 |
|---|---|
| 项目 | <PROJECT_NAME> |
| Mode | <research/software> |
| 目标 | <PROJECT_GOAL> |
| 方法 | <METHOD_OUTLINE> |

## COL4 真源关系

| 层 | 文件/目录 | 职责 |
|---|---|---|
| 人读代码地图 | `_codemap.md` | 代码域、入口、测试指针（调用关系用 CodeGraph） |
| 机读代码注册 | `_meta/_registry.yml` | 代码域、工具、pipeline、脚本、可复用入口 |
| 数据注册 | `_meta/_data_registry.yml` | 数据集、模型、外部资产、生成物血缘 |
| 查询/同步工具 | `_code/` | registry 查询、lint、同步 wiki 投影 |

## 主要代码域

| 代码域 | 入口 | 注册/测试 |
|---|---|---|
| 主流程 | `_pipelines/` | `_meta/_registry.yml` + `_wiki-methodology/_tests/` |
| 可复用代码 | `_code/` | `_meta/_registry.yml` |
| 数据接口 | `_data/` | `_meta/_data_registry.yml` |
| 输出/图/论文 | `_outputs/` / `_figures/` / `_paper/` | `_meta/_runs.yml` / `_meta/_data_registry.yml` |
| 实验代码 | `_sandbox/` | `_sandbox/_index.yml`; 优于 baseline 才进入主流程 |
| 归档代码 | `_legacy/` | 每个归档目录需 README/TOMBSTONE |

## 注册维护

- 新增主流程代码:先查 `_meta/_registry.yml`,复用已有条目;确实新增再注册。
- 新增数据/模型/外部资产:写 `_meta/_data_registry.yml`,不要只写 README。
- 新增测试:测试地图写 `_wiki-methodology/_tests/`,不要只在提交说明里写。
- 临时探查:留 `_tmp/` 或 `_sandbox/`,不进 registry。

## 不放在本文的内容

- 当前 phase / next action / service online-offline: `_wiki-methodology/_top/_task_plan.md`
- 长期路线和阶段边界: `_wiki-methodology/_top/_roadmap.md`
- 历史交接: `_wiki-methodology/_top/_handoff*.md`
- 架构图: `_wiki-methodology/_top/_SYSTEM-ARCH.md`
- 文件生命周期缺口: `_meta/_known_issues.md`
