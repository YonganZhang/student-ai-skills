# Pipeline 基座：边界、失效模式与升级条件

## 1. 定义

- **基座（base）**：面向通用/多任务监督学习的训练工程层。提供配置、数据接口、训练循环、checkpoint、日志、单/多卡、HPO 接入。
- **专用栈（domain stack）**：为某一任务范式提供成熟 recipe、数据变换、模型库和评价器的栈，例如 MMEngine 之于检测/分割，HF Trainer 之于 Transformer/VLM，MONAI 之于医学 3D。
- **适配层（adapter）**：项目自己的 DataModule、LightningModule、loss、evaluator、gates。它不属于任何通用模板。

基座不是“所有任务都能直接跑”的承诺；它是“通用任务少写训练工程，专用任务不强行套”的边界。

## 2. 能力边界

| 维度 | 基座内 | 需要适配 | 基座外 |
|---|---|---|---|
| 数据 | 内存/磁盘张量、固定 shape、标准 collate | 变长、稀疏、多模态、点云、图 | 流式/分布式数据平台、在线特征 |
| 任务 | 分类、回归、密集预测原型、时序、多任务 | 点检测/实例分割原型、简单 3D | 大规模检测/分割、LLM/VLM、RL、GAN、生产 Serving |
| 模型 | 任意 `nn.Module` | 需要自定义 loss/输出结构的模型 | 需要专用并行/量化/服务框架的模型 |
| 训练 | 单卡/多卡 DDP、AMP、梯度累积、断点 | 多 optimizer、复杂 scheduler、RL | 跨节点大规模、异构集群 |
| 评价 | 标准 metric | 匹配/阈值/解码/集成 | 在线 A/B、业务指标 |
| 调参 | Optuna/Ray Tune 接入 | 多目标、约束搜索 | AutoML 平台 |

### 判定规则

满足以下全部条件，才用基座：

1. 任务是通用监督学习，或可拆成通用监督学习；
2. 数据和评价器能用 Python/PyTorch 接口表达；
3. 单卡或单机多卡足够；
4. 没有成熟专用栈能以更低成本覆盖 ≥80% 需求。

否则先读 [候选栈矩阵](stack-matrix.md)，不要先写基座适配。

## 3. 已知失效模式

| 现象 | 原因 | 守卫 | 升级条件 |
|---|---|---|---|
| 模板装不上/API 不兼容 | 模板停在旧版本，Lightning/Hydra 已演进 | 固定 commit、锁依赖、smoke | 修不动或修的成本 > 重选 |
| 自定义 optimizer 不生效 | Lightning 接管了 optimizer/scheduler | 打印 optimizer 成员、参数组、step 前后 LR | 复杂多 optimizer/RL 循环，换 Accelerate/Ignite |
| 多卡结果变差 | 有效 batch、LR、BN、sampler 改变 | 记录 global batch、LR scaling、每卡 batch | 需要跨节点/FSDP 深改 |
| checkpoint 恢复不一致 | RNG、scheduler、EMA、数据顺序未恢复 | strict reload、step0 输出、resume 对拍 | 无法对齐则不用该栈 |
| best 落在预算上限 | 预算不够或曲线仍在降 | `BEST_AT_CAP` 报警；预算允许就扩展，否则标右删失做固定预算比较 | 不得把右删失写成收敛 |
| val loss 最低但部署指标更差 | 选点指标与报告指标不一致 | 同时记录 val loss、部署指标、单视图/D4 | 重定义选择合同；不能看 test 回头选 |
| 验证集被 HPO 用旧 |  trial 太多，选择过拟合 | trial 上限、Hyperband、独立确认集 | 需要 nested CV 或新 holdout |
| 时序分数虚高 | 随机切分泄漏未来/实体 | 按时间/实体切分，gap、滚动验证 | 专用时序栈 |
| 3D 分数虚高 | 各向异性、间距、切片泄漏 | spacing/orientation 进合同，按病人/体积切分 | MONAI |
| 多任务互相拖累 | 梯度冲突、loss 尺度失衡 | 单任务 baseline、grad norm、loss 权重扫描 | 多任务专用调度/架构 |
| HF Trainer 行为意外 | 它默认假设 Transformer 输出/labels | 自定义 `compute_loss`、`compute_metrics`、collator | 非 Transformer 任务优先 Lightning/专用栈 |

## 4. HF Trainer 的准确边界

结论：**不是只能用于 Transformer，但它是 Transformer-first，不是 generic-first。**

- API 上，`Trainer` 接收任意 `torch.nn.Module`，支持分布式、AMP、checkpoint、logging、early stopping、HPO 接入。
- 官方文档明确提示：它针对 Transformers 模型优化，用于其他模型时可能有意外行为；模型应返回 tuple/`ModelOutput`，提供 `labels` 时能计算 loss，多标签用 `label_names`。
- 图像分类（ViT）、音频、多模态都有官方示例；3D/时序也可以，只要自定义 dataset/collator/model 和 loss/metric。
- 对点检测这类输出坐标/热图、需要匹配和阈值解码的任务，默认 `Trainer` 的 `prediction_step`/`compute_metrics` 不够，适配量不小。

适用判断：

| 场景 | 建议 |
|---|---|
| HF 模型、Transformer/VLM/LLM 微调 | 首选 HF Trainer/TRL |
| 图像分类、ViT 微调 | 可用 HF Trainer，也可 Lightning |
| 任意 3D/时序小模型 | 可用，但要自定义 collator/loss/metric；优先专用栈 |
| 点检测/分割/检测 | 不用 HF Trainer 作基座；用 Lightning 适配或 MMEngine/Detectron2 |

## 5. 何时离开基座

出现任一条件，停止在基座上加适配，转专用栈或单独立项：

1. 任务属于检测/分割/LLM/VLM/医学 3D/大规模时序，且专用栈已有成熟 recipe；
2. 基座适配代码超过模型代码，或需要改 Trainer 核心行为；
3. 多卡/跨节点成为主要瓶颈；
4. 评价器需要专用解码/匹配/后处理，基座没有干净接口；
5. 维护成本超过实验收益；
6. license/供应链不允许继续使用当前上游。

离开基座不等于离开 S1–S9。数据合同、划分、基线、选点、test guard 仍按全局标准流程。

## 6. 没有“解决所有问题”的 Pipeline

不存在一个静态 Pipeline 能同时满足：

- 任意任务/任意数据形态；
- 任意模型/任意并行策略；
- 任意评价器/任意业务约束；
- 零适配、零维护、永远正确。

原因是：任务先验、数据合同、评价器、部署单元和失败代价都不同；这些不是训练框架能统一的。
能做到的是**稳定的元流程**：

1. 先选栈（S0），再定任务/指标（S1）；
2. 借成熟轮子，固定版本，写适配层；
3. 用 baseline、positive control、parity、manifest 把错误暴露在结论之前；
4. 用选择卫生防止 val/test 污染；
5. 每个失败转成一条“条件—不变量—边界—验证”的规则，回写 skill；
6. 专用任务及时离开基座。

目标不是“永不犯错”，而是**错误不会静默变成论文结论**。

## 7. 升级/回退

- 上游升级：先读 changelog，固定新 commit，跑 smoke + parity；不直接跟 main。
- 适配层升级：保留旧 runner 作为 oracle；新旧同时跑一个小样本。
- 回退：保留上一固定 commit 与依赖 lock；实验记录写实际版本。
- 任何升级都不覆盖历史 run 目录和已冻结结果。
