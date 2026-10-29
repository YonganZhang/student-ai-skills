# 整图视觉任务：分类、回归、检索

本页把[标准流程](../standard-flow.md) S1–S9 落到"一张图出一个答案"的任务上。通用规则只链接；本页只写这个任务族特有的做法和坑。

## 1. 适用范围与典型任务

- **分类**：单标签（softmax）或多标签（逐类 sigmoid）；缺陷/病灶有无、材料相别、显微图像质量分级。
- **回归**：由图预测一个或几个连续量（厚度、浓度、年龄、性能参数）。
- **检索/度量学习**：输出嵌入向量，按相似度找同一实体或近似样本。
- 逐像素输出读 [vision-dense.md](vision-dense.md)；图像与时序/表格联合读[多模态融合](../../multimodal-fusion-design.md)。

## 2. 数据接口合同

样本单位是"一张图 + 一个标签（或一个身份）"。同一物体多次拍摄的多张图不是多个独立样本，见第 3 节。

| 项 | 写死什么 | 本族常见静默 bug |
|---|---|---|
| 图像张量 | `[B,3,H,W]` float32；通道顺序 RGB；mean/std 与输入尺寸跟随预训练模型（timm 可用 `timm.data.resolve_model_data_config(model)` 取） | OpenCV 读出 BGR 直接喂 RGB 权重；EXIF 旋转没处理；训练与推理的缩放/裁剪比例不同 |
| 灰度/多通道 | 单通道如何映射到 3 通道；超过 3 通道时首层如何初始化 | 灰度图被复制成 3 通道但统计仍按自然图像 |
| 标签编码 | 类别名 → 索引的映射表写盘并随模型保存；多标签用 0/1 向量；回归目标的标准化参数只在训练段拟合 | `ImageFolder` 按字母序编号，新增一类后所有索引平移；回归预测忘了反标准化 |
| 缺测/未知 | 未知标签用忽略值，不当作某一类 | "其他"类混入无法判定的样本，压低所有类的精度 |
| 预测时可见性 | 推理时可得的元数据（相机、批次、放大倍数）才可作输入 | 文件名或目录名里藏着标签，模型学到路径而非内容 |

另一个常见 bug：评估时没有切 `model.eval()`，BatchNorm 用当前 batch 统计，分数随 batch 大小波动。

## 3. 划分与独立单位

- 独立单位是**患者/样品/个体、拍摄 session、相机或站点**。同一个体的多张图分到训练和验证，测到的是"认得这个个体"。
- 先做近重复检测（感知哈希或预训练嵌入的余弦相似度），近重复图归同组。
- 分组且需保持类别比例时用 [StratifiedGroupKFold](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.StratifiedGroupKFold.html)。
- 检索任务按**身份**划分：验证身份完全不在训练中，查询时排除查询图本身。
- 早停、阈值、TTA 选择都在 select 段做：[划分合同](../../split-design-contract.md)、[选择卫生](../../selection-hygiene.md)。

## 4. 指标与评价器

- **分类**：阈值无关的 AUROC/AUPRC、log-loss；工作点的准确率、F1、指定特异度下的灵敏度。宏平均与微平均分开报，稀有类单列；需要概率时加校准误差（ECE）。
- **回归**：原单位 MAE/RMSE + R²，并与"训练段均值"基线比；按组报告，见[评测对齐](../../evaluation-alignment.md)第 4 条。
- **检索**：Recall@K、mAP；写清 gallery 是否含同一身份的其他图。
- **评价器自检**：完美预测得满分；常数预测时 AUROC = 0.5、准确率 = 多数类比例；把标签与预测的类别映射故意错一位，分数必须崩；多标签时检查是按类平均还是按样本平均。

## 5. 强基线与预训练

先跑，再加模块：

1. **平凡基线**：多数类 / 训练段均值。
2. **冻结特征 + 线性头**：DINOv2、CLIP（open_clip）或 timm 模型抽特征，接逻辑回归/岭回归或 GBDT。几分钟出结果，常是小数据上最难打败的基线。
3. **整体微调**：timm 预训练 CNN（ConvNeXt、EfficientNet）或 ViT，换分类/回归头。

冻结还是微调、数据量阈值、降维与多 backbone 集成见[迁移学习优先](../../transfer-learning-first.md)。输入分辨率与预训练对齐；领域差异大（显微、遥感、医学）时同时试领域预训练与通用预训练。

## 6. 增强与正则

- 常用且一般安全：RandomResizedCrop、水平翻转、小幅颜色抖动、RandAugment/TrivialAugment、mixup/cutmix（分类）。
- **按语义收窄**：文字、左右有别的结构不能翻转；颜色本身是标签依据时不做颜色抖动；回归目标与尺度相关（如尺寸、厚度）时不做随机缩放，或同步换算标签。
- mixup/cutmix 用于回归要证明标签可线性混合。
- 泄漏：用全数据（含验证/测试）算 mean/std；按测试集分数挑 TTA 组合。用预训练权重时直接用其官方 mean/std。
- 正则：label smoothing、权重衰减、stochastic depth、EMA。

## 7. 体检要点（S5）

做法与工具见[排错分层](../../triage/README.md)；本族的具体检查：

| 检查 | 做法 | 反向对照 |
|---|---|---|
| 评价器 | 第 4 节自检 | 预测打乱顺序后与标签对不上，分数必须回到随机水平 |
| 真实批次叠图 | DataLoader 出口取 batch，反归一化后把类别名/数值写在图上存 PNG 人看；按类各抽几张 | 标签打乱后再看，人眼应能看出不符；不能看出说明类别本身难辨，先确认标注定义 |
| 映射往返 | 类别名 → 索引 → 类别名，训练、推理两个进程各算一次 | 删掉一个类目录重建映射，必须报错而非静默平移 |
| 小样本过拟合 | 32–64 张，在训练用的变换下训练到样本内准确率接近 1 | 故意制造训练故障（梯度断开、新参数漏进优化器、学习率为 0）必须达不到；随机标签能被大模型记住，不能当这里的反例（随机标签泄漏检查放在独立留出集） |
| eval 模式 | 同一批数据，batch=1 与 batch=64 的预测一致 | 故意留在 train 模式，两者必须不一致 |
| 错标扫描 | 用交叉验证的 OOF 概率跑 cleanlab，人工复核排名靠前的样本 | 人为翻转 2% 标签，应大部分被排在前面 |

S6 逐格检查按接线门禁（mlgain 组件接入参考库，可选，本包未包含）。

## 8. 常见模块与放置

- 先试改动小、收益常见的：换更强/更合适的预训练 backbone、提高输入分辨率、换头（池化方式、检索用 GeM 池化或 margin 类损失头）。
- 通道/空间注意力（SE、CBAM 类）一般放在 stage 末的残差分支内；新分支零初始化接入：残差门控（mlgain 组件接入参考库，可选，本包未包含）、函数保持插座（mlgain 组件接入参考库，可选，本包未包含）。
- 放在哪、为什么：放置理论（mlgain 组件接入参考库，可选，本包未包含）、框架惯例（mlgain 组件接入参考库，可选，本包未包含）；timm 的换件方式见 pipeline 包目录（mlgain 组件接入参考库，可选，本包未包含） C1。
- 同容量对照与配对 seed：受控比较（mlgain 组件接入参考库，可选，本包未包含）。

## 9. 调参起点

以下是起点区间，按[调参](../../tuning/README.md)在 select 段确认。

- 微调：AdamW；CNN 学习率约 1e-4–1e-3，ViT 约 1e-5–1e-4，可加分层学习率衰减；权重衰减 CNN 约 1e-4–1e-2、ViT 约 0.05；余弦 + warmup；label smoothing 0.1 起。
- 线性探针：学习率可大一个数量级，正则强度是主要旋钮。
- batch 取显存允许的最大值，不当调参项。
- 换架构后先重调：学习率 → 权重衰减 → 训练轮数/步数 → 增强强度；输入分辨率改变时一并重调学习率。

## 10. 已验证的经验

- **Bag of Tricks**（[arXiv 1812.01187](https://arxiv.org/abs/1812.01187)）：学习率随 batch 线性缩放、warmup、余弦衰减、label smoothing、mixup 等训练细节合起来，ResNet-50 的 ImageNet top-1 从 75.3% 升到 79.29%（摘要原文数字）。启示：比较架构前先确认训练配方一致。
- **ResNet strikes back**（[arXiv 2110.00476](https://arxiv.org/abs/2110.00476)）：只换训练配方，原版 ResNet-50 达到 80.4% top-1（摘要原文数字），配方与模型一并发布在 timm；旧论文里的基线常被低估。
- **DINOv2**（[arXiv 2304.07193](https://arxiv.org/abs/2304.07193)）：目标是不经微调即可跨任务使用的通用视觉特征；据此第 5 节先跑冻结特征基线（推断，具体任务仍需实测）。
- **Confident Learning**（[arXiv 1911.00068](https://arxiv.org/abs/1911.00068)）：用 OOF 预测概率估计并定位错标样本，是 cleanlab 的方法来源。
- 本地案例中暂无整图视觉条目；新增时登记到[案例索引](../../case-studies/INDEX.md)。

## 11. 推荐库与工具

| 库 | 用途 | 许可（GitHub 元数据，2026-10-22 核） |
|---|---|---|
| [timm](https://github.com/huggingface/pytorch-image-models) | 预训练 backbone、数据配置、训练配方 | Apache-2.0（权重许可逐模型看） |
| [open_clip](https://github.com/mlfoundations/open_clip) | CLIP 类图文模型的图像特征 | MIT 式自定义许可（GitHub 标为 NOASSERTION） |
| [DINOv2](https://github.com/facebookresearch/dinov2) | 自监督冻结特征 | Apache-2.0 |
| [Lightning](https://github.com/Lightning-AI/pytorch-lightning) | 自写循环时的训练框架 | Apache-2.0 |
| [kornia](https://github.com/kornia/kornia) | GPU 增强 | Apache-2.0 |
| [torchinfo](https://github.com/TylerYep/torchinfo) | 逐层 shape 与参数量 | MIT |
| [cleanlab](https://github.com/cleanlab/cleanlab) | 错标检测（需要 OOF 概率） | Apache-2.0 |
| [FiftyOne](https://github.com/voxel51/fiftyone) | 浏览数据与预测、按错误排序、找近重复 | Apache-2.0 |
| [Captum](https://github.com/meta-pytorch/captum) | 归因图（只作解释辅助，不当因果证据） | BSD-3-Clause |

注意：原 Albumentations 仓库已归档（MIT），后继 AlbumentationsX 为 AGPL-3.0，引入前确认许可。
