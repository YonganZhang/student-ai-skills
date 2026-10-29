---
name: research-dl-pipeline-base
description: "深度学习训练与研究闭环：强制 CUDA GPU、默认 PyTorch Lightning、过拟合/欠拟合诊断、loss 选择、超参/训练策略、归一化与初始化、通道尺度对齐、模型融合、论文找 idea→GitHub 代码→模块移植→结构对照、Kaggle/Hugging Face 比赛 trick 采购、AI 独立检查点，以及 Lightning/MMEngine/HF Trainer 选型、多任务、HPO、断点续跑、共享 backbone+任务头。也覆盖旧名 dl-pipeline-base、research-autoresearch-engine。纯概念、只查成绩、材料结论、普通代码报错不触发。"
---

# DL Pipeline Base

一个入口，两层用法：**第一层把模型训好，第二层把实验做可信。** 主入口语义是 `dl-pipeline-base`；全局注册名是 `research-dl-pipeline-base`，`research-autoresearch-engine` 是历史名，不维护第二套流程。

工程门禁、回执、结构卡是护栏，不是训练本身。判断模型发生什么、loss 怎么选、模块怎么接，永远排在“流程有没有填表”前面。

## 训练执行层（硬规则）

1. **深度学习训练必须在 CUDA GPU 上跑。** CPU 只允许数据检查、纯单测、无梯度探针；CPU 20 步不能写成“训练已迁移/已通过”。入口无 GPU 时明确 `CUDA_REQUIRED` 退出，不静默回退。
2. **默认用 PyTorch Lightning 的 `LightningModule` + `Trainer` 组织训练。** 不再新写裸 `for batch in loader` 循环；LLM/VLM 用 HF Trainer/TRL、OpenMMLab 检测分割用 MMEngine 等专用栈例外，但例外要写进 stack card，并做 GPU 与重载对拍。
3. **迁移先 parity，再谈涨点。** 至少验证：同 batch step-0 loss 对拍、真实 GPU 跑过一个验证周期、选中权重 strict reload、优化器成员/更新、同预算曲线。Lightning 不自动提升精度，也不是科学选择规则的替代品。
4. **多 benchmark 的“统一模型”默认是统一架构家族**：共享 backbone/模块 bank/接口，按任务独立 head、loss、解码器和 checkpoint。一个静态 head 服务异构任务是接口错配；一套共享权重服务所有库必须另做联合训练/多 seed 证据，不能口头预设。

操作合同、GPU 回执字段、迁移验收与共享/独立边界见 [GPU 与 Lightning](references/gpu-lightning.md)。

## 先读：训练判断核心

1. **诊断过拟合/欠拟合**：同时看 train/val loss、gap、曲线形状、数据量、容量和错误样本；先做记忆探针/学习信号探针。见 [训练判断核心](references/training-core.md)。
2. **Loss、超参、训练策略**：loss 与输出/标签匹配；lr/batch/schedule/正则/AMP/早停按顺序调；pilot 与正式比较分开。见 [训练判断核心](references/training-core.md)。
3. **归一化、初始化、通道/尺度对齐**：BatchNorm/LayerNorm/GroupNorm/InstanceNorm/RMSNorm 的适用条件；Xavier/He/零初始化/预训练；投影、插值、感受野、语义层级。见 [训练判断核心](references/training-core.md)。
4. **模型融合**：先有强单模型，再看错误相关性；权重只在 select 段选；简单平均优先，stacking 必须 OOF。见 [训练判断核心](references/training-core.md)。
5. **找 idea、读论文、拆模块**：先判断任务是识别/检测/分割/追踪；去 CVPR/ICCV/ECCV/NeurIPS/ICLR/ICML/AAAI/ACM MM 等找论文；下载官方代码，提取机制，不是抄一个类名。见 [从论文到模块](references/idea-to-module.md)。
6. **把模块接进来**：按模块假设检查位置、融合、函数保持、归一化、通道尺度、训练策略、对照和诊断；不搞与假设无关的全套仪式。见 [组件工作流](references/component-integration.md)。
7. **实验对照**：同数据、同 split、同主预算轴、同评价器；一次只改一个科学变量；干扰超参两边对称重调。见 [实验协议](references/experiment-protocol.md)。
8. **主动买 idea**：从 Kaggle solution、HF 模型卡/论文、官方代码和错误切片里找候选 trick；先过机制与泄漏记分卡，再做最小验证。见 [Idea 采购](references/idea-sourcing.md)。
9. **让另一个 AI 检查**：设计、接线、第一次信号、冻结/test 前、负结果后各设检查点；Reviewer 只读，Builder 负责修。见 [AI 检查点](references/ai-checkpoints.md)。

## 容易漏掉的水下问题

- **任务/评价器定义**：指标、阈值、匹配、聚合、部署单元没定，曲线没有解释力。
- **标签/数据泄漏**：错标、空标、类别不平衡；同病人/视频/位置跨 split、统计量用了全量。
- **baseline 不公平**：没调好、主预算轴不同、增强/评价器不同。
- **优化不稳定**：lr/warmup/AMP/梯度爆炸；先修训练再谈结构。
- **归一化/选择噪声**：小 N 不必然 BN 失效；验证集太小、候选太多、差异接近噪声。
- **论文条件/部署约束**：通用涨点是条件性证据；离线涨点不等于延迟/显存可用。

## 主动发现与固化

水下问题不会自己冒出来；固定做三件事：

- **采购**：按当前失败模式去 Kaggle/HF/论文/代码里找候选，不按“最近什么火”找。见 [Idea 采购](references/idea-sourcing.md)。
- **检查**：C0 问题定义、C1 数据/指标、C2 基线/稳定性、C3 模块接入、C4 第一次信号、C5 冻结/test 前、C6 负结果复盘；按风险选，不必全跑。见 [AI 检查点](references/ai-checkpoints.md)。
- **固化**：现象 → 证据 → 根因层 → 不变量 → 检查 → 自动化/门禁 → 回归，走到回归才算修完。见 [从问题到流水线](references/incident-to-pipeline.md)。

检查点提示词模板：[Scout](assets/check-prompts/scout.md)、[Red Team](assets/check-prompts/red-team.md)、[Training review](assets/check-prompts/training-review.md)、[Pre-freeze](assets/check-prompts/pre-freeze.md)、[Postmortem](assets/check-prompts/postmortem.md)。

## 工程护栏（第二层）

1. **项目约束**：项目已有深度学习合同时先读；没有时按项目规则补最小数据/指标/test 边界。全局技能不写项目路径、GPU、benchmark 状态。
2. **选栈**：首次选栈或实质换栈写 [Stack Card](assets/stack-card.template.md)；通用监督学习默认 Lightning，检测/分割/医学 3D/时序/LLM/VLM 先走专用栈；任何栈都必须在 CUDA 上验收，CPU 只做单测。
3. **标准流程**：[标准流程](references/workflow/standard-flow.md) 是 S1–S9 的唯一阶段真源；它防漏项，不替代训练判断。
4. **结构判断**：改 backbone/neck/head、skip/残差/融合、移植论文模块的正式实验，先在实验记录写清失败模式、张量/位置契约、最小证伪对照；完整模板见 [结构判断单](references/architecture-judgment-gate.md)。未写不进正式结构训练；有界 wiring/shape 探针可先做，不把 smoke 当证据。
5. **运行回执**：每个 run 写 manifest（生效 config、data hash、seed、预算、best step、`test_read`）；缺关键回执不写最终结论。

## 什么时候用

| 任务 | 动作 |
|---|---|
| 模型不涨、过拟合/欠拟合、loss 不降、训练不稳 | 先读 [训练判断核心](references/training-core.md)，不要先改结构 |
| 想融合模块、找创新点、移植论文 | [从论文到模块](references/idea-to-module.md) → [组件工作流](references/component-integration.md) |
| 想从 Kaggle/HF 榜单/比赛方案找 trick | [Idea 采购](references/idea-sourcing.md)：先看机制、泄漏、成本，再 screen |
| 要另一个 AI 做审查/监督/红队 | [AI 检查点](references/ai-checkpoints.md)；提示词在 `assets/check-prompts/` |
| 同类问题反复出现，想固化成检查 | [从问题到流水线](references/incident-to-pipeline.md) |
| 调参、超参搜索、预算阶梯、断点续跑 | [调参](references/tuning/README.md)、[实验协议](references/experiment-protocol.md) |
| 先用预训练/强 baseline，别从零造 | `transfer-learning-first.md`、`kaggle-as-toolbox.md` |
| 搭/迁移 pipeline、选 Lightning/MMEngine/HF Trainer、多任务、多卡 | 本页 + [GPU 与 Lightning](references/gpu-lightning.md) + [Pipeline 边界](references/pipeline-boundary.md) + [栈矩阵](references/stack-matrix.md) |
| 检测/分割、医学 3D、时序、LLM/VLM、RL、表格 | 先按栈矩阵路由；专用栈覆盖 ≥80% 就不强套基座 |
| 只解释概念、只查排行榜/成绩、材料/物理结论、普通 ImportError | 不触发；分别走对应技能或直接排查 |

## 资产状态（别把“有链接”当“已验收”）

| 资产 | 状态 | 边界 |
|---|---|---|
| `references/training-core.md` | ✅ 方法手册 | 训练诊断/调参/归一化/初始化/融合/对照；不含项目数据 |
| `references/idea-to-module.md` | ✅ 方法手册 | 论文→代码→模块→结构对照；检索入口见来源库 |
| `references/idea-sourcing.md` | ✅ 方法手册 | Kaggle/HF/论文 trick 采购、记分卡、公榜风险 |
| `references/ai-checkpoints.md` | ✅ 方法手册 | 七个检查点、Codex 监督闭环、提示词模板 |
| `references/incident-to-pipeline.md` | ✅ 方法手册 | 问题台账、根因、不变量、自动化与回归 |
| Lightning 参考模板 `assets/lightning-template/` | ✅ 单卡 GPU 实测 | points/series/multitask 的 CPU 单测保留；维护者已在单张消费级 GPU 上跑过真实 GPU step-0 parity + strict reload；DDP/生产检测器 parity 仍未验收 |
| 多任务 runner | ✅ 首版最小实现 | 同输入、全标签、共享 backbone、每任务 head、共同 `val/loss`；不支持缺标签/异步采样/PCGrad/每任务 best |
| `scripts/audit_curve.py` / `scripts/check_run.py` | ✅ 单测 | 曲线与开发准入；不等于最终 test 回执 |
| `scripts/issue_ledger_check.py` | ✅ 4 项单测 | 台账字段/枚举/关闭证据；不判断事故是否真实 |
| `scripts/structure_gate.py` + 结构判断单 | ✅ 模板已接 + 7 项单测 | 缺卡/过期/预算/seed 不符在优化器前退出；自定义入口必须自己接 |
| MMEngine/MMDetection/MMSegmentation、HF Trainer、MONAI、PyTorch Forecasting、TRL | 🔗 仅路由 | 未在本 skill 的参考模板跑通，不宣称可用 |

## 五条不变量

1. **先判断再调参/改结构**：过拟合/欠拟合、loss、数据、评价器没搞清，不要用加模块掩盖问题。
2. **逻辑 → 工程 → 实验**：论文的“通用涨点”是条件性证据，不是定理；先确认机制和条件，再忠实实现，再做同预算对照。工程不对先修工程；工程对仍不涨，写清边界。
3. **一次只改一个变量**：科学变量、干扰变量、固定变量分开；改结构后两边对称重调 lr/wd/warmup/预算；同主预算轴、多 seed、看方差。
4. **选点在 select，test 只做最后验收**：权重、阈值、解码器、融合权重在 select 段选；模型冻结后可以也应该用 test 打分，和 baseline 比；但看了 test 后不要再回头改模型再报同一 test。项目所有者给的长期 test 授权可以直接使用，不再逐次询问，也不要求封存；授权只覆盖评估，不覆盖训练/选择。
5. **证据先于结论**：`best_at_cap` 不是收敛；固定预算比较标右删失；缺 manifest/hash/seed 的结果不写成最终结论。

## 执行顺序

阶段定义只看 [标准流程](references/workflow/standard-flow.md)；这里是工程落地顺序：

1. **S1 任务与指标**：原生指标、聚合、匹配、阈值/解码规则写成合同。
2. **S2 数据接口**：数据合同、真实样本叠图、预处理统计只来自训练子集。
3. **S3 划分与选择**：fit / select / evaluate / test 四段；按独立单位切；随机只用于 iid 样本。
4. **S4 基线与阳性对照**：强 baseline + 一个“已知好”的参照能在本流水线复现。
5. **S5 流水线体检**：评分器自检、叠图反向对照、增强同步、记忆/学习探针、strict reload、断梯度失败。
6. **S6 结构判断**：先写结构判断单；先位置后模块；一次只改一层。
7. **S7 调参**：pilot → 预算阶梯 → 曲线审计；pilot 标 exploration，不当最终证据。
8. **S8 比较与采纳**：同主预算轴、多 seed、效应/区间/方差；结论只写有用/无用/有害/不可判。
9. **S9 溯源与归档**：manifest、生效 config、命令、环境、失败记录；test 最后验收。

已有 runner 的调参可直接从 S7 进入；不强制重搭 pipeline。S0 的最终选型不能早于 S1 的最低合同。

## 运行与结果门禁

- **选点**：模板固定最低加权 `val/loss`；多任务也是共同折中。loss/tasks/loss_weights/`data.target_dtypes` 写入 `selection_recipe.json`，同一 run 改变就拒绝续跑。
- **曲线**：`audit_curve.py` 判 `TURNED_UP/PLATEAU/BEST_AT_CAP/STILL_DECREASING/INSUFFICIENT/INVALID`；`BEST_AT_CAP` 默认不通过，需显式 `--allow-censored` 标右删失；不自动当成“预算不足”或“已收敛”。
- **开发准入**：`check_run.py` 要求 manifest 完整、config/data hash 一致、best 与 history 一致；`--strict` 还会因 `git_dirty=true` 阻断。
- **右删失**：固定预算比较可加 `--allow-censored`，输出标 `censored=true`；不得写成收敛。
- **结构**：训练入口在首个 `optimizer.step()` 前用 `scripts/structure_gate.py` 校验结构判断单与配置；Lightning 模板已接 `--structure-card` / `--validate-only`。
- **test**：模型冻结后可以也应该测试；test 只做最终验收，不参与 checkpoint/阈值/融合/解码器选择。已读 test 的 run 不得回流选择。项目合同若已给长期 test 授权，直接按合同使用，不再逐次申请，也不要求 `TEST_SEALED`；授权不等于可用于训练/调参。

## 多任务

首版支持：同一输入/同一 batch、所有任务标签齐全、共享 backbone、`nn.ModuleDict` 每任务 head、每任务独立 loss/metric、单优化器、固定非负权重、单设备。

明确不支持：缺标签、异步 loader、动态任务采样、PCGrad/GradNorm/自动权重、多优化器、每任务最优 checkpoint、DDP 正确性、生产检测器、多模态、RL。首版选点固定为共同 `val/loss`；实现与验收见 [多任务](references/multi-task.md)。

## 多 benchmark 的统一架构家族

先写清“共享什么、独立什么”，再训练：

- 共享：输入/预处理语义、视觉或证据 encoder、模块 bank、任务接口、日志与回执；
- 按任务独立：head、loss、解码器、阈值、选择指标、checkpoint；
- 不同 benchmark 的标签空间和评价器不同，不能用一个静态 head 硬套；
- 要共享一套权重/联合训练，单独登记为 ablation，用同预算、多 seed、逐库指标证明不伤害单库；没有证据不把它写成默认赢家。

汇报“一个统一模型”时，必须能回答：共享权重是否真的同一套？哪些 head 不同？各库是独立 checkpoint 还是联合训练？答不清就写“统一架构家族，独立 checkpoint”，不要写“一个统一 checkpoint”。

## 常见失效模式

| 现象 | 先查 | 再查 |
|---|---|---|
| 换栈后 loss 不降 | 数据接口、归一化、标签、step0 输出、官方 recipe | 记忆探针、梯度 |
| train 低 val 高 | 过拟合、分布偏移、增强/预处理不一致 | 加数据/正则；查 split |
| train/val 都高 | 优化不足、容量、标签噪声（不排他） | lr/loss/标签/记忆探针 |
| checkpoint 恢复不一致 | RNG、scheduler、EMA、数据顺序、optimizer 成员 | strict reload、step0 对拍 |
| best 在 cap | 右删失；曲线仍降只是可能性 | 结合趋势/噪声扩预算，否则标右删失 |
| val loss 最低但部署指标差 | 单视图/多视图、阈值、选择指标 | 重定义选择合同，不回头用 test |
| 多任务总 loss 降、单任务退化 | 梯度冲突、loss 尺度、采样 | 单任务 baseline、梯度范数 |
| HPO 越搜越差 | 验证集用旧、trial 太多 | trial 上限、独立确认集 |
| 3D/时序分数虚高 | spacing/orientation、按切片/时间泄漏 | 按病人/体积/时间块切 |
| 模块不涨 | 位置/融合/初始化/梯度/预算 | 同参数量对照、多 seed、同 checkpoint on/off |

## 什么时候必须停下来问用户

- 需要把 test 用于训练/选择/调参、改数据只读边界、跨项目/跨领域、超过已批预算或并发上限；常规冻结模型 test 评价若已有项目长期授权，不在此列；
- 要换栈、换 backbone/结构、改项目合同，或项目规则与全局规则冲突；
- 论文声称通用、工程检查也过，但仍不涨，需要判断是条件不匹配还是放弃；
- 同一接口连续负结果且现有证据分不清“实现失败/方向失败”，或验证集已明显用于过多试验；
- 需要凭记忆补实验参数、文献结论或物理机制，而 wiki/原文没有证据。

停下来时说明：缺什么、影响、最小改法、建议层级；不要静默择一。

## 验收

- [ ] 任务、指标、部署单元、数据单位、baseline 明确；
- [ ] 记忆探针达到预期下限、真实增强下有学习信号；strict reload/断梯度失败；
- [ ] train/val 曲线能解释；loss/归一化/初始化/尺度有检查；
- [ ] 改模块：位置/融合/初始化/梯度有检查；step 0、on/off、独立 baseline 分清；
- [ ] 融合：单模型够强、错误相关性、权重只在 select 段选；
- [ ] 训练在 CUDA GPU 上完成；回执有设备/GPU 名称/峰值显存；没有把 CPU smoke 当训练验收；
- [ ] 训练循环走 Lightning（或 stack card 写明的专用栈例外）；迁移有 step-0 parity + strict reload；
- [ ] 同主预算轴、≥3 seeds 起步、报告区间/方差；pilot 与正式比较分开；
- [ ] `BEST_AT_CAP` 已明确标右删失或已扩预算；不把 cap 当收敛；
- [ ] 多 benchmark：共享 encoder/模块 bank/接口、按任务 head；没有联合训练证据时不写“一套共享权重”；
- [ ] manifest 完整；test 最后验收，结果不覆盖；
- [ ] 结论等级明确：有用/无用/有害/不可判。

## 按需路由

| 阶段 / 问题 | Read |
|---|---|
| 过拟合/欠拟合、loss、超参、归一化、初始化、融合、对照 | [训练判断核心](references/training-core.md) |
| 找论文、读代码、拆模块、移植、结构对比 | [从论文到模块](references/idea-to-module.md) |
| Kaggle/HF 比赛 trick、公榜过拟合、trick 记分卡 | [Idea 采购](references/idea-sourcing.md) |
| AI 审查/监督/红队、检查点、冻结前复核 | [AI 检查点](references/ai-checkpoints.md)；`assets/check-prompts/` |
| 把反复出现的问题固化成断言/检查/门禁/回归 | [从问题到流水线](references/incident-to-pipeline.md) |
| 加模块/换结构/改 skip/融合 | [组件工作流](references/component-integration.md)；正式实验先写结构判断（可内联） |
| 论文移植忠实性 | paper-port-fidelity（mlgain 组件接入参考库，可选，本包未包含） |
| 调参、超参搜索、断点续跑 | [调参](references/tuning/README.md)；`scripts/hpo_study.py` |
| 结果反直觉、实验本身可疑 | [排错](references/triage/README.md) |
| 指标口径、评价器、数据泄漏 | `evaluation-alignment.md`、`data-hygiene.md`、`leakage-checklist.md` |
| 划分与选择 | `split-design-contract.md`、`selection-hygiene.md` |
| 多源/多模态融合 | `multimodal-fusion-design.md`、`multimodal-fusion-diagnostics.md` |
| 架构、特征或消融设计 | `architecture-ablation.md`；位置消融先过结构门禁 |
| 稳定冠军、多 seed、同预算 | `stable-champion-protocol.md`、`experiment-protocol.md` |
| 盘点已测模型、排行榜、下一批测哪些 | `model-matrix-planning.md`；`assets/model-matrix.template.json` |
| 智能体/团队职责、假设台账 | `agent-value-oracle.md`、`multi-agent-protocol.md`；`assets/hypothesis-trace.schema.json` |
| ARIS 实验实现/审查、模块接入验收 | `aris/README.md` |
| 吸收的外部仓库/工具、案例 | `upstream/README.md`、`case-studies/INDEX.md` |
| 早期方法论与最小实验循环（背景） | `engine-manual.md`、`core-loop-karpathy.md`、`core-methodology.md` |
| 来源、论文、代码、技术博客 | [来源库](references/source-library.md)、[方法来源](references/method-sources.md) |
| LLM/VLM 微调、LoRA/QLoRA、量化部署 | [LLM 子流程](references/llm-finetuning/README.md)；不强套 Lightning |
| 搭基座、选 Lightning/MMEngine/HF Trainer、多任务 | [GPU 与 Lightning](references/gpu-lightning.md)、[Pipeline 边界](references/pipeline-boundary.md)、[栈矩阵](references/stack-matrix.md)、[模板](assets/lightning-template/README.md) |
| 结论与证据分级、独立验证、运行溯源 | `evidence-trail.md`、`independent-verification.md`；`scripts/run_manifest.py` |
| 卡住、需要人工 checkpoint | `stuck-protocol.md`、`human-checkpoint-protocol.md` |
| 模型设计团队、多智能体分工 | `multi-agent-protocol.md`；`assets/hypothesis-trace.schema.json` |
| 核验本入口与兼容路由 | `evals/evals.json`；`skill-routing-evaluation.md` |

项目特有的数据路径、GPU、phase、benchmark 状态和实验队列放项目合同/项目页，不写回全局入口。
