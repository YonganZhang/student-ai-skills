# 视觉密集预测：点/中心检测、分割、计数

本页把[标准流程](../standard-flow.md) S1–S9 落到"每个像素/体素都要预测"的任务上。通用规则（划分、选择、调参、排错）只链接，不重复；本页只写这个任务族特有的做法和坑。

## 1. 适用范围与典型任务

- **点/中心检测**：原子柱、荧光斑点、细胞核中心、冷冻电镜断层里的颗粒或鞭毛马达；输出是坐标列表（可带类别和置信度）。
- **语义/实例分割**：逐像素类别或逐实例掩膜。
- **计数**：由点检测数个数，或由密度图积分。
- 2D 图、2.5D（相邻切片当通道）、3D 体数据都适用。整图一个标签的任务读 [vision-image.md](vision-image.md)。

## 2. 数据接口合同

样本单位是"一张图/一个体 + 它的全部标注"。训练时的随机裁剪是采样方式，不是独立样本。

| 项 | 写死什么 | 本族常见静默 bug |
|---|---|---|
| 图像张量 | `[B,C,H,W]` 或 `[B,C,D,H,W]`，float32；原始 dtype（uint8/uint16/float）与归一化方式（逐图百分位还是全局统计） | 16-bit 图按 /255 归一化后整片饱和；训练逐图归一化、推理用全局统计 |
| 坐标约定 | `(row, col)` 还是 `(x, y)`；像素中心记作整数还是 +0.5；单位是像素还是物理长度（Å、nm）及体素间距 | 方形图上 x/y 颠倒不报错；系统性 0.5 px 偏移；重采样后坐标没乘缩放比 |
| 标签编码 | 点 → 高斯热图（σ 用物理尺度定）或偏移/流场；分割 → int64 类别号与忽略值 | 用插值缩放掩膜产生不存在的类别号；换分辨率后 σ 仍按旧像素数 |
| 缺测与掩膜 | 只标了部分区域的图要有 valid mask；图边缘排除带宽度 | 未标注区域被当成负样本，模型学会"不检出" |
| 预测时可见性 | 推理是整图还是滑窗；滑窗大小、重叠、拼接权重 | 训练用裁剪、验证用整图缩放，两边分布不同 |

断言写在 Dataset 出口：坐标落在裁剪范围内、热图在每个标注点处约为 1、掩膜取值只在合法集合内。

## 3. 划分与独立单位

- 独立单位是**样品、采集 session、一次扫描/一个断层**，不是 patch、不是同一体积的不同切片、不是同一视野的连续帧。同一张大图切块分到训练与验证，只能叫内插评估。
- 图很少时按图做留一或 K 折。CZII 第 1 名：7 个断层做 5 折，每折 2 个验证、5 个训练。
- 阈值、解码器、NMS 半径都要在 select 段选，划分绑数据种子：[划分合同](../../split-design-contract.md)、[选择卫生](../../selection-hygiene.md)。

## 4. 指标与评价器

- **点检测**：按距离阈值做一对一匹配（匈牙利或按置信度贪心）后算 P/R/F1 或 Fβ；AP 按置信度排序积分；定位误差只在匹配对上算。匹配距离用物理单位写死，按类别分别给出（CZII 的指标是 β=4 的 F-beta，偏重召回；匹配距离以比赛页定义为准）。
- **分割**：Dice/IoU 写明是逐图再平均还是全体素合并；实例分割用 AP@IoU。
- **计数**：MAE 与相对误差，并按图报告。
- 两类都报：**阈值无关**（AP、PR 曲线）和**工作点**（select 段选阈值后的 F1）。只在 F1 上有差异时，先怀疑阈值。
- 按图宏平均和合并计算分开报；稀有类单列。
- **评价器自检**：真值对真值 = 1；空预测 = 0；平移小于匹配距离仍全匹配、大于则全不匹配；重复预测只算一个 TP；空真值 + 空预测**不能**得 1 进入选择（[选择卫生](../../selection-hygiene.md)的案例里零检出解码器因此被打满分）。能拿到官方评分代码时逐例对拍，见[评测对齐](../../evaluation-alignment.md)第 2 条。

## 5. 强基线与预训练

先跑，再加模块：

1. **非学习基线**：LoG/DoG 或局部极大值 + 阈值。它给出噪声地板，也检验指标是否有区分力。
2. **U-Net + 高斯热图 + 局部极大值解码**（CenterNet 式 `x * (x == maxpool(x))` 去重）。
3. **现成专用工具**：荧光斑点用 Spotiflow（带预训练模型、阈值无关、亚像素）；3D 用 MONAI 的 SegResNet/DynUNet；2D 用 smp 的 U-Net 接 timm 编码器。

预训练来源：2D 用 timm 的 ImageNet 编码器；3D 可用 MONAI model zoo（CZII 第 1 名用 `wholeBody_ct_segmentation` 的 SegResNet 权重）。单通道灰度图接三通道权重时，复制通道或把首层卷积权重按通道求和，输入统计与预训练对齐。通用决策见[迁移学习优先](../../transfer-learning-first.md)。

## 6. 增强与正则

- **几何变换必须图标同步**：掩膜用最近邻；坐标用同一变换矩阵变换后**重新生成**热图，不插值旧热图。
- 安全：物理上对称时的翻转与 90° 旋转、小尺度抖动；只作用于图像的亮度、对比度、噪声。
- 要按物理约束收窄：物体有手性或方向、采集各向异性（如断层 Z 向分辨率差）时，只做允许的旋转。CZII 第 1 名：绕 Z 轴 ±180°，绕 X/Y 只 ±10°，尺度 ±5%，三轴翻转。
- **TTA 必须是训练增强的子集**。训练没用翻转/旋转，推理端做 D4 平均得到的分数变化是伪影，不能当模型能力或模块效果；TTA 前后都在 select 段重选阈值。
- 泄漏：copy-paste、mixup 的素材来自验证图；用全部数据算归一化统计。
- 不一定有效：CZII 第 1 名报告 mixup、copy-paste、random erasing 本地 CV 升而榜单降。
- 正则：EMA、多个检查点权重平均（CZII 第 1 名保存 top-5 检查点后平均，几乎总能提高 F-beta）。

## 7. 体检要点（S5）

做法与工具见[排错分层](../../triage/README.md)；本族的具体检查和证明检查有效的反向对照：

| 检查 | 做法 | 反向对照 |
|---|---|---|
| 评价器 | 第 4 节自检全过 | 把预测整体平移超过匹配距离，分数必须掉到约 0 |
| 真实批次叠图 | 取 DataLoader 出口的 batch，标注点画在图上存 PNG 人看；统计热图在标注点的值、标注点相对全图的亮度差 | 行列互换后同一统计应接近 0；不变说明检查看不到标签 |
| 增强同步 | 合成已知点的图过同一套变换，亮点与变换后坐标距离中位数 < 0.5 px | 只变换图像不变换坐标，距离必须明显变大 |
| 小样本过拟合 | 1–4 张图，在训练用的变换下评估，样本内 AP 接近 1 | 故意制造训练故障（梯度断开、新参数漏进优化器、学习率为 0）必须达不到；随机标签能被大模型记住，不能当这里的反例（随机标签泄漏检查放在独立留出集）；**不要用"loss 减半"判断**：软高斯目标的 BCE 下限 > 0，loss 平台不代表没学会 |
| 滑窗拼接 | 整图滑窗推理与单块推理在块中心区域一致 | 关掉拼接权重，边缘处应出现可见接缝 |
| 坐标单位 | 坐标经重采样再还原，往返误差 < 0.1 px | 故意少乘一次缩放比，误差必须报警 |

S6 的逐格检查（第 0 步等价、优化器成员、有效贡献、强制关闭等）按接线门禁（mlgain 组件接入参考库，可选，本包未包含）执行。

## 8. 常见模块与放置

- **输出步长与颈部**：点检测不一定要全分辨率输出。CZII 第 1 名：步长 2 比步长 1 只低约 0.002，提速近 50%；BYU 第 3 名：步长 16 + 简单 FPN 颈部融合低层特征。
- **头**：热图 + 偏移头给亚像素；也可做无锚点的点检测头（CZII 第 1 名仿 PP-YOLO 损失，用关键点相似度 `exp(-d²/2r²)` 代替 IoU）。
- **解码器跳连**：注意力门、多尺度融合常对小目标有用；换更强的预训练编码器常比加模块收益大。
- **输入侧**：2.5D 把相邻切片当通道。
- 新分支以零初始化残差或门控接入：残差门控（mlgain 组件接入参考库，可选，本包未包含）、函数保持插座（mlgain 组件接入参考库，可选，本包未包含）；放在哪：放置理论（mlgain 组件接入参考库，可选，本包未包含）、框架惯例（mlgain 组件接入参考库，可选，本包未包含）；包的换件位置见 pipeline 包目录（mlgain 组件接入参考库，可选，本包未包含） C1/C2 与 MONAI。每个模块配同容量对照：受控比较（mlgain 组件接入参考库，可选，本包未包含）。

## 9. 调参起点

以下是起点区间，不是结论；按[调参](../../tuning/README.md)在 select 段确认。

- AdamW；从头训练的 U-Net 学习率约 1e-3，预训练编码器约 1e-4 或分层学习率；权重衰减 1e-4–1e-2；余弦 + warmup。BYU 第 3 名一组配置：lr 5e-4，32000 步中 warmup 3000 步，batch 2 × 梯度累积 2。
- batch 取显存允许的最大值，不当调参项（tuning playbook 的建议）；3D 常是 1–4 加梯度累积。
- 换架构后先重调：学习率 → warmup 与总步数 → 热图 σ 与正负 patch 采样比 → 解码阈值与 NMS 半径（每个模型都在 select 段重选）。

## 10. 已验证的经验

- **CZII CryoET Object Identification 第 1 名**（BloodAxe 与 Christof Henkel，[代码与 WRITEUP](https://github.com/BloodAxe/Kaggle-2024-CryoET)，[比赛页](https://www.kaggle.com/competitions/czii-cryo-et-object-identification)）：高斯热图 + CenterNet focal loss 的分割基线公榜约 0.740，自写点检测头单折公榜 0.752；验证用与推理相同的滑窗；每轮按类在验证集上选阈值；验证集加入翻转与 90° 旋转后 F-beta 曲线更平滑、阈值噪声更小；最终阈值来自 OOF 曲线。
- **CZII 第 4 名**（[arXiv 2502.13484](https://arxiv.org/abs/2502.13484)）：热图关键点检测，两种带深度压缩的 2.5D U-Net 集成，结构简单统一。
- **BYU 鞭毛马达定位第 3 名**（[代码](https://github.com/dangnh0611/kaggle_byu)）：全部重采样到 16 Å；步长 16、σ=200 Å 的高斯热图；简单 BCE 最好；重增强允许训练更久；伪标签经人工复核；多模型与 TTA 结果用 WBF 融合。
- **Spotiflow**（[代码](https://github.com/weigertlab/spotiflow)，[Nature Methods 2025](https://doi.org/10.1038/s41592-025-02662-x)）：阈值无关、亚像素的 2D/3D 斑点检测，可作强基线或预训练起点。
- **一个原子定位项目**：D4 TTA 伪影与软高斯 BCE 下限两条见第 6、7 节；模块"无效"先排查实验本身的完整经过见[小数据点检测案例](../../case-studies/small-data-point-detection-module-triage.md)；训练集上选解码器导致 56 个候选并列满分，见[选择卫生](../../selection-hygiene.md)案例。

## 11. 推荐库与工具

| 库 | 用途 | 许可（GitHub 元数据，2026-10-22 核） |
|---|---|---|
| [timm](https://github.com/huggingface/pytorch-image-models) | 2D 预训练编码器；`features_only=True` 读通道与步长 | Apache-2.0（权重许可逐模型看） |
| [segmentation_models.pytorch](https://github.com/qubvel-org/segmentation_models.pytorch) | U-Net/FPN 等解码器接 timm 编码器 | MIT |
| [MONAI](https://github.com/Project-MONAI/MONAI) | 3D 网络、滑窗推理、医学/体数据变换 | Apache-2.0 |
| [Spotiflow](https://github.com/weigertlab/spotiflow) | 斑点检测强基线与预训练模型 | BSD-3-Clause |
| [Lightning](https://github.com/Lightning-AI/pytorch-lightning) | 自写循环时的训练框架 | Apache-2.0 |
| [kornia](https://github.com/kornia/kornia) | GPU 上的几何增强，可同步变换关键点与掩膜 | Apache-2.0 |
| [torchinfo](https://github.com/TylerYep/torchinfo) | 逐层 shape 与参数量，核对步长与容量 | MIT |
| [cleanlab](https://github.com/cleanlab/cleanlab) | 疑似错标检测，含[分割](https://docs.cleanlab.ai/stable/cleanlab/segmentation/index.html)与[目标检测](https://docs.cleanlab.ai/stable/cleanlab/object_detection/index.html)模块 | Apache-2.0 |
| [FiftyOne](https://github.com/voxel51/fiftyone) | 浏览叠图、按误差排序找坏样本 | Apache-2.0 |
| [Captum](https://github.com/meta-pytorch/captum) | 归因分析（只作解释辅助，不代表因果贡献） | BSD-3-Clause |

注意：原 Albumentations 仓库已归档（MIT），后继 AlbumentationsX 为 AGPL-3.0，引入前确认许可。
