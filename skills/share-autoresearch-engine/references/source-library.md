# 来源库：范式、官方文档与使用方法

本文件不是“书单”，是**排障与选型的入口**。访问日期：2026-10-25；原有链接抽查过，新增入口按季度复核。外部站点会改版/重定向；引用前以当前官方页面为准，不把历史入口当现役真源。原则：

1. 先官方文档，再源码，再维护良好的示例；博客只用于建立直觉。
2. 只读与当前决策有关的一节，不从头读到尾。
3. 每读一条，落成一个判断、一个 adapter、一个检查或一个门；否则不算学到。
4. 记录 URL、访问日期、用在哪；来源会变，引用前复核。
5. 不复制整篇文档；短引用可以，长文放链接。

## 快速入口

| 你现在要解决什么 | 先读 |
|---|---|
| 过拟合/欠拟合、loss、超参、归一化、初始化、融合、模块接入 | [训练判断核心](training-core.md) |
| 从论文找 idea，下载代码，拆模块，移植并对照 | [从论文到模块](idea-to-module.md) |
| 从 Kaggle/HF 比赛方案找 trick，判断公榜过拟合/泄漏 | [Idea 采购](idea-sourcing.md) |
| 让另一个 AI 做审查、红队、冻结前复核 | [AI 检查点](ai-checkpoints.md) |
| 把反复出现的问题固化成检查/回归 | [从问题到流水线](incident-to-pipeline.md) |
| 论文、会议、代码、官方文档、技术博客的入口 | 本页第 1.5、9.6、11 节 |
| 结果反直觉、怀疑实验本身 | [排错](triage/README.md) |
| 改结构后重调、预算与搜索 | [调参](tuning/README.md)、[实验协议](experiment-protocol.md) |
| 模块接不进去、梯度/初始化/位置问题 | [组件工作流](component-integration.md)、[结构判断门禁](architecture-judgment-gate.md) |

## 0. 掌握状态（别把“有链接”当成“已验证”）

| 领域 | 状态 | 证据/边界 |
|---|---|---|
| Lightning 基座 | ✅ 最小实测 | 参考模板 CPU smoke 通过（points/series/multitask）；GPU/DDP/真实任务 parity 未在本 skill 验收 |
| HF Trainer/HF 生态 | 📖 已读关键文档 | 边界已写清；参考模板未跑过 HF Trainer |
| MMEngine/MMDetection/MMSegmentation | 🔗 仅路由 | 参考模板未安装/跑通 |
| MONAI/nnU-Net | 🔗 仅路由 | 参考模板未跑过医学 3D |
| PyTorch Forecasting/NeuralForecast | 🔗 仅路由 | 参考模板未跑过时序预测 |
| TRL/Accelerate/PEFT | 🔗 仅路由 | 参考模板未跑过 LLM/VLM |
| 方法论（Karpathy/Google/ML Test Score 等） | 📖 已吸收为检查 | 只吸收可执行条目，不等于读完原文 |

状态含义：✅ 有可复现实验；📖 读过关键节并能落到边界；🔗 知道入口和适配点，但没有实操证据。不要拿 🔗 当 ✅ 宣称。

## 1. 通用/多任务基座

| 主题 | 官方入口 | 解决什么 | 何时读 |
|---|---|---|---|
| Lightning 总览 | https://lightning.ai/docs/pytorch/stable/ | Module/DataModule/Trainer/callbacks/checkpoint | 搭基座、迁移旧循环 |
| Lightning Trainer | https://lightning.ai/docs/pytorch/stable/common/trainer.html | max_steps、val_check_interval、devices、precision | 配训练预算/多卡 |
| Lightning checkpoint | https://lightning.ai/docs/pytorch/stable/common/checkpointing.html | 保存/恢复、`save_top_k`、`monitor` | 选点、断点续跑 |
| Lightning early stopping | https://lightning.ai/docs/pytorch/stable/common/early_stopping.html | patience、min_delta、何时停 | 设计预算守卫 |
| Hydra | https://hydra.cc/docs/intro/ | 配置组合、multirun、sweep | 多实验/多数据集 |
| Optuna | https://optuna.readthedocs.io/en/stable/ | 搜索空间、pruner、study | HPO |
| torchmetrics | https://lightning.ai/docs/torchmetrics/stable/ | 分布式 metric、累积 | 替换“逐 batch 平均”的近似 metric |
| PyTorch AMP | https://pytorch.org/docs/stable/amp.html | autocast/GradScaler | 混合精度排障 |
| PyTorch DDP | https://pytorch.org/docs/stable/distributed.html | 进程组、sampler、同步 | 多卡排障 |
| 多任务（论文） | https://arxiv.org/abs/1706.05098 | 共享表示、任务关系、负迁移 | 设计多任务结构；不是官方文档 |

**边界**：Lightning 管训练工程，不管数据泄漏、指标定义、阈值、test guard；Hydra 管配置，不管科学选择；Optuna 管搜索，不管验证集是否被用旧。

## 1.5 论文、会议与代码发现

这不是“多读论文”，是**按任务和失败模式找可迁移机制**。详细流程见 [从论文到模块](idea-to-module.md)。

### 顶会/期刊入口

| 方向 | 入口 | 用法 |
|---|---|---|
| CVPR/ICCV/WACV | https://openaccess.thecvf.com/ | 按年份/关键词找论文与补充材料 |
| NeurIPS | https://papers.nips.cc/ | 按年份找论文/代码 |
| ICML/AISTATS 等 | https://proceedings.mlr.press/ | PMLR 论文集 |
| ICLR/NeurIPS 投稿 | https://openreview.net/ | 看评审、rebuttal、版本 |
| AAAI | https://ojs.aaai.org/index.php/AAAI | AAAI 论文 |
| ACM MM | https://dl.acm.org/ | 多媒体/视频论文 |
| 视觉期刊 | https://www.computer.org/csdl/journal/tp （TPAMI）; https://link.springer.com/journal/11263 （IJCV） | 期刊论文 |
| 医学 3D | https://www.miccai.org/ ; https://www.sciencedirect.com/journal/medical-image-analysis | MICCAI/MIA |

### 搜索与代码入口

| 入口 | 解决什么 | 注意 |
|---|---|---|
| https://paperswithcode.com/ | 历史论文—代码入口；当前可能重定向到 HF | 不再当当前榜单真源；引用前核最终页面 |
| https://huggingface.co/papers | 近期论文/trending | 不是正式同行评审；只作线索 |
| https://arxiv.org/ | 预印本 | 版本可能变；中稿后以正式版为准 |
| https://www.semanticscholar.org/ | 引用网络、相关工作 | 引用数不是质量 |
| https://scholar.google.com/ | 找引用/后续工作 | 噪音大，需筛 |
| https://github.com/ | 官方/复现代码 | 先官方，再看高星复现 |

**筛选优先级**：任务/评价器匹配 > 有官方代码 > 有消融和位置对照 > 同预算可复现 > 榜单分数。没有代码的论文不是不能读，但移植风险高。

### Kaggle / Hugging Face / 比赛代码

| 入口 | 找什么 | 注意 |
|---|---|---|
| https://www.kaggle.com/competitions | 同任务历史比赛、metric、规则 | 规则/外部数据限制 |
| 比赛页 Code / Discussion | 高分 notebook、solution writeup、失败复盘 | 公榜过拟合、泄漏、算力不对等 |
| https://www.kaggle.com/code | 通用 notebook/教程 | 质量参差，先复现 |
| https://www.kaggle.com/discussions | 比赛/数据讨论 | 非正式来源 |
| https://huggingface.co/papers | 近期论文/代码 | 不是正式评审 |
| https://huggingface.co/models | 预训练权重、模型卡 | 看数据/license/评测口径 |
| https://huggingface.co/datasets | 数据卡、划分 | 数据卡不等于无泄漏 |
| https://huggingface.co/spaces | demo/推理代码 | demo 不等于可训练 |
| https://huggingface.co/learn | 课程/教程 | 入门用，不当研究证据 |
| https://huggingface.co/blog | 工程/训练技巧 | 版本相关 |
| https://github.com/trending | 新仓库/工具 | 热度不等于质量 |

**比赛方案不是论文，公榜不是我们的验证集。** 读法、trick 分类和采纳记分卡见 [Idea 采购](idea-sourcing.md)。

### 读论文的最小记录

`任务 → 失败模式 → 机制假设 → 张量契约 → 原生位置 → 训练条件 → 对照/消融 → 边界 → 是否移植`

不要只记“某某模块涨点”；要记它在什么条件下涨、和谁比、代码是否一致。

## 2. 视觉：分类、检测、分割

| 任务 | 官方入口 | 解决什么 | 何时读 |
|---|---|---|---|
| 视觉模型/训练 recipe | https://huggingface.co/docs/timm/index | backbone、预训练、分类训练脚本 | 图像分类 baseline |
| MMEngine | https://mmengine.readthedocs.io/ | Runner/Config/Registry/Hook | 检测/分割工程底座 |
| MMDetection | https://mmdetection.readthedocs.io/ | 检测模型、数据管道、评测 | 目标检测 |
| MMSegmentation | https://mmsegmentation.readthedocs.io/ | 语义分割模型、数据管道、评测 | 语义分割 |
| Detectron2 | https://detectron2.readthedocs.io/ | 检测/分割/关键点 | 需要 Detectron2 生态 |
| Ultralytics | https://docs.ultralytics.com/ | YOLO 训练/推理/部署 | 实时检测 baseline |
| torchvision references | https://github.com/pytorch/vision/tree/main/references | 分类/检测/分割参考训练脚本 | 想看官方 recipe |

**边界**：这些栈的成熟 recipe 往往绑定数据格式和评测器；换任务不是改一个 config 就完事。点检测/实例分割要先确认评价器是否支持匹配/阈值。

## 3. 3D：体数据、医学、点云

| 任务 | 官方入口 | 解决什么 | 何时读 |
|---|---|---|---|
| MONAI | https://monai.io/ | 医学 3D transform、网络、loss、评估 | 医学体数据 |
| MONAI tutorials | https://github.com/Project-MONAI/tutorials | 分割/分类/检测端到端示例 | 找 3D recipe |
| nnU-Net | https://github.com/MIC-DKFZ/nnUNet | 医学分割强 baseline、预处理/训练策略 | 医学分割 baseline |
| PyG | https://pytorch-geometric.readthedocs.io/ | 图/点云消息传递 | 点云/图任务 |
| Open3D-ML | https://github.com/isl-org/Open3D-ML | 3D 感知、点云模型 | 点云检测/分割 |
| PointNeXt | https://github.com/guochengqian/PointNeXt | 点云分类/分割强 baseline | 点云 baseline |

**边界**：3D 的 spacing、orientation、各向异性、按病人/体积切分是数据合同的一部分；不能把 2D 的随机切分直接搬来。“简单 3D”可以 Lightning + 自定义 DataModule；医学 3D 优先 MONAI/nnU-Net。

## 4. 时序

| 任务 | 官方入口 | 解决什么 | 何时读 |
|---|---|---|---|
| PyTorch Forecasting | https://pytorch-forecasting.readthedocs.io/ | TimeSeriesDataSet、滚动验证、预测模型 | 多变量预测 |
| NeuralForecast | https://nixtlaverse.nixtla.io/neuralforecast/ | 现代预测模型、交叉验证 | 快速强 baseline |
| TSLib | https://github.com/thuml/Time-Series-Library | 长时序预测/分类/异常检测 | 论文复现 |
| sktime | https://www.sktime.net/ | 时序 API、分类/回归/预测 | 传统+深度统一接口 |

**边界**：时序不能随机切分；要按时间/实体切，留 gap，做滚动验证。分类/回归任务用 Lightning 基座可以，但预测任务优先专用栈。

## 5. LLM/VLM/Transformer

| 主题 | 官方入口 | 解决什么 | 何时读 |
|---|---|---|---|
| HF Hub 模型 | https://huggingface.co/models | 权重、模型卡、版本 | 找预训练/发布 |
| HF Hub 数据集 | https://huggingface.co/datasets | 数据卡、划分、许可 | 找数据/对照 |
| HF Evaluate | https://huggingface.co/docs/evaluate/index | 指标实现与比较 | 选指标 |
| HF Safetensors | https://huggingface.co/docs/safetensors/index | 权重格式/加载 | 发布/部署 |
| HF Trainer | https://huggingface.co/docs/transformers/main_classes/trainer | 训练循环、分布式、AMP、checkpoint、HPO 接口 | 微调 HF 模型 |
| TRL | https://huggingface.co/docs/trl/index | SFT/DPO/PPO 等对齐 | LLM 对齐 |
| Accelerate | https://huggingface.co/docs/accelerate/index | 多卡/混合精度/FSDP/DeepSpeed 启动 | 自定义循环/大模型 |
| PEFT | https://huggingface.co/docs/peft/index | LoRA/Adapter 等参数高效微调 | 低显存微调 |
| DeepSpeed | https://www.deepspeed.ai/ | ZeRO、Offload、分布式 | 大模型训练 |
| PyTorch FSDP | https://pytorch.org/docs/stable/fsdp.html | 参数分片 | 多卡大模型 |
| LLaVA | https://github.com/haotian-liu/LLaVA | VLM 指令微调/多模态对话 | VLM 原型 |
| OpenCLIP | https://github.com/mlfoundations/open_clip | 图文对比学习、零样本分类 | 视觉-语言 baseline |

**关键纠正**：`Trainer` 不是只能用于 Transformer。API 上可以接收任意 `nn.Module`；但它针对 Transformers 优化，官方文档明确提示用于其他模型可能有意外行为。对任意 3D/时序模型，要自定义 `compute_loss`、`compute_metrics`、collator；对点检测/分割，默认 `prediction_step` 不够。

## 6. 表格

| 主题 | 官方入口 | 解决什么 | 何时读 |
|---|---|---|---|
| PyTorch Tabular | https://pytorch-tabular.readthedocs.io/ | 表格深度模型、DataModule | 深度表格 |
| LightGBM | https://lightgbm.readthedocs.io/ | 强树模型 baseline | 表格首选 baseline |
| XGBoost | https://xgboost.readthedocs.io/ | 强树模型 baseline | 表格首选 baseline |
| CatBoost | https://catboost.ai/docs/ | 类别特征、强 baseline | 表格类别特征多 |

**边界**：表格任务先跑树模型，不要默认上深度模型；深度模型只在有明确交互/表示需求时用。

## 7. GAN/RL/自监督/图

| 主题 | 官方入口 | 解决什么 | 何时读 |
|---|---|---|---|
| Stable-Baselines3 | https://stable-baselines3.readthedocs.io/ | RL 算法/训练/评估 | RL baseline |
| CleanRL | https://docs.cleanrl.dev/ | 单文件 RL 实现 | 学 RL 细节 |
| PyTorch-GAN | https://github.com/eriklindernoren/PyTorch-GAN | 各类 GAN 最小实现 | GAN 原型/对照 |
| StyleGAN3 | https://github.com/NVlabs/stylegan3 | 高分辨率图像生成、等变网络 | 生成模型 baseline |
| Lightly | https://docs.lightly.ai/ | 自监督预训练 | 无标签预训练 |
| Solo-learn | https://github.com/vturrisi/solo-learn | 自监督方法集合 | 自监督对比 |
| PyG | https://pytorch-geometric.readthedocs.io/ | 图神经网络 | 图任务 |
| DGL | https://www.dgl.ai/ | 图神经网络 | 图任务 |

**边界**：这些任务的训练循环、loss、评估与监督学习差异大，不套基座；用专用库或原论文实现。

## 8. 服务/部署/HPO

| 主题 | 官方入口 | 解决什么 | 何时读 |
|---|---|---|---|
| BentoML | https://docs.bentoml.com/ | 模型打包/服务 | 部署 |
| Triton | https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/index.html | 高性能推理 | 生产推理 |
| Ray Tune | https://docs.ray.io/en/latest/tune/index.html | 分布式 HPO | 大规模搜索 |
| Optuna | https://optuna.readthedocs.io/en/stable/ | 单机 HPO | 默认 HPO |
| MLflow | https://mlflow.org/docs/latest/ | 实验跟踪/模型注册 | 实验管理 |
| W&B | https://github.com/wandb/wandb | 实验跟踪/可视化 | 实验管理 |

## 9. 方法论与检查表

| 来源 | 入口 | 解决什么 | 边界 |
|---|---|---|---|
| Karpathy recipe | https://karpathy.github.io/2019/04/25/recipe/ | 先看数据、记忆探针、baseline、逐步加复杂度 | 直觉性清单，不是统计规范 |
| Google Rules of ML | https://developers.google.com/machine-learning/guides/rules-of-ml | 简单模型先行、训练-服务偏差、新鲜数据评估 | 偏产品/工程 |
| Hidden Technical Debt | https://papers.nips.cc/paper/5656-hidden-technical-debt-in-machine-learning-systems | glue code、配置、数据依赖、反馈环 | 不给代码 |
| ML Test Score | https://research.google/pubs/pub46555/ | 数据/模型/基础设施测试 | 偏生产 |
| scikit-learn model selection | https://scikit-learn.org/stable/model_selection.html | fit/select/evaluate、交叉验证 | 不覆盖大模型预算 |
| No Free Lunch（二手） | https://en.wikipedia.org/wiki/No_free_lunch_in_search_and_optimization | 没有通用最优算法 | 不告诉你选哪个；原站证书失效，引用时注明二手 |
| NeurIPS checklist | https://www.cs.mcgill.ca/~jpineau/ReproducibilityChecklist.pdf | 代码/数据/seed/误差棒 | 不保证设计正确 |
| HF Papers（原 PwC 已重定向） | https://huggingface.co/papers | 找论文/代码入口 | 已非原 PwC 榜单；排名/口径要另核 |

## 9.5 项目合同与状态（按所在项目读）

全局技能只提供通用入口，不内置某个项目的训练合同、数据路径或排行。进入具体项目后：

| 入口 | 位置 | 用途 |
|---|---|---|
| 项目深度学习合同 | 项目 `AGENTS.md` 的指针，或 `scripts/dl_project_contract.py check` 指定路径 | 训练/比较/判据，项目专属约束 |
| 项目 benchmark 状态 | 项目自己的状态/结果页 | 当前排名、差距、证据 |
| 任务计划 | 项目自己的 task plan | 当前 phase 与待办 |

外部来源不能覆盖项目合同；冲突时以合同和数据边界为准。全局模板不提供项目成绩，也不替代项目合同。

## 9.6 训练经验、归一化、初始化、融合参考

这些是“怎么把模型训好”的原始来源，不只是工程文档。先读 [训练判断核心](training-core.md)，需要原始依据时再查下面。

### 训练配方与诊断

| 来源 | 入口 | 用途 |
|---|---|---|
| Karpathy, A Recipe for Training Neural Networks | https://karpathy.github.io/2019/04/25/recipe/ | 先看数据、记忆探针、baseline、逐步加复杂度 |
| Google, Deep Learning Tuning Playbook | https://github.com/google-research/tuning_playbook | lr/批量/正则/预算/消融的系统顺序 |
| Google, Rules of Machine Learning | https://developers.google.com/machine-learning/guides/rules-of-ml | 简单 baseline、训练-服务偏差 |
| fast.ai Practical Deep Learning | https://course.fast.ai/ | 先跑起来、强 baseline、顶层优先 |
| PyTorch Tutorials | https://pytorch.org/tutorials/ | 官方训练/部署示例；先看对应版本 |
| Sebastian Raschka, Practical Tips | https://sebastianraschka.com/blog/ | 混合精度/工程细节（按版本核对） |

### 优化、损失与训练机制

| 主题 | 原始来源/入口 | 用途/边界 |
|---|---|---|
| AdamW | https://arxiv.org/abs/1711.05101 | 区分 Adam 的 L2 与 decoupled weight decay；参数组/权重衰减按任务验证 |
| AMP 梯度累积 | https://pytorch.org/docs/stable/notes/amp_examples.html | 累积完成后 unscale→clip→step 的顺序；按安装版本核对 |
| BatchNorm2d | https://pytorch.org/docs/stable/generated/torch.nn.BatchNorm2d.html | 统计轴 N,H,W、`track_running_stats`、train/eval；不是小 batch 一刀切 |
| CrossEntropyLoss | https://pytorch.org/docs/stable/generated/torch.nn.CrossEntropyLoss.html | logits、软标签、ignore_index、reduction；软标签概率条件不自动校验 |
| SWA / update_bn | https://pytorch.org/docs/stable/optim.html#stochastic-weight-averaging | 平均权重、采样、BN 重估；旧 torchcontrib API 不直接复制 |
| ResNet strikes back | https://arxiv.org/abs/2110.00476 | 训练配方能解释部分“结构增益”；分类证据不外推 |
| CutMix / mixup | https://arxiv.org/abs/1905.04899 ; https://arxiv.org/abs/1710.09412 | 标签混合规则；检测/分割/物理数据不能照搬 |
| Simple Copy-Paste | https://arxiv.org/abs/2012.07177 | 实例粘贴、遮挡后 mask/box 重建；依赖可靠实例标注 |
| FixMatch | https://arxiv.org/abs/2001.07685 | 弱增强伪标签 + 强增强一致性；只用允许的无标签池，阈值不是正确性 |
| Weighted Boxes Fusion | https://github.com/ZFTurbo/Weighted-Boxes-Fusion | 框坐标/类别/分数/IoU 融合；密集相邻目标可能误合并 |
| ByteTrack | https://github.com/FoundationVision/ByteTrack | 高低分检测两阶段关联；低分召回与误连有权衡，按视频重置 |
| TrackEval | https://github.com/JonathonLuiten/TrackEval | HOTA/DetA/AssA/IDF1/MOTA；固定 ignore/class/sequence 聚合 |
| Calibration | https://arxiv.org/abs/1706.04599 | 温度缩放/NLL/Brier/可靠性图；不修复域偏移，ECE 依赖分箱 |
| PyTorch reproducibility | https://pytorch.org/docs/stable/notes/randomness.html | worker/seed/确定性边界；固定 seed 不等于跨平台位级一致 |

### 归一化与初始化

| 主题 | 原始来源/入口 | 用途 |
|---|---|---|
| BatchNorm | https://arxiv.org/abs/1502.03167 | batch 统计、CNN 归一化 |
| LayerNorm | https://arxiv.org/abs/1607.06450 | 序列/Transformer/小 batch |
| GroupNorm | https://arxiv.org/abs/1803.08494 | 小 batch 检测/分割 |
| InstanceNorm | https://arxiv.org/abs/1607.08022 | 风格/生成 |
| RMSNorm | https://arxiv.org/abs/1910.07467 | LLM/Transformer 效率 |
| Xavier/Glorot | https://proceedings.mlr.press/v9/glorot10a.html | tanh/线性初始化 |
| He/Kaiming | https://arxiv.org/abs/1502.01852 | ReLU 卷积/线性 |
| Fixup / 零初始化残差 | https://arxiv.org/abs/1901.09321 | 深网络/残差训练稳定性 |
| PyTorch init API | https://pytorch.org/docs/stable/nn.init.html | 具体实现与默认值 |

### 结构、模块与融合

| 主题 | 入口 | 用途 |
|---|---|---|
| ResNet | https://arxiv.org/abs/1512.03385 | 残差/深层 CNN |
| FPN | https://arxiv.org/abs/1612.03144 | 多尺度特征融合 |
| U-Net | https://arxiv.org/abs/1505.04597 | skip 连接/分割 |
| SENet | https://arxiv.org/abs/1709.01507 | 通道注意力/重标定 |
| CBAM | https://arxiv.org/abs/1807.06521 | 通道+空间注意力 |
| Non-local | https://arxiv.org/abs/1711.07971 | 长程依赖 |
| ViT | https://arxiv.org/abs/2010.11929 | patch/Transformer |
| Swin | https://arxiv.org/abs/2103.14030 | 窗口注意力/多尺度 |
| ConvNeXt | https://arxiv.org/abs/2201.03545 | 现代 CNN 训练配方 |
| DETR | https://arxiv.org/abs/2005.12872 | 检测 Transformer |
| Deformable DETR | https://arxiv.org/abs/2010.04159 | 可变形注意力/收敛 |
| DeepLabv3+ | https://arxiv.org/abs/1802.02611 | 分割 decoder/空洞卷积 |
| timm docs | https://huggingface.co/docs/timm | backbone/预训练/训练脚本 |
| MMEngine docs | https://mmengine.readthedocs.io/ | 视觉训练工程 |
| MONAI docs | https://monai.io/ | 医学 3D transform/loss |
| nnU-Net | https://github.com/MIC-DKFZ/nnUNet | 医学分割强 baseline/配方 |

### 融合与集成

| 主题 | 入口 | 用途 |
|---|---|---|
| Deep Ensembles | https://arxiv.org/abs/1612.01474 | 多模型不确定性/集成 |
| Snapshot Ensembles | https://arxiv.org/abs/1704.00109 | 单次训练多 snapshot |
| MC Dropout | https://arxiv.org/abs/1506.02142 | 近似贝叶斯/不确定性 |
| Model Soups | https://arxiv.org/abs/2203.05482 | 权重平均/微调模型合并 |
| 多模态融合 | [融合设计](multimodal-fusion-design.md)、[融合诊断](multimodal-fusion-diagnostics.md) | 融合位置/对齐/诊断 |

**边界**：论文/博客给的是机制和直觉，不保证在我们任务上涨点；最终仍按 [训练核心](training-core.md) 的对照和 [实验协议](experiment-protocol.md) 做同预算比较。

## 10. 阅读协议（怎么“统一学一遍”）

不要试图一次读完。按决策读：

1. **S0 选型**：读候选栈的 quickstart + “limitations/caveats” + 1 个官方 example；写 stack card。
2. **S1 指标**：读评价器文档；确认匹配、阈值、聚合、部署单元。
3. **S2 数据**：读数据格式/transform 文档；写数据合同和叠图检查。
4. **S5 排错**：读 troubleshooting/FAQ/issue；先查官方，再查 issue。
5. **S7 调参**：读 HPO 文档；写搜索空间和 trial 上限。
6. **S9 溯源**：读 reproducibility checklist；写 manifest。
7. **出事故**：先查本文件对应栈的官方文档/源码；再查 issue；最后才看博客。
8. **每读一条**：写“它改变了哪个判断/检查/门”；写不出就不算学到。

### 来源记录格式

```yaml
source:
  title:
  url:
  accessed:
  used_for:
  key_caveat:
```

## 11. 源码与包文档怎么查

官方文档不够时，按这个顺序：

1. **API 文档**：看参数、返回、shape、默认值。
2. **源码**：在固定 tag/commit 上读实现，不读 `main`；用 `inspect.getsource` / `help()` 核对签名。
3. **示例**：官方 examples/tests 比博客可靠；测试里常有边界条件。
4. **issue/changelog**：搜报错原文；确认是版本 bug 还是用法错误。
5. **包元数据**：`pip show`、`importlib.metadata.version`、license、依赖。
6. **记录**：把 repo + commit + 文件路径写进 stack card 或 manifest。

常用命令：

```bash
python -c "import inspect, lightning; print(lightning.__version__); print(inspect.signature(lightning.Trainer))"
python -c "import importlib.metadata as m; print(m.version('lightning'))"
```

不要用“最新 main 的源码”解释“固定版本的行为”；版本错位是最常见的假归因。

## 12. 出问题先查哪里

| 症状 | 先查 | 再查 |
|---|---|---|
| API 报错/参数不存在 | 当前版本文档 + `inspect.signature` | 固定 tag 源码、changelog |
| 训练 loss 不降 | 官方 recipe、数据 pipeline、优化器文档 | issue、最小复现 |
| 多卡变差/卡住 | DDP/Accelerate/Lightning 多卡文档 | NCCL 日志、issue |
| checkpoint 恢复不一致 | checkpoint 文档、RNG/EMA 源码 | parity 最小例 |
| 指标异常/全零/全一 | 评价器源码、匹配/阈值实现 | 阳性对照、混淆矩阵 |
| 3D/时序分数虚高 | 数据切分文档、泄漏检查 | 专用栈教程 |
| 显存/吞吐不够 | AMP/FSDP/DeepSpeed 文档 | profiler |
| 模型发布/加载失败 | HF Hub 模型卡、safetensors 文档 | issue、版本 |

原则：**先证明是用法问题还是库 bug，再改代码。** 没有最小复现，不要归因于框架。

## 13. 维护

- 新栈进入矩阵前，先补本文件的一行：入口、解决什么、边界。
- 官方链接失效时，优先找同版本 docs 或 pinned commit 的 README；不要用二手博客替代。
- 每季度抽查一次高风险链接（模板、Lightning、HF Trainer、MMEngine、MONAI）。
- 本文件只放“去哪里查”，不复制整篇文档；项目事实放项目合同。
