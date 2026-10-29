# Auto Research / ARIS 与六合一联动

本页负责研究工作流与项目记录的交界；研究实现和检查仍走 [Auto Research](../../share-autoresearch-engine/SKILL.md) → [ARIS 本地合同](../../share-autoresearch-engine/references/aris/README.md)。用户无需说 ARIS，直接表达论文模块接入、融合验证、消融或实验审计意图即可路由。

## 何时使用

- 研究项目已经有 TOP：开始、恢复、改变方法或收尾时使用本页；先读 [runbook](share-top-runbook.md) 和 [CLI 手册](sixone-cli-design.md)。
- 项目没有 TOP：沿用现有计划和结果目录；不为一次模块试验强制初始化/迁移六合一，不新造 ARIS 当前计划。
- 这是一套智能体执行约定加已有 CLI；没有后台 hook，也不声称训练一结束就自动回写所有文档。

## 一份计划，按阶段留证据

1. 进入项目先运行 `sixone-cli.py plan show <项目>`，再 `brief`、`doctor`，确认当前任务、预算、数据边界及实际 owner；旧结构按 runbook 路由，不擅自升级。
2. 已有任务就 `plan inspect` / `plan edit` 补当前改动的 scope 与 gate；确需新任务才 `plan add`，再 `plan start`。沿用项目 phase 和任务 ID，不硬编码示例编号，不重复创建“ARIS 当前任务”。
3. 通过 ARIS 按需读取一个 `aris-*` 参考阶段。把方法合同、输入可见性、baseline、指标及预算写到现有方法/设计 owner，并从任务链接；上游 `EXPERIMENT_PLAN.md`、`RESEARCH_CONTRACT.md` 或 iteration log 若确需交付，只作为标注日期的设计/实验快照，必须链接 TOP 当前任务，不另维护待办状态。
4. 将 `integration_gate.py` 的项目断言、真实运行日志、独立审查与修复复验放到项目测试/证据目录；实验配置、split、seed、checkpoint 和原始指标按资产归属保存。任务 gate 指向实际断言/报告，不以 README 或空报告代替验收。
5. 缺检查、失败或 `review_unavailable` 时写明状态和下一步，必要时 `plan block --reason`；允许预算内诊断，不正式采纳或写验证通过。问题修复后重跑受影响 gate。
6. 完成任务范围要求的实际检查后，以 `plan complete --evidence <证据引用>` 关闭任务，运行 `plan validate`，按 runbook 执行 closeout / doctor。阴性实验可以作为“实验已完成”的结果，但不能写成“模块稳定提升”。新认识或路线决策用 `record add finding|decision`；进展/复核过程用 `record add log|review`，不把历史全文堆回当前任务。

所有 CLI 命令通过当前执行器自己的 `~/.claude/skills/share-top/scripts/sixone-cli.py` 调用；完整参数以 CLI 手册为准。没有真实执行和证据时不得宣称 TOP 已更新。

涉及方法取舍、缺失/掩码语义或失败方案时，按 [决策记忆](decision-memory.md) 在开工前查相关记录，收尾关联实际代码和验证证据；记录不能替代 ARIS 的接口、梯度、数据与效果检查。

## 六列各管什么

| Owner | 研究工作产生的内容 | 不应放这里的内容 |
|---|---|---|
| Wiki：`_wiki-methodology/_wiki/` | 论文来源、模块假设、方法合同、张量/时间/模态语义 | 当前任务状态与活进程 |
| Top：`_wiki-methodology/_top/` | 唯一当前计划、路线、发现、决定、审查与执行日志；链接原始证据 | 复制原始数据或第二份待办 |
| Tests：`_wiki-methodology/_tests/` + 项目 tests | 可执行断言、gate 定义、接线检查、独立审查结论和报告索引 | 仅凭工具退出 0 宣称科学结论成立 |
| Code：CodeGraph + `_codemap.md`、`_meta/_registry.yml` + 代码 | 实际模块/训练入口、调用链（CodeGraph 实时）、注册与使用说明；按需 verify-pipeline | 另一份算法事实或手写验证 hash |
| Lifecycle：项目资产登记与目录 | 数据划分、配置、权重、原始结果、临时/归档位置及复现路径 | 把机器路径和运行态复制到全局 skill |
| Whole Picture：`_whole_picture/` | 用户明确要求时生成、链接上述 owner 的网页 | 默认自动生成或充当当前计划 |

运行态 PID、端口和活日志按项目 runtime_facts 或既有运行记录保存；只操作本次可核对的任务，不能按通用进程名批量终止。证据含义始终区分接线通过、可学习、同预算提升与稳定泛化。
