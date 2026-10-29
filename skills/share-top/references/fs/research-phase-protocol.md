# 科研项目 Phase 与任务控制协议 v5.1

> 目标：跨会话接手时，30 秒知道“目标、当前任务、下一步、最新认识、阻塞”，并能在路线变化时增删改查任务而不丢历史。

## TL;DR

1. `_task_plan.md` 是当前进度唯一真源；`Current Coordinate` 是恢复镜像，`Active Work` 是任务状态真源。
2. 进入研究项目先跑 `sixone-cli.py plan show <项目>`，再按需读当前 phase 文件。
3. task ID 与 phase 绑定，例如 `P3.9.E2`；一个计划至多一个 `in_progress`。
4. 完成任务必须附 evidence 或明确无产物理由；阻断/取消必须留原因。
5. phase 文件描述阶段范围、输入、输出和长期路线，不维护第二套 live task 状态。
6. 结论进 findings，时间线进 logs，决策进 decisions；不要把历史正文堆回 plan。

## 1. Phase 骨架

| Phase | 名 | 典型范围 |
|---|---|---|
| P0 | 问题界定 | gap、RQ、假设、合规 gate |
| P1 | 方法论设计 | 数据规约、指标、判据、预注册 |
| P2 | 数据/实现准备 | 数据、接口、训练/评估底座 |
| P3 | 探索/Pilot | 受控开发实验、模块探索、失败排除 |
| P4 | Confirmatory | 冻结后主实验、稳健性、裁决 |
| P5 | 合成与可视化 | finding、主图、表格、规律分析 |
| P6 | 写作与投稿 | 论文、复核、投稿包 |
| P7（可选） | 审稿回复 | 补实验、改稿、回复 |

`phase_id` 语法为 `P<int>(.<int|slug>)*`，最深四段。项目可以增加 repair subphase，例如 `P3.9`，但不得静默改写已完成阶段的历史结论。

## 2. 当前进度 stamp

只有项目真源已经给出 phase，且当前工作/交接需要汇报状态时才显示 stamp；不要凭记忆编，也不要求每条闲聊都挂。

```text
🧭 当前 [P3.9] task=[P3.9.E2] 接入受控计划 CLI
```

stamp 是 Active Work 的短镜像：

- phase 必须等于当前计划 phase；
- task 必须等于唯一 `in_progress`；
- 标题必须与该任务一致；
- 没有 `in_progress` 时，stamp 可指向 dependency-ready 的 pending 项，但 `Current task` 应为空，由 CLI 给出 next。

## 3. task_plan.md 机器可读区

```markdown
# <项目> — 任务计划

> 创建: YYYY-MM-DD
🧭 当前 [P3.9] task=[P3.9.E2] 接入受控计划 CLI
> Done Criteria: <本轮可验证完成条件>

## Current Coordinate
- Goal: <本阶段目标>
- Current task: P3.9.E2 接入受控计划 CLI
- Next task: P3.9.E3 跑项目 case
- Latest learning: <最近改变路线的重要认识>
- Blocker: none

## Active Work
- [x] P3.9.E1 冻结协议 · state=done · ev=test:plan-parser
- [ ] P3.9.E2 接入受控计划 CLI · state=in_progress · dep=P3.9.E1 · scope=path:_code · gate=test:unit
- [ ] P3.9.E3 跑项目 case · state=pending · dep=P3.9.E2 · gate=test:integration
```

任务元数据使用 ` · ` 分隔。允许重复的键：

- `dep=`：依赖任务 ID；
- `scope=`：`path:`、`symbol:`、`registry:`、`pipeline:` 等影响范围；
- `gate=`：完成前必须过的验证；
- `ev=`：完成证据；
- `reason=`：blocked/cancelled 原因；
- `no_artifact_reason=`：无独立产物时的明确说明。

状态只能是 `pending|in_progress|blocked|done|cancelled`。没有物理删除命令，路线淘汰用 cancelled 留痕。

## 4. Phase 文件职责

`_wiki-methodology/_top/_phases/P<N>_<slug>.md`：

```markdown
---
phase_id: P3
upstream: P2
downstream: P4
status: in_progress
---

# Phase 3: 探索

## 范围
- 只使用 development split。

## 输入
- 已冻结的数据与指标定义。

## 输出
- 可复现的阳性或阴性裁定。

## 历史变更
- YYYY-MM-DD: 增加 P3.9 repair 路线。
```

硬规则：

- 每个顶层 `P<N>` 至多一个当前 phase 文件，YAML `phase_id` 全局唯一；
- 旧版进入 `_legacy/` 并留 tombstone，不与当前文件并存；
- phase 文件拥有范围和阶段边界，不拥有 Active Work 的 live checkbox；
- task 的细分可以随发现扩展为 `E2.1/E2.2`，无需改写 phase 历史。

## 5. CLI 增删改查

```bash
CLI=~/.claude/skills/share-top/scripts/sixone-cli.py

python3 "$CLI" plan show <项目>
python3 "$CLI" plan validate <项目>
python3 "$CLI" plan add <项目> --id P3.9.E4 --title "新任务" --dep P3.9.E3
python3 "$CLI" plan add <项目> --parent P3.9.E4 --title "新增子任务"
python3 "$CLI" plan edit <项目> P3.9.E4 --add-scope symbol:ControllerGate --add-gate test:negative-case
python3 "$CLI" plan start <项目> P3.9.E4
python3 "$CLI" plan block <项目> P3.9.E4 --reason "缺固定输入"
python3 "$CLI" plan reopen <项目> P3.9.E4
python3 "$CLI" plan complete <项目> P3.9.E4 --evidence test:integration
python3 "$CLI" plan cancel <项目> P3.9.E5 --reason "被统一方案替代"
```

完整参数、并发 CAS 和错误语义见 `../sixone-cli-design.md`。

## 6. 冷启动接力

新 AI 接手研究项目：

1. 跑 `plan show`，不要先读整份超长 plan；
2. 如果 `verdict` 非 ok，跑 `plan validate` 并先修 plan invariant；
3. 读当前 phase 文件的范围/输入/输出；
4. 如果任务有 `scope/gate`，跑 `affected --task <id>` 找代码、测试和 owner；
5. 必要时再读最近 finding/log，不全仓漫游。

接手汇报：

```text
我接手 P3.9.E2；目标是……；当前证据是……；下一步是……；阻塞为 none。
```

读完关键真源仍不清楚时应直说不知道，不能靠聊天记忆补写项目状态。

## 7. Findings / Logs / Decisions

```yaml
---
phase_id: P3.9
---
```

- plan：当前意图、依赖、scope、gate、证据指针；
- findings：稳定结论、失败机理、可复用规律；
- logs：发生顺序和命令摘要；
- decisions：路线选择及理由；
- external reviews：外援原意见；只有被接受的影响才回写 plan/finding。

推翻 finding 不删除：增加 `overturned_phase_id`、`replaced_by_phase_id`，相关资产移入 `_legacy/<date>_<name>/` 并写恢复方式。

## 8. CodeGraph 与扫描联动

任务可把影响范围声明成：

```text
scope=path:_code/models/controller.py
scope=symbol:ControllerGate
scope=registry:controller
gate=test:controller-dev
```

然后运行：

```bash
python3 "$CLI" affected <项目> --task P3.9.E2
```

日常影响分析使用 fresh CodeGraph；用户明确要求扫描模式/语义扫描/重建 codemap 时才加载代码语义扫描技能（可选，本包未包含）做有边界扫描。`affected --task` 不等于全仓扫描，所有结构结论仍需源码和测试复核。

## 9. 更新触发

| 发生什么 | 动作 |
|---|---|
| 新任务出现 | `plan add`；需要时添加 dep/scope/gate |
| 开始/切换任务 | 先关闭或阻断当前项，再 `plan start` |
| 完成任务 | 先产出 evidence，再 `plan complete` |
| 路线失败 | `plan block` 或 `plan cancel`；机理写 finding |
| 新结论/决策 | `record add finding|decision` |
| 代码 scope 变化 | 更新任务 scope，跑 `affected --task` |
| phase 切换 | 关闭当前 Active Work，更新 phase 文件，再建立新 phase 任务 |

## 10. 验收清单

- [ ] `plan validate` verdict=ok；
- [ ] 至多一个 in-progress；
- [ ] stamp、Current Coordinate、Active Work 一致；
- [ ] done/cancelled/blocked 有证据或理由；
- [ ] （若使用 phase 文件）phase 文件存在且范围/输入/输出清楚；
- [ ] 当前任务的 scope/gate 能定位到真实代码与测试；
- [ ] 历史结论在 finding/log/decision，不挤占恢复卡；
- [ ] 完成的任务带 gate 的验证结果作为证据（`plan complete --evidence … --commit`）；相关测试通过。

本协议只管科研 phase 路线与当前任务控制。论文写作、具体实验方法、Git 流程分别走对应 skill/rule。
