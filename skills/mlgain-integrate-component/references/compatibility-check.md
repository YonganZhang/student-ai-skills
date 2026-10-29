# 集成前的兼容性检查清单

拿到组件的真实契约（见 `extract-interface-contract.md`）之后，动手写集成代码之前，对照**你现有模型的实际数据流**逐条核对。

## 通用五条

- **维度/dtype 是否匹配**：组件期望的输入形状和你现有模型在插入点产出的张量形状是否一致；不一致时的 reshape/投影层本身要不要额外训练、会不会引入额外的信息损失（见 `module-taxonomy.md` 的 B12 形状适配类——投影层本身要计入单变量记账，不是无关紧要的胶水）。
- **batch/seq 维度顺序**：常见坑——组件按 `(seq, batch, feature)` 写的，你的模型是 `(batch, seq, feature)`，直接接会跑得通但语义全错。
- **梯度是否必须流经该模块**：这个组件是否处于反向传播的关键路径上；如果它被放在 `no_grad`/`detach` 过的分支里，加了等于没加，且不会报错（`mechanistic-diagnosis.md` 的 P2 直接测这条）。
- **是否引入信息泄漏**：时序模型里最容易被组件集成带进来的新泄漏——全局池化/全局注意力模块作用在整条序列上，可能让当前时刻的预测提前看到未来时刻的信息，即使原论文场景（可能是非时序任务）没有这个问题。**集成到时序任务时必须重新检查这一条**。
- **显存/算力量级变化**：本身不是问题（见 `controlled-comparison.md`——参数量和训练时间的变化不需要控制）；但如果因此被迫缩小 batch size 或缩短序列长度，这是一个新引入的自变量，要显式记录，不能悄悄跟"是否加了这个组件"混在一起。

## 族专属兼容标记（由 `module-taxonomy.md` 的分类卡自动展开）

分类完成后，按组件所属家族逐条核对：

- **是否依赖 batch 统计量**（BN类归一化）→ 与小 batch、非 i.i.d./异构数据、RNN/序列、对比学习、对抗训练不兼容，且训练/推理统计量可能不匹配。
- **KV-cache 与流式兼容性**：换了序列混合机制（attention→SSM等）会不会破坏下游的增量推理假设。
- **是否需要因果 mask**：以及换了实现是否需要**同名注册配对的 mask 接口**（HF `AttentionInterface`+`AttentionMaskInterface` 是典型例子，不配对会被静默传入 `None`）。
- **是否改变下游 channel 数**：concat 型跳连与 add 型不可互换，见 `architecture-placement-theory.md`。
- **是否有 `size_divisibility` 类输入约束**：横向连接/FPN类结构对非整除输入的处理。
- **活体手术是否需要迁移 optimizer**：用类型键控 surgery（如 MosaicML Composer 的 `replace_module_classes`）替换既有模块时，必须同事务迁移 optimizer 状态，否则新参数永不被更新。

## 构造期校验，不是运行时才报错

兼容性结论最终要落成一行 **构造期 assert**（对标 mmseg `BaseDecodeHead._init_inputs` 的形状/类型硬校验、smp 的 `len(features) == _depth + 1`），在模型 build 时报错，而不是等第一次 forward 才炸。

## 输出

产出一份简短的"兼容性检查结论"，供 `integration-report-template.md` 引用：核对过的每一项 + 结论（兼容/需要适配层/发现潜在泄漏风险需要额外处理）。发现任何一条不兼容或有风险，先解决掉再进入集成编码，不要带着已知风险写代码指望"消融阶段会测出来"——`integration-sanity-checks.md` 的 Wiring Gate 阶段能拦住的问题不要留到 `controlled-comparison.md` 才发现。
