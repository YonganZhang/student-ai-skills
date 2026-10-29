# 更新触发矩阵

目标：让 AI 知道“发生什么就更新哪里、不要更新哪里”。表里的登记类 owner（codemap、registry、data registry、wiki、tests、pipeline）都是**可选模块**（CodeBook 已退役，代码结构交给 CodeGraph）：项目启用了才更新，没启用不补建。

## 边界

不承诺后台自动实时同步。实时性来自三件事：

- `sixone-cli plan show` 进入项目时给恢复卡（“我在哪”唯一入口）。
- AI 开工时在任务上写清 `gate`，完成时按本矩阵写入对应 owner 并附一次证据。
- 需要时用 `sixone-cli doctor`（死链、登记路径、plan validate、未记录改动）和项目自己的测试确认。

没有 hook、脚本、测试三件证据时，不得写“自动注册”“自动同步”“commit 自动生成”。

分级同步（何时更新什么）：

- **实时**（任务状态一变就更新）：问答工作本经`plan add/start/done/block/reopen/cancel`写入，目录镜像和自动日志由CLI生成；途中有实质进展用`plan note`。业务代码按项目Git流程提交/集成，`plan done --commit`保存计划提交，不把它说成自动提交全部业务。旧计划继续按所属格式操作。
- **收尾**（改了代码/数据/pipeline/测试时，本轮结束前）：codemap（仅入口变了）、registry、data registry、pipeline verify、tests gate，按下表；可复用理由写decision，证据路径用`plan done --ev`挂到对应尝试。
- **方法变化当轮**：权威方法正文及相应实现/验证合同同步；图语义受影响时更新可编辑图与预览。实验候选与已采用方法分开，详见[方法论工作流](methodology-workflow.md)。
- **按需**：whole picture网页、与本轮无关的Wiki长文和可复用decision。方法任务不等用户再次提醒才更新其方法页。

收尾检查 hook 只提示、不拦截，注册与边界见 `share-top-runbook.md`「Hooks」。

## 触发矩阵

| 发生什么 | 更新（已启用的 owner） | 禁止更新 | 验证 |
|---|---|---|---|
| 当前任务、阻塞、下一步变了 | 用 `plan add/start/done/block/reopen/cancel` 改工作本并生成目录镜像 | `_codemap.md` / roadmap / handoff 里维护第二套 current | CLI 写入时自带校验 |
| 任务代码范围或 gate 变了 | 问题/尝试的验收及相关验证合同；新尝试用`plan add --gate`，旧目录计划按所属格式维护scope/gate | 在日志复制静态影响清单 | 实现影响面核对 + relevant tests |
| 新增/删除/改主流程代码入口 | `_codemap.md` + `_meta/_registry.yml` | wiki 长正文替代 registry | registry path check + relevant tests |
| 启用知识树的项目：新增、改写、改名或删除扫描范围内的文档 | 同一次提交里改 `_meta/_doc_summaries.yml` 的条目（复核后 `doctree summaries stamp`），再 `doctree build` | 在文档头部写 `topics:`/`summary:`；手改 `TREE.md`、`_tree/`、`CATALOG.md` | `doctree check` |
| 新建/修改 pipeline 或 step 接线 | `_pipelines/<name>.yml` + `_meta/_registry.yml` + `_wiki-methodology/_tests/`；同步 `_codemap.md` 路由 | 手填 `verified_steps_hash` / 只改代码不改 manifest | action+assertion / SSDO / anti-fake gate + `sixone-cli verify-pipeline <项目> <pipeline>` |
| 新增/改数据资产 | `_meta/_data_registry.yml` | `_registry.yml` 里塞数据资产 | data path/provenance check |
| 改公式、参数、方法论或核心接口 | 当轮更新权威方法页及相应代码/实验/Tests；图语义变化时更新图源和预览 | 只改Plan或批次报告；用未采纳实验覆盖原方法；图维护第二套进度 | formula/unit/repro gate；来源/图漂移检查及真实预览 |
| UI 视觉/交互变更 | codemap UI 域 + `_wiki-methodology/_tests/` 证据 | 自动更新 whole_picture，除非用户说网页/HTML | Playwright/screenshot gate |
| 外援 review / 多智能体审查 | 采纳的结论进任务（`plan add`/`note`），可复用理由进 `_decisions/` | external review 直接变 current | 任务 gate |
| 跨列 ref 新增或修改 | ref 所在 owner 文件 | 手写 reverse-ref 表 / 复制正文 | `sixone-cli doctor`（默认含 typed ref 死链） |
| 临时截图、下载、实验 | `_tmp/` 或 `_sandbox/` | 项目根长期保留 | lifecycle check |
| 旧物、废弃代码、废弃输出 | `_legacy/<YYYY-MM-DD>_<name>/README.md` | 直接 `rm` 用户资产 | tombstone / rollback note |
| release / live 验收 | task_plan 摘要 + tests artifact | roadmap 当验收记录 | release/live gate |
| 用户明确要求扫描模式/语义扫描 | 加载代码语义扫描技能（可选，本包未包含），做有边界扫描；接受的结构事实回写 codemap/registry | 把 daily CodeGraph 或 `affected --task` 冒充全仓扫描 | live source/test verification |

## 收尾（最多 4 步）

本轮改了方法、主流程代码、数据、测试、输出资产或项目结构时，最终回复前：

1. `git status --short` 看实际改动。
2. 按实际方法、代码、数据或结构变化，对照本矩阵更新相关且已启用的owner。
3. 完成：`plan done <ID> "实际结果" --ev <证据> --commit`；未完成：`plan note`。跨项目用`-p`，旧格式命令见对应运行手册。
4. 最终回复写清“更新了哪些真源 / 哪些未更新及原因”。

已知过期的 owner 不报“完成”。`topic-closeout.py`、`top-lint.py` 等是可选工具，不是报完成的前置条件（见 runbook「可选与旧工具」）。

## CRUD Cheatsheet

| 动作 | 做法 |
|---|---|
| 查现有功能 | 先看 `_codemap.md` + `_meta/_registry.yml`，再 `rg` 代码验证 |
| 增代码入口 | 写实现 + 测试；补 `_registry.yml` 和 `_codemap.md` |
| 改代码入口 | 改实现 + 相关测试；同步 registry/codemap 的路径、状态、测试指针 |
| 删/废弃代码入口 | 从 registry/codemap 移除或标 deprecated；用户资产进 `_legacy/`，不直接删 |
| 增数据资产 | 放到合适目录；补 `_data_registry.yml` 的 path/source/check/hash |
| 改测试 gate | 补 `_wiki-methodology/_tests/` 的覆盖说明或运行记录 |
| 查/恢复当前阶段 | `sixone-cli plan show <项目>`，不从聊天记忆猜 |
| 增任务 | `plan ask`建问题，`plan add "尝试" --to Qn --gate ...`声明验收；旧格式按相应手册 |
| 改任务内容/状态 | 问答计划用`plan start/done/block/reopen/cancel`，完成带`--ev`；问题答案用`plan answer`，阶段判断加`--keep-open`；中途`plan note` |
| 查任务影响面 | `affected --task <id>`；CodeGraph 结果仍回源码/tests 复核 |

## Code Map

`_codemap.md` 只写 COL4：代码域、入口、调用关系、registry/query 指针、相关测试指针。

不写：

- 当前 phase。
- 下一步。
- 在线/离线状态。
- 长篇方法论。

改代码入口后必须同步：

1. `_meta/_registry.yml`
2. `_codemap.md`
3. 对应测试或 `_wiki-methodology/_tests/` gate

## Plan

问答计划的`_questions/`工作本拥有状态/答案/尝试；`_task_plan.md`中的“现在”和问答摘要由CLI派生。旧目录计划的状态仍在其步骤中，旧恢复字段按对应格式读。

它应该包含：

- current phase
- next action
- blockers
- done criteria
- required gates
- latest evidence pointer

Live task 不直接手改第二份 checkbox；CLI 完整命令、CAS 和 schema 见 `sixone-cli-design.md`。

它不应该吞掉历史、review、roadmap 和方法论：计划 ≤30KB、任务行 ≤500B、note ≤300 字；超了用 `plan compact` / `plan archive` 移到 `_logs/`。

## Data Registry

`_meta/_data_registry.yml` 管数据资产。推荐字段：

- `id`
- `path` / `local_path`
- `source` / `provenance`
- `size_bytes`
- `manifest_sha256` 或 hash 字段
- `check_command`
- `used_by`

hash 只证明本地漂移，不证明外部来源真实。

## File Lifecycle

写文件前先判定生命周期：

- 临时代码/实验 → `_sandbox/`
- 临时下载/中间态 → `_tmp/`
- 可复用测试证据 → `_wiki-methodology/_tests/_artifacts/` 或项目测试 artifact 目录
- 输出 → `_outputs/` / `_figures/`
- 旧物 → `_legacy/`

不确定时先问用户，不要把 root clutter warning 当成自动搬文件许可。

## Complex Software

复杂软件项目还需要测试 gate map：

- frontend -> browser/screenshot gate
- registry/data -> registry/data gate
- plugin/scenario/expert/skill -> corresponding local gate
- release/live -> release/live gate

项目已有 canonical script 时，以项目脚本为准，例如 `scripts/test-*.sh`。
