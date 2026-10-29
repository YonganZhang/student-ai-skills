# 组件集成工作流：唯一执行入口

这是 Auto Research 的组件执行分支。`mlgain-integrate-component` 只保留兼容入口与参考库；不要求先完成全家族排行榜，也不为已有用途重复确认权限。

**先读**：[训练判断核心](training-core.md)（过拟合/欠拟合、loss、归一化、初始化、融合、对照）；找模块与移植流程读 [从论文到模块](idea-to-module.md)。结构判断单是护栏，不替代这些判断。

## 接入前先回答的六个问题

1. **它解决什么失败模式？** 小目标、遮挡、尺度、运动、语义、时序关联，还是只是“论文说涨点”？
2. **原生位置在哪？** 论文/代码里模块接在哪个 stage、哪个分辨率、和谁融合？
3. **张量契约是什么？** 输入输出 shape、通道、dtype、mask、归一化、激活。
4. **为什么能迁移到我们的结构？** 语义层级、感受野、数据规模、任务是否匹配。
5. **候选位置有哪些？** 含原生位置，数量按结构决定；只有一个合理位置就写原因。
6. **对照是什么？** step 0 等价、训练后 on/off、独立 baseline、同参数量 control、seed 怎么设；主预算轴是什么。

## 接入维度（不要只加残差）

| 维度 | 要比较的选项 |
|---|---|
| 位置 | stem / stage 内 / bottleneck / decoder / skip / neck / head 前 |
| 融合 | add / concat+1×1 / gate / cross-attention / adapter / FiLM / 逐元素乘 |
| 函数保持 | 最后一层零初始化、gate 零初始化、残差缩放；仅函数保持接口要求 step 0 同权重/buffers/eval 下接近父模型 |
| 归一化/激活 | pre/post norm、融合前/后、BN 统计量、激活顺序 |
| 通道/尺度 | 投影、插值、padding、stride/dilation、感受野 |
| 训练 | 新模块 lr、warmup、freeze backbone、分层解冻、梯度裁剪 |
| 诊断 | 梯度范数、有效贡献、同 checkpoint on/off、strict reload、优化器成员 |

## 结构判断：先写假设，不必先造表

任何加模块、换结构、改 skip/残差/融合、移植论文模块的**正式实验**，先在实验记录里写清三件事：失败模式/机制假设、张量/位置契约、最小证伪对照。需要完整模板时再用 [结构判断单](architecture-judgment-gate.md)。

- 没有判断就进入正式结构训练，等于用算力代替假设；但已授权的有界 wiring/shape/无参数更新探针可以先做，用来验证接口，不把 smoke 当结构证据。
- 位置对照不适用时写原因；固定同一个外挂接口换模块，只检验了一个放置假设，不能据此判断模块家族。
- 未做能区分假设的对照，不把负结果归因于模块。

## 按当前任务选择最少步骤

1. 从会话提取用途、可信 pipeline、目标组件/任务接口和指标，先不预设插槽；有端到端学习需求先读[学习 SOP](end-to-end-learning-sop.md)。
2. 搜本地注册与 vendor，再读上游源码/论文确认真实契约；已有可信 pipeline 直接复用，只有缺失时才选包。
3. 先做结构判断：写清失败模式、结构图、候选位置、机制假设和证伪条件；候选位置按结构决定（含原生位置；若只有原生位置，写明原因）。先解决维度、缺测、可见性问题，不混入新的训练循环/损失/缩放。
4. 实际接入 fit/predict/save/load 的生产消费者；正式结构训练入口记录判断单并与当前配置一致；按 [ARIS 接入检查](aris/integration-checks.md) 把 shape、参数实际更新、初始化、数据语义/mask、on/off 和保存恢复落实为项目断言，运行 `scripts/integration_gate.py` 留存日志；失败先修，扩大预算前做一次独立审查。
5. 同输入同编码器的独立 baseline 与候选一起训练；依据真实预测、曲线和误差判定。不理想时只运行能区分当前两三个假设的探针，再决定修改或结束。结果与预期方向相反时先按[排错](triage/README.md)逐层排查，选点是否过早按[选择卫生](selection-hygiene.md)第 5 条核对。
6. 记录改动、来源、预算、结果及边界；明确是 smoke、同预算 screen 还是稳定冠军。长期维护项目另补注册/文档/回归，不把它们混成模型精度要求。

## 专门知识按需读取

下表保留旧库路径；这里负责步骤，详细知识不复制。

| 需要解决的问题 | 参考 |
|---|---|
| 没有可信完整 pipeline | [借 pipeline](../../mlgain-integrate-component/references/borrow-existing-pipeline.md)、[包与精确插槽](../../mlgain-integrate-component/references/pipeline-package-catalog.md) |
| **先判断改哪里、原生还是外挂** | [结构判断门禁](architecture-judgment-gate.md) |
| 惯例、分类和理论放置 | [框架惯例](../../mlgain-integrate-component/references/framework-placement-conventions.md)、[模块分类](../../mlgain-integrate-component/references/module-taxonomy.md)、[放置理论](../../mlgain-integrate-component/references/architecture-placement-theory.md) |
| 张量/语义/数据契约 | [抠契约](../../mlgain-integrate-component/references/extract-interface-contract.md)、[兼容性](../../mlgain-integrate-component/references/compatibility-check.md)、[数据合理性](../../mlgain-integrate-component/references/feature-and-data-reasonableness.md) |
| 旁路、初始化、残差与门控 | [函数保持](../../mlgain-integrate-component/references/function-preserving-socket-protocol.md)、[残差门控](../../mlgain-integrate-component/references/residual-gating-safe-integration.md) |
| 真实梯度与缺测接线 | [接线检查](../../mlgain-integrate-component/references/integration-sanity-checks.md)、[机理探针](../../mlgain-integrate-component/references/mechanistic-diagnosis.md)及该页挂载的 `probe_hooks.py` |
| 论文/作者实现的忠实移植与等价测试 | [论文移植忠实性](../../mlgain-integrate-component/references/paper-port-fidelity.md) |
| 结果反直觉、怀疑实验本身有错 | [排错](triage/README.md)：有序排查，缺层写"不可判" |
| 改结构后重调与可续跑搜索 | [调参](tuning/README.md) |
| 扩大实验与独立确认 | [稳定冠军](stable-champion-protocol.md)、[证据等级](evidence-trail.md)、[独立验证](independent-verification.md) |
| 长期维护的组件卡 | [集成报告](../../mlgain-integrate-component/references/integration-report-template.md) |

## 程度和结论边界

- 做了结构/接口改动时，最小 wiring 检查不能省；纯数据/loss/调参不套这套。单卡不跑分布式探针；compile/FSDP/捕获等只在实际使用时查机理参考的适用范围，不继承“所有生态已验证”的泛化保证。
- 首轮同合理默认超参回答有限预算下哪一个更好；不是证明两架构各自最优。进一步 HPO 给双方对称预算。既有[受控比较细则](../../mlgain-integrate-component/references/controlled-comparison.md)用于需要稳健采纳/调参的阶段，不强制每次试模块前完成 HPO。
- 诊断数值帮助定位，不是机械审批阈值。零初始化首步梯度例外以实际后续更新检验；未使用分支也不能仅凭注意力可视化判定。
- 限定动作 oracle 只适用于对应的选择/门控职责；不能拿“选已有结果”的上界否定可生成额外修正的神经网络。涉及该问题再读[职责与上界](agent-value-oracle.md)。
- 用户要可训练模块时就把模块接入并完成有界试验；固定后处理、重复审计或无限等待冠军都不能替代交付。
- “接入”不等于“随便找插槽”：未写结构判断不进正式结构训练；允许只读契约抽取、shape 推演、无参数更新的探针，以及已授权的有界 wiring 检查。
