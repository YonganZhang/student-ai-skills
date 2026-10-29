# 时序任务：预测、序列回归、参数→轨迹代理

本页把[标准流程](../standard-flow.md) S1–S9 落到按时间排列的数据上。通用规则只链接；时序泄漏的七类细节在[泄漏清单](../../leakage-checklist.md)，面板数据的划分问题在[划分合同](../../split-design-contract.md)，本页不重复。

## 1. 适用范围与典型任务

- **预测（forecasting）**：由过去 L 步（加协变量）预测未来 H 步；单序列、多变量或多实体面板。
- **序列回归/分类**：一个窗口 → 一个标量或类别（如由传感器窗口估计当前状态）。
- **参数→轨迹代理**：静态参数向量 → 多通道轨迹，推理时没有历史序列；直接用 [model-zoo](../../model-zoo/SOURCES.md)。
- 异常检测、缺失填补、时序分类的现成包见 pipeline 包目录（mlgain 组件接入参考库，可选，本包未包含） T4–T8；多源传感器融合读[多模态融合](../../multimodal-fusion-design.md)。

## 2. 数据接口合同

样本单位是"一个起报时刻 t0 的一个窗口"（含输入段与目标段）。同一序列上相邻窗口高度重叠，不是独立样本。

| 项 | 写死什么 | 本族常见静默 bug |
|---|---|---|
| 张量轴 | `[B, L, C]` 还是 `[B, C, L]`；TSLib 一类模型用 `[B, L, C]`，`nn.Conv1d` 要 `[B, C, L]` | 轴放反后 shape 恰好能跑（L 与 C 相等或被广播），模型在"通道"上做卷积 |
| 时间轴 | 频率、时区、夏令时、重复与缺失时间戳的处理；时间戳表示区间起点还是终点 | 小时数据按区间终点记录，与按起点记录的协变量错位一步 |
| 目标对齐 | 目标段是 `t0+1 … t0+H`；`shift` 方向；horizon 从 1 还是 0 计 | 差一步（off-by-one），分数略好且无人察觉 |
| 协变量分类 | 静态、历史观测（只到 t0）、未来已知（起报时已确定，如日历、计划值、已发布的预报） | 把未来实测值当"未来已知"；预报用了发布时间晚于 t0 的版本 |
| 缺测 | NaN 保留并附 mask 与"距上次观测的时长" | 先插值再切窗，插值用到了 t0 之后的点 |
| 归一化 | 训练段拟合的全局统计，或逐窗口（RevIN 式）只用输入段统计 | 用整条序列算 mean/std；逐窗口归一化时把目标段也算进统计 |

数据加载格式与长度约束可参考 [TimesFM 数据准备](../../timesfm/references/data_preparation.md)。

## 3. 划分与独立单位

- 按**连续时间块**划分，训练段在前，验证、测试段依次在后；滚动起点（rolling origin）或扩展窗口做多次评估。
- 训练与验证之间留间隔，至少覆盖 `lookback + horizon`，有强自相关时再加长。scikit-learn 的 [TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html) 有 `gap` 参数；方法背景见 [FPP3 时序交叉验证](https://otexts.com/fpp3/tscv.html)。
- 多实体面板先回答"已见实体的未来"还是"未见实体"，四种问题与对应划分见[划分合同](../../split-design-contract.md)。
- 早停与超参只在验证块上选：[选择卫生](../../selection-hygiene.md)。参数→轨迹代理的独立单位是"一次模拟/一组参数"，按参数样本划分，不按时间步。

## 4. 指标与评价器

- 原单位 MAE/RMSE；跨序列比较用 MASE（以季节朴素预测的样本内误差为尺度，见 [FPP3 精度评估](https://otexts.com/fpp3/accuracy.html)）。目标含零或接近零时不用 MAPE/sMAPE 作主指标。
- 概率预测加分位数 pinball loss 或 CRPS，并检查区间覆盖率。
- **按 horizon 分段报**（第 1 步与第 H 步的误差往往差很多），按实体宏平均与合并计算分开报。
- 阈值类输出（告警、异常）另报工作点指标。
- **评价器自检**：预测 = 真值时误差为 0；季节朴素预测的 MASE 在训练段约为 1；把预测整体前移/后移一步重算——若移动后分数更好，说明对齐有错或存在泄漏。

## 5. 强基线与预训练

先跑，再加模块：

1. **朴素、季节朴素、漂移**；再加 ETS/ARIMA（statsforecast 一行调用）。新模型赢不了季节朴素就先查数据。
2. **线性模型**：DLinear/NLinear（原始实现见 [model-zoo SOURCES](../../model-zoo/SOURCES.md)）。
3. **GBDT + 滞后特征**：滞后、滚动统计（只用 t0 以前）、日历特征，接 LightGBM；面板数据上常是强基线，做法见 [tabular.md](tabular.md)。
4. **零样本基础模型**：TimesFM、Chronos，见本技能 [TimesFM 参考](../../timesfm/REFERENCE.md)。注意（推断）：公开基准序列可能在其预训练语料中，在公开基准上的零样本成绩要先查预训练数据说明。
5. **参数→轨迹**：先用条件 Transformer，再比更复杂的骨干（实测记录未随本包发布；适配实现见 [model-zoo](../../model-zoo/SOURCES.md)）。

## 6. 增强与正则

- 相对安全：随机起点采样窗口、小幅加噪、幅度缩放（模型逐窗口归一化时）、随机遮蔽部分输入步并给 mask。
- 危险：时间反转、窗口内打乱（破坏因果顺序）；跨划分边界取窗口；中心化滑动平均、双向滤波、全序列去趋势或插值——都把未来信息带进当前输入。
- 正则：dropout、权重衰减、在验证块上早停；通道独立（每个变量共享参数）本身就是一种强正则。

## 7. 体检要点（S5）

做法与工具见[排错分层](../../triage/README.md)；本族的具体检查：

| 检查 | 做法 | 反向对照 |
|---|---|---|
| 因果性 | 只改 t0 之后的原始数据，重新走完整特征管线，t0 处的输入与预测必须逐位不变 | 故意换成中心化滚动平均，检查必须报错 |
| 轴约定 | 构造只有通道 0 随时间线性上升的合成序列，检查模型输入里"时间轴"那一维确实单调 | 把 `[B,L,C]` 转置后喂入，单调性检查必须失败 |
| 目标对齐 | 用 `y(t)=x(t-k)` 的合成数据，最优滞后应恰为 k | 故意把 shift 方向写反，最优滞后变成 -k |
| 统计来源 | 断言归一化、填补、编码的拟合行全部早于训练截止时间 | 把测试段混入拟合，断言必须触发 |
| 小样本过拟合 | 几十个窗口、训练变换下，样本内误差接近 0 | 故意制造训练故障（梯度断开、新参数漏进优化器、学习率为 0）必须达不到；随机标签能被大模型记住，不能当这里的反例（随机标签泄漏检查放在独立留出集） |
| 叠图 | 预测、真值、季节朴素三条线画在同一张图，按 horizon 抽几个起报点人看 | 把预测前移一步再画，人眼应看得出错位 |

S6 逐格检查按接线门禁（mlgain 组件接入参考库，可选，本包未包含）。

## 8. 常见模块与放置

- **输入侧**：逐窗口归一化（RevIN 类）、趋势/季节分解、patching、通道独立 vs 通道混合——这几项常比换主干影响大。
- **协变量编码**：静态条件注入、未来已知变量单独分支；参数→轨迹任务统一用条件注入适配，见 [model-zoo SOURCES](../../model-zoo/SOURCES.md)。
- **多源融合**：拼接 vs 交叉注意力的同输入比较，见[多模态融合](../../multimodal-fusion-design.md)。
- 现成包的换件位置：pipeline 包目录（mlgain 组件接入参考库，可选，本包未包含） T1–T3；放置理论与零初始化接入：放置理论（mlgain 组件接入参考库，可选，本包未包含）、残差门控（mlgain 组件接入参考库，可选，本包未包含）；特征合理性：特征与数据合理性（mlgain 组件接入参考库，可选，本包未包含）。

## 9. 调参起点

以下是起点区间，按[调参](../../tuning/README.md)在验证块上确认。

- Adam/AdamW，学习率约 1e-4–1e-3；batch 32–256；训练轮数不多，配验证块早停或固定步数后按验证挑检查点。
- **lookback 长度**是首要结构性超参，可从 horizon 的 2–8 倍起扫，并覆盖至少一个主要季节周期。
- 换架构后先重调：学习率 → lookback → dropout/权重衰减 → 训练步数。比较不同容量的模型时同时报参数量，例如 DLinear 与加宽的 DLinear-wide 不能只比误差（原始实测记录未随本包发布）。

## 10. 已验证的经验

- **简单线性很强**：DLinear 论文（Zeng et al., AAAI 2023，见 [model-zoo SOURCES](../../model-zoo/SOURCES.md)）（[arXiv 2205.13504](https://arxiv.org/abs/2205.13504)）在九个真实数据集的长期预测基准上，单层线性模型在所有情形下都超过了当时的 Transformer 预测器（摘要原文）。
- **参数→轨迹实测**（Volve/Norne 公开油田数据的条件代理）：条件 Transformer 是强基线，FNO、DeepONet 未胜出；容量与搜索预算必须一起报。原始记录未随本包发布，结果只适用于当时的数据与预算。
- **AR 残差校正的假涨**：残差滞后用了验证段真实目标，评分从 0.8999 假涨到 0.9393，见[泄漏清单](../../leakage-checklist.md)的实战例。
- **基础模型**：TimesFM（[arXiv 2310.10688](https://arxiv.org/abs/2310.10688)）、Chronos（[arXiv 2403.07815](https://arxiv.org/abs/2403.07815)；Chronos-2 技术报告 [arXiv 2510.15821](https://arxiv.org/abs/2510.15821)）。零样本结果先与季节朴素和 GBDT 比，再决定是否微调。

## 11. 推荐库与工具

| 库 | 用途 | 许可（GitHub 元数据，2026-10-22 核） |
|---|---|---|
| [statsforecast](https://github.com/Nixtla/statsforecast) | 朴素/ETS/ARIMA 等统计基线，快 | Apache-2.0 |
| [neuralforecast](https://github.com/Nixtla/neuralforecast) | 神经预测模型集合（Lightning 底座） | Apache-2.0 |
| [Darts](https://github.com/unit8co/darts) | 统一接口跑统计/GBDT/神经模型，含回测 | Apache-2.0 |
| [GluonTS](https://github.com/awslabs/gluonts) | 概率预测模型与评估 | Apache-2.0 |
| [sktime](https://github.com/sktime/sktime) | sklearn 风格的时序工具与划分器 | BSD-3-Clause |
| [Time-Series-Library](https://github.com/thuml/Time-Series-Library) | 标准长期预测基准与 40+ 模型（仅 vendor，见包目录 T3） | MIT |
| [TimesFM](https://github.com/google-research/timesfm) | 零样本预测基础模型 | Apache-2.0 |
| [Chronos](https://github.com/amazon-science/chronos-forecasting) | 零样本预测基础模型（含 Chronos-Bolt、Chronos-2） | Apache-2.0 |
| [Optuna](https://github.com/optuna/optuna) | 可续跑的超参搜索（本技能包装见[调参](../../tuning/README.md)） | MIT |
| [Lightning](https://github.com/Lightning-AI/pytorch-lightning) / [torchinfo](https://github.com/TylerYep/torchinfo) | 自写循环 / 核对 shape 与参数量 | Apache-2.0 / MIT |

pytorch-forecasting 的版本约束与 Lightning 命名空间分裂问题见 pipeline 包目录（mlgain 组件接入参考库，可选，本包未包含），不在此重复。
