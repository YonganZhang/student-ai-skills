---
name: research-mlgain-integrate-component
description: "论文/SOTA 模块接入模型：选接入点，排查接错和效果下降；普通调参/报错不触发。"
---

# 组件集成：兼容入口

深度学习研究统一从 [DL Auto Research](../share-autoresearch-engine/SKILL.md) 进入。显式调用本技能时，直接读取它的[组件工作流](../share-autoresearch-engine/references/component-integration.md)，不再启动第二套立项、排行榜或审批流程。

本目录的 `references/`、`scripts/`、`assets/` 保留为组件专门知识与工具库，既有路径继续有效。按组件工作流逐项按需读取，不把全部诊断套到每次实验。

- 已明确要可训练融合：先读[端到端学习 SOP](../share-autoresearch-engine/references/end-to-end-learning-sop.md)。
- 需要判断插入位置、掩码、梯度或初始化：使用组件工作流的相应参考和最小接线探针。
- 用户已有用途与预算说明就直接执行；只有缺失信息会改变实际动作时才澄清。
- 接线、有效学习、跨划分稳定性是三个结论；任何一个都不能冒充另一个。
- 需要完整阶段表（P0–P5 借 pipeline、S0–S11）、按用途分级的严谨程度表、场景路由表或快速自检清单时，读[详细 SOP](references/detailed-sop.md)；与组件工作流冲突时以组件工作流为准。
- 移植论文/作者模块：先读[论文移植忠实性](references/paper-port-fidelity.md)（出处、对应表、等价测试、覆盖门）。
- 可调用的检查实现：`scripts/module_probe.py`（插座、等价、有效贡献、选点暴露）、`scripts/train_sanity_checks.py`（重载、优化器覆盖、按训练变换过拟合）、`scripts/alignment_probe.py`（叠图、反向对照、增强同步）；测试在 `tests/test_dl_probes.py`。
- 结果反直觉：按[排错](../share-autoresearch-engine/references/triage/README.md)逐层排查，缺层写"不可判"。
