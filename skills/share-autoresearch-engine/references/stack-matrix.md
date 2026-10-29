# 候选栈矩阵与选型协议

Star 数只作生态可见度参考，不作质量或适配度证据；数据截至 2026-10-24 的 GitHub API。选型以任务、接口、维护、迁移成本为准。

## 1. 总表

| 栈 | 主领域 | 优势 | 边界 | 在本 skill 中的角色 |
|---|---|---|---|---|
| [PyTorch Lightning](https://github.com/Lightning-AI/pytorch-lightning) + Hydra | 通用/多任务监督学习 | `LightningModule`/`DataModule` 接口清楚；DDP、AMP、checkpoint、callbacks、日志成熟；图像/时序/3D 均可 | 抽象泄漏；自定义循环/多 optimizer 别扭；不提供科学选择与 HPO | **基座候选** |
| [HF Transformers Trainer](https://github.com/huggingface/transformers) | Transformer/VLM/LLM、HF 模型 | 生态最大；分布式/AMP/checkpoint/日志/HPO 集成；文档与社区强 | Transformer-first；任意模型要改 `compute_loss`/`compute_metrics`/collator；点检测不自然 | LLM/VLM/HF 模型专用，不作基座 |
| [MMEngine](https://github.com/open-mmlab/mmengine) | OpenMMLab 视觉检测/分割 | Registry + Config + Hook；成熟 recipe；分布式；与 MMDetection/MMSegmentation 配套 | 偏图像；体系重；时序/自定义点检测适配成本高 | 检测/分割专用栈 |
| [Accelerate](https://github.com/huggingface/accelerate) / [Fabric](https://lightning.ai/docs/fabric/stable/) | 原生 PyTorch 多卡/AMP | 侵入小；灵活；HF/Lightning 生态 | 不提供 Trainer、callbacks、config、HPO；要自己重建 | 自定义循环/特殊任务 |
| [Ignite](https://github.com/pytorch/ignite) | 轻量训练引擎 | Engine/Event 模型清楚；可控；分布式支持 | 生态较小；配置/实验管理层要自建 | 研究型自定义循环 |
| [MONAI](https://github.com/Project-MONAI/MONAI) | 医学 3D 影像 | 医学变换、网络、loss、评估；可与 Lightning 组合 | 医学领域专用；通用任务不需要 | 医学 3D 专用 |
| [PyTorch Forecasting](https://github.com/sktime/pytorch-forecasting) / [NeuralForecast](https://github.com/Nixtla/neuralforecast) | 时序预测 | TimeSeriesDataSet、滚动验证、领域模型 | 以预测任务为主；自定义多任务要适配 | 大规模时序专用 |
| [timm](https://github.com/huggingface/pytorch-image-models) | 视觉模型库/训练脚本 | 强模型 zoo、成熟训练 recipe、蒸馏/EMA | 分类为主；不是通用多任务 pipeline | 视觉 baseline/backbone |
| [MMDetection](https://github.com/open-mmlab/mmdetection) / [Detectron2](https://github.com/facebookresearch/detectron2) / [Ultralytics](https://github.com/ultralytics/ultralytics) | 目标检测/分割 | 成熟模型、数据管道、评测、部署 | 任务专用；换任务成本高 | 检测/分割专用 |
| [TRL](https://github.com/huggingface/trl) | LLM 对齐/微调 | SFT/DPO/PPO 等成熟流程；HF 生态 | LLM 专用 | LLM 专用 |
| [Keras 3](https://github.com/keras-team/keras) | 多后端高层训练 | `fit`/callbacks/HPO 简单；JAX/TF/PyTorch 后端 | 与现有 PyTorch 代码/生态不一致 | 非 PyTorch 项目备选 |
| [Ray Train](https://github.com/ray-project/ray) | 分布式/HPO 编排 | 大规模调度、超参搜索、容错 | 是编排层，不是模型训练骨架 | 大规模 HPO/集群 |

## 2. 关键结论

### Lightning

- 适合：需要统一“换模型/换 head/换数据/单卡多卡”的通用监督学习。
- 不适合：需要精细控制训练循环、多个 optimizer、RL/GAN、跨节点大规模。
- 主要风险不在框架，在**模板**：`ashleve/lightning-hydra-template` 默认分支最近提交停在 2023-09，依赖需升级；必须固定 commit + smoke + parity。
- 它不是科学正确性的保证；`EarlyStopping`、`ModelCheckpoint` 只执行你给的规则。

### HF Trainer

准确说法：**不是只能用于 Transformer；它是 Transformer-first，不是 generic-first。**

- API 上可接收任意 `nn.Module`，支持分布式、AMP、checkpoint、日志、early stopping、HPO 接入。
- 官方文档明确提示：`Trainer` 针对 Transformers 模型优化，用于其他模型可能有意外行为；模型应返回 tuple/`ModelOutput`，有 `labels` 时能算 loss，多标签用 `label_names`。
- 官方有 ViT 图像分类、音频等示例；3D/时序也可用，但要自定义 dataset/collator/model/loss/metric。
- 对点检测的匹配、阈值解码、D4/集成，默认 `prediction_step`/`compute_metrics` 不够；适配量大于 Lightning。
- 权威性：Transformers 约 168k stars、34k forks，是 HF 生态的行业标准；`Trainer` 在 NLP/VLM/音频微调中权威性很高。但“权威”不等于“通用任务最佳”。

适用：

| 场景 | 选择 |
|---|---|
| LLM/VLM/Transformer 微调 | HF Trainer/TRL |
| ViT 图像分类 | HF Trainer 或 Lightning 都可 |
| 任意 3D/时序小模型 | 可以，但优先专用栈；否则自定义适配 |
| 点检测/分割/检测 | 不用 HF Trainer 作基座 |

### MMEngine

- 成熟度来自 OpenMMLab 的整套 recipe，不只是 `mmengine` 本身；单看它 1.5k stars 会误判。
- 适合检测/分割/姿态等视觉密集任务；Registry/Config/Hook 对多实验管理很强。
- 不适合把时序、表格、自定义点检测硬塞进去；配置体系和 Hook 会变成负担。

## 3. 选型协议（S0）

写一页 **stack card**，至少包含：

1. **任务范式**：分类/回归/密集预测/时序/多任务/检测/分割/LLM/3D。
2. **数据形态**：shape、dtype、轴含义、变长/稀疏、3D spacing/orientation。
3. **评价器**：原生指标、聚合、阈值/解码、是否需要匹配、是否需要集成。
4. **候选栈**：2 个，不得只写一个；写清主候选与备选。
5. **适配点**：DataModule/Dataset、loss、head、evaluator、checkpoint、分布式。
6. **维护证据**：最近 release/commit、issue 状态、license、依赖重量。
7. **bake-off 标准**：适配代码行数、首次跑通时间、checkpoint 恢复、DDP、HPO、报错可读性。
8. **放弃条件**：什么情况下换专用栈，而不是继续加适配。

### 选择准则（按顺序）

1. **任务匹配**：专用栈能覆盖 ≥80% 需求时，优先专用栈。
2. **接口匹配**：数据/评价器能否干净接入；需要改核心循环就说明不匹配。
3. **维护健康**：固定 commit、license 清楚、依赖可安装、有人处理 issue。
4. **迁移成本**：适配层行数、模型改动、评测改动。
5. **科学契合**：能否实现 fit/select/evaluate 三段、阈值只在 val、test guard。
6. **运行契合**：单卡/多卡、显存、依赖、团队熟悉度。

### Bake-off（候选接近时）

同一小任务，各跑 100–300 步，记录：

- 适配代码行数；
- 首次跑通时间；
- step0 输出与 loss 量级；
- checkpoint 保存/恢复；
- 单卡/双卡；
- HPO 接入；
- 报错可读性；
- 依赖数量/安装失败点。

结果写回 stack card；不以 star 数或“大家都用”作为唯一理由。

## 4. Hugging Face 生态的定位

用户判断成立：**现在模型发布、权重分发、数据集共享，Hugging Face 是事实中心。** 但要把四件事分开：

| 层 | 代表 | 作用 | 是否等于训练 Pipeline |
|---|---|---|---|
| Hub | https://huggingface.co/models | 权重/模型卡/数据集 | 否 |
| Transformers | https://huggingface.co/docs/transformers | 模型定义、`from_pretrained` | 否 |
| Trainer | https://huggingface.co/docs/transformers/main_classes/trainer | 训练循环（Transformer-first） | 是，但只适合其生态 |
| Accelerate/TRL/PEFT | https://huggingface.co/docs/accelerate / https://huggingface.co/docs/trl / https://huggingface.co/docs/peft | 分布式、对齐、参数高效微调 | 否，是组件 |

因此：

- **模型发布/复用**：优先 HF Hub，哪怕训练用 Lightning。
- **Transformer/VLM/LLM 微调**：优先 HF Trainer/TRL。
- **通用图像/时序/多任务**：可以复用 HF 模型和数据集，但训练骨架仍可用 Lightning；不要因为“模型在 HF”就强行用 Trainer。
- **点检测/分割/检测**：模型可以在 HF，训练/评测用专用栈；HF Trainer 不是这条线的主骨架。

一句话：**HF 是模型与权重的中心，不等于所有任务的训练中心。**

## 5. 上游固定与升级

- 记录 `repo + commit + license + install command + adapter path`。
- 不跟 `main/latest`；升级先跑 smoke + parity。
- 模板只 vendor 最小必要文件；不把整仓复制进项目。
- 上游停更不等于不能用，但必须自己承担安全/依赖/兼容维护；无法承担时换栈。
