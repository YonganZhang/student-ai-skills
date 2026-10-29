# 表格任务：分类、回归、排序

本页把[标准流程](../standard-flow.md) S1–S9 落到"一行一个样本、各列含义不同"的数据上。通用规则只链接；泄漏细节见[泄漏清单](../../leakage-checklist.md)与[数据卫生](../../data-hygiene.md)，本页不重复。

## 1. 适用范围与典型任务

- 行是实体、事件或测量记录，列是异构特征（数值、类别、序数、时间、ID）。
- 分类、回归、排序；科学/工程里的小样本回归（几十到几千行，如岩心物性、材料配方、实验条件 → 性能）。
- 由时间序列做出的滞后特征表也按本页处理，但划分规则以 [time-series.md](time-series.md) 为准。
- 表格与图像/序列联合读[多模态融合](../../multimodal-fusion-design.md)；把图像嵌入作为表格特征的做法见[迁移学习优先](../../transfer-learning-first.md)的 cookbook。

## 2. 数据接口合同

先写清"一行是什么"：一个病人还是一次就诊、一口井还是一个深度点、一个样品还是一次重复测量。行的定义决定第 3 节的独立单位。

| 项 | 写死什么 | 本族常见静默 bug |
|---|---|---|
| 特征类型表 | 每列的类型、单位、合法范围；ID 列与时间列单独标记 | ID 被当数值特征；时间戳当数值导致模型按时间外推 |
| 预测时可见性 | 每列标注"何时可得"：在预测时点之前就已知，还是事后才记录 | 标签发生之后才产生的列（结算结果、复查结论、由标签派生的汇总）混进特征——目标泄漏 |
| 类别编码 | 类别 → 编码的映射只在训练折拟合并随模型保存；未见类别与缺失各有固定编码 | 训练与测试各自 `astype('category')`，同一类别编号不同；目标编码在全数据上算 |
| 缺测 | GBDT 可保留 NaN 走原生缺失分支；神经网络/线性模型填补并加缺失指示列 | 用 0 或 -999 填补后，模型把它当真实取值；填补统计用了全数据 |
| 标签 | 变换（对数、分位）与反变换写死；分类的正类定义 | 目标跨数量级仍用原尺度 RMSE，指标被少数大值主导 |
| 表连接 | 每次 join 前后核对行数与主键唯一性 | 一对多 join 悄悄放大行数，同一实体的复制行跨进不同划分 |

## 3. 划分与独立单位

- 独立单位是**实体/组**（病人、井、批次、供应商），同一组的行只能在同一侧：[GroupKFold / StratifiedGroupKFold](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.StratifiedGroupKFold.html)。
- 有时间先后且部署是预测未来时，按时间划分（[TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html)），或组 × 时间双重留出，四种问题见[划分合同](../../split-design-contract.md)。
- 先去重（完全重复与近重复行）再划分。
- 小样本：重复 K 折或留一组，报告每折分数与单样本影响（[评测对齐](../../evaluation-alignment.md)第 5 条）；数据暴露预算见[划分合同](../../split-design-contract.md)第 10 条。
- 所有拟合步骤（填补、缩放、编码、特征选择、过采样）放在折内，用 scikit-learn `Pipeline` 包住，见[常见陷阱](https://scikit-learn.org/stable/common_pitfalls.html)。

## 4. 指标与评价器

- 分类：阈值无关的 AUROC/AUPRC、log-loss；工作点的 F1、召回@精度；需要概率时报校准。
- 回归：原单位 MAE/RMSE + R²，跨数量级目标同时报对数尺度误差；按组报告并与组均值基线比（[评测对齐](../../evaluation-alignment.md)第 3–4 条）。
- 排序：NDCG@K、MAP，按查询组平均。
- **评价器自检**：完美预测满分；训练段均值预测 R² ≈ 0（在验证段上可能略负）；常数分类预测 AUROC = 0.5；样本权重、分组平均的实现与手算一个小例对拍。

## 5. 强基线与预训练

先跑，再上深度模型：

1. **平凡基线**：均值/多数类、按组均值。
2. **线性/逻辑回归**（标准化 + L2），给出可解释的参考线。
3. **GBDT 三件套**：LightGBM、XGBoost、CatBoost，默认参数 + 验证折早停。类别列多时 CatBoost 的原生类别处理常省事。
4. **TabPFN**：小数据上的预训练表格模型，几乎不用调参；先看其 README 中各版本的行数/特征数上限与权重许可（见第 11 节）。
5. 之后才考虑 MLP、FT-Transformer 等深度模型；若赢不了调好的 GBDT，先查数据与划分，不先加模块。

为什么先 GBDT：Grinsztajn et al.（[arXiv 2207.08815](https://arxiv.org/abs/2207.08815)）在 45 个数据集上发现，中等规模（约 1 万行）时树模型仍是最优，且不计其速度优势。

## 6. 增强与正则

- 表格数据一般没有安全的通用增强；SMOTE 之类过采样只在训练折内做，并在不过采样的验证折上评估。
- 主要正则来自模型本身：GBDT 的 `min_child_samples`、行/列子采样、L1/L2、树深或叶子数；神经网络用权重衰减、dropout 与早停。
- 目标编码必须折内计算并加平滑；在全数据上算等于把标签写进特征。
- 特征选择也是模型选择：只在训练折上做，见[选择卫生](../../selection-hygiene.md)。

## 7. 体检要点（S5）

做法与工具见[排错分层](../../triage/README.md)；本族的具体检查：

| 检查 | 做法 | 反向对照 |
|---|---|---|
| 目标泄漏扫描 | 逐列单变量 AUC/R²，异常高的列（如 > 0.95）逐个追来源与记录时间 | 人为加入一列"标签 + 小噪声"，扫描必须把它排第一 |
| 标签打乱 | 打乱训练标签后完整重跑管线，分数应回到平凡基线 | 若打乱后仍明显高于基线，说明有泄漏通道（如 ID、行序、重复行） |
| 对抗验证 | 训练一个区分"训练行 vs 测试行"的分类器，AUC 接近 0.5 为好 | 把一列只在测试段出现的取值偏移加进去，AUC 必须上升 |
| 折内拟合 | 断言所有 `fit` 只见过训练折索引 | 故意在全数据上拟合编码器，断言必须触发 |
| 组隔离 | 断言每个组 ID 只出现在一侧 | 随机划分时断言必须失败 |
| 小样本过拟合 | 神经网络在几十行上训练误差接近 0 | 故意制造训练故障（梯度断开、新参数漏进优化器、学习率为 0）必须达不到；随机标签能被大模型记住，不能当这里的反例（随机标签泄漏检查放在独立留出集） |

S6 逐格检查按[接线门禁](../../../../mlgain-integrate-component/references/integration-sanity-checks.md)；特征是否合理按[特征与数据合理性](../../../../mlgain-integrate-component/references/feature-and-data-reasonableness.md)。

## 8. 常见模块与放置

- 表格上收益最大的通常是**特征**（领域公式派生量、组内统计、比率），而不是网络模块；派生特征同样遵守折内拟合与预测时可见性。
- 深度模型里常见改动位置：数值特征的嵌入层、类别嵌入、跨列注意力；接入方式与放置理论见[放置理论](../../../../mlgain-integrate-component/references/architecture-placement-theory.md)、[残差门控](../../../../mlgain-integrate-component/references/residual-gating-safe-integration.md)。
- 外部预训练嵌入（图像、文本）降维后拼进 GBDT，见[迁移学习优先](../../transfer-learning-first.md)。
- 每个改动配同容量/同预算对照：[受控比较](../../../../mlgain-integrate-component/references/controlled-comparison.md)。

## 9. 调参起点

以下是起点区间，按[调参](../../tuning/README.md)在验证折上确认；LightGBM 官方建议见[参数调优](https://lightgbm.readthedocs.io/en/stable/Parameters-Tuning.html)。

- LightGBM：`learning_rate` 0.02–0.1，树数由早停决定；`num_leaves` 15–255；`min_child_samples` 5–100（小样本取大）；`feature_fraction`、`bagging_fraction` 0.5–1；`lambda_l1/l2` 0–10。
- 顺序：先定学习率并用早停定树数 → 树复杂度（`num_leaves`/深度）→ 叶子最小样本 → 子采样 → 正则。小样本时优先调大叶子最小样本与正则，不调高复杂度。
- 神经网络换架构后先重调学习率与权重衰减；GBDT 换特征集后至少重调树复杂度与早停。

## 10. 已验证的经验

- **树模型仍是中等规模表格的强基线**：Grinsztajn et al., NeurIPS 2022（[arXiv 2207.08815](https://arxiv.org/abs/2207.08815)），并指出神经网络要应对无信息特征、保持数据朝向、学习不规则函数。
- **TabPFN**：Hollmann et al., *Accurate predictions on small data with a tabular foundation model*, Nature 2025（[doi:10.1038/s41586-024-08328-6](https://doi.org/10.1038/s41586-024-08328-6)）。
- **小样本案例**：约 100 个样品、目标跨数量级，十余轮换模型无效，根因在标签、指标尺度、划分与采集上下文特征，见[小样本重尾回归案例](../../case-studies/small-sample-heavy-tail-regression.md)。
- **泄漏的数字特征**：结果"太好"按[泄漏清单](../../leakage-checklist.md)排查；结果"很吵"按[选择卫生](../../selection-hygiene.md)排查。

## 11. 推荐库与工具

| 库 | 用途 | 许可（GitHub 元数据，2026-10-22 核） |
|---|---|---|
| [LightGBM](https://github.com/lightgbm-org/LightGBM)（原 microsoft/LightGBM，已迁移） | GBDT 基线，速度快 | MIT |
| [XGBoost](https://github.com/dmlc/xgboost) | GBDT 基线 | Apache-2.0 |
| [CatBoost](https://github.com/catboost/catboost) | GBDT，原生类别特征处理 | Apache-2.0 |
| [TabPFN](https://github.com/PriorLabs/TabPFN) | 小数据预训练表格模型 | 代码 Apache-2.0；**权重另行许可**：README 称 TabPFN-2.5 及以后版本权重为非商用许可，TabPFN-2 权重为附署名要求的 Prior Labs License；首次使用需登录接受许可 |
| [scikit-learn](https://scikit-learn.org/stable/modules/cross_validation.html) | 划分器、`Pipeline`、线性基线 | BSD-3-Clause |
| [Optuna](https://github.com/optuna/optuna) | 可续跑的超参搜索（本技能包装见[调参](../../tuning/README.md)） | MIT |
| [cleanlab](https://github.com/cleanlab/cleanlab) | 用 OOF 概率找疑似错标行 | Apache-2.0 |
| [Captum](https://github.com/meta-pytorch/captum) | 神经网络特征归因（只作解释辅助） | BSD-3-Clause |
