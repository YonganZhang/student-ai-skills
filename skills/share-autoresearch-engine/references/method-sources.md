# 方法论来源：哪些思维已被别人总结过

结论：**没有人总结出“解决所有深度学习问题”的流水线，但有人总结出了大量可复用的失败模式和检查表。**
本 skill 的工作不是再写一套理论，而是把这些经验转成可执行的门。

| 来源 | 可迁移的核心思想 | 在本 skill 中落成什么 | 它不解决什么 |
|---|---|---|---|
| [Karpathy, A Recipe for Training Neural Networks](https://karpathy.github.io/2019/04/25/recipe/) | 先看数据、记忆探针、先跑简单 baseline、逐步加复杂度、检查输入/标签/评估 | smoke gate：记忆/学习探针；数据叠图；baseline 先行；一次只改一个因素 | 不告诉你具体任务用哪个栈，也不替代统计比较 |
| [Google, Rules of Machine Learning](https://developers.google.com/machine-learning/guides/rules-of-ml) | 先上简单规则/模型；先保证 pipeline 正确；警惕训练-服务偏差；用新鲜数据评估 | S4 baseline/positive control；S5 流水线体检；test guard；部署指标入合同 | 不覆盖研究型新结构探索 |
| [Hidden Technical Debt in Machine Learning Systems](https://papers.nips.cc/paper/5656-hidden-technical-debt-in-machine-learning-systems) | ML 系统大部分成本在 glue code、数据依赖、配置、反馈环，不在模型 | 固定上游 + 薄适配层；config/manifest；数据合同；禁止 pipeline jungle | 不给具体代码模板 |
| [The ML Test Score](https://research.google/pubs/pub46555/) | 数据测试、模型测试、基础设施测试、监控要系统化 | 数据/模型/恢复/守卫检查表；run manifest；报警码 | 面向生产系统，研究实验需裁剪 |
| [No Free Lunch（概览）](https://en.wikipedia.org/wiki/No_free_lunch_in_search_and_optimization) | 没有对所有问题都最优的算法 | “没有通用最优 pipeline”；专用任务走专用栈；必须 bake-off | 不告诉你当前任务该选哪个 |
| [scikit-learn: Model Selection](https://scikit-learn.org/stable/model_selection.html) | 训练/验证/测试分离；交叉验证；选择会消耗数据 | fit/select/evaluate 三段；val 选点；test 最终评价；best−2nd | 不覆盖深度模型的大预算和分布式 |
| [NeurIPS Reproducibility Checklist](https://www.cs.mcgill.ca/~jpineau/ReproducibilityChecklist.pdf) | 代码、数据、超参、seed、计算量、误差棒要可复现 | manifest；3 seeds；配置/数据哈希；结论带区间 | 不保证实验设计正确 |
| [Datasheets for Datasets](https://arxiv.org/abs/1803.09010) / [Model Cards](https://arxiv.org/abs/1810.03993) | 数据和模型要有来源、边界、适用条件 | 数据合同、stack card、上游来源与 license 记录 | 不解决训练调参 |
| [fast.ai Practical Deep Learning](https://course.fast.ai/) | 先跑起来、先强 baseline、再逐步深入；顶层优先 | baseline 先行；pilot 短跑；不先造框架 | 不提供严格的选择卫生 |
| [Lightning Docs](https://lightning.ai/docs/pytorch/stable/) | 工程层标准化：Module/DataModule/Trainer/callbacks | 基座工程层 | 不管指标、划分、test guard |
| [HF Trainer Docs](https://huggingface.co/docs/transformers/main_classes/trainer) | 成熟 Trainer，但针对 Transformers 优化；自定义模型有边界 | 专用栈矩阵；HF Trainer 不作通用基座 | 不覆盖点检测/分割 |
| [MMEngine Docs](https://mmengine.readthedocs.io/) | Registry/Config/Hook 的成熟视觉训练体系 | 检测/分割专用栈 | 不适配时序/通用多任务 |

## 为什么“看过”不等于“做到”

这些材料提供的是**原则**，不是**门**。原则在压力下会被跳过；门会拒绝启动。

例如：

- “用验证集选模型”是原则；
- “每个 run 必须记录 best step、best val loss、是否 best at cap，test_read 必须为 false”才是门。

一个反复出现的失败不是不知道 early stopping，而是：

1. 选点指标（单视图/单损失）和报告指标（任务指标/集成指标）没有同时记录；
2. best at cap 没有报警；
3. 看到 val loss 更低就默认模型更好，没有检查视图/阈值/方差。

所以“多读几本书”不会自动修复；必须把事故转成：

> **条件 → 不变量 → 边界 → 验证**

这条规则来自技能写作规范，也适用于科研方法论。

## 推荐的学习顺序

1. 先读 Karpathy 的 recipe，建立“先看数据、先过拟合、先 baseline”的直觉；
2. 读 Google Rules of ML，理解训练-服务偏差和 pipeline 债；
3. 读 scikit-learn model selection，理解 fit/select/evaluate 与选择消耗；
4. 读 ML Test Score，补系统化检查；
5. 读所选栈的官方 docs，而不是二手博客；
6. 每读一条，问：**它能变成哪个门？不能变成门的，放参考资料，不放常驻规则。**

## 没有“银弹”的正式理由

- **No Free Lunch**：没有对所有任务最优的算法；
- **分布/评价器/部署单元不同**：统一训练循环不能统一科学合同；
- **选择本身消耗信息**：验证集不是无限的；
- **规格不完整**：真实任务的需求会在实验中变化；
- **未知未知**：再全的 checklist 也不能枚举所有失败。

因此目标不是“找到永不犯错的 pipeline”，而是：

> **建立一个稳定的元流程，让错误尽早暴露，让结论不超过证据。**

这就是本 skill 的定位。
