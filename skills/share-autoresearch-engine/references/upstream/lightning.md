# 上游卡片：PyTorch Lightning（工具）

## 链接与许可证

- 仓库：<https://github.com/Lightning-AI/pytorch-lightning>（默认分支 `master`）
- 许可证：Apache-2.0。

## 吸收的版本

- 记录点：2026-10-22 查到的默认分支 HEAD `84df182f50ab34301aabb3c0eb4031815bfb413d`（提交于 2026-09-21）。行号对应此 commit。
- 核对过的已安装版本：lightning 2.6.6（2026-10-22；本技能脚本不导入 Lightning）。安装与升级用当前项目的解释器。
- 包名：新包是 `lightning`（`import lightning.pytorch as pl`），旧包是 `pytorch_lightning`。回调与 Trainer 须来自同一个包，不能混用两个包里的同名类。
- 封装 Lightning 的框架可能只透传部分 `Trainer` 参数（例如只透传 `callbacks` / `logger`）；`overfit_batches`、`detect_anomaly`、`gradient_clip_val` 这类参数要先查封装层是否透传，不透传时自建 `Trainer` 或用回调实现等价功能。

## 拿了什么

| 上游位置 | 用途 | 状态 |
|---|---|---|
| `src/lightning/pytorch/callbacks/spike.py:12` `SpikeDetection`（实现在 `src/lightning/fabric/utilities/spike.py:15`） | 损失尖峰检测，触发时抛 `TrainingSpikeException` 而不是悄悄继续 | 已写进文档（`references/tuning/README.md`"训练过程里的保护"，只列回调名）；`../mlgain-integrate-component/scripts/train_sanity_checks.py` 不导入或调用它 |
| `src/lightning/pytorch/callbacks/weight_averaging.py:366` `EMAWeightAveraging` | EMA 权重；评估时要分清 EMA 与原始权重 | 已写进文档（`references/tuning/README.md`，只列回调名） |
| `src/lightning/pytorch/callbacks/on_exception_checkpoint.py:31` `OnExceptionCheckpoint` | 异常/被杀时保存检查点，配合可续跑 | 备选，未接入（`scripts/hpo_study.py` 与 `references/tuning/README.md` 都未提及） |
| `src/lightning/pytorch/callbacks/lr_finder.py:32` `LearningRateFinder` | 学习率范围测试，作为扫学习率前的粗定位 | 已写进文档（`references/tuning/README.md`，只列回调名） |
| `src/lightning/pytorch/callbacks/model_summary.py:39` `ModelSummary` | 训练开始时打印可训练参数量 | 备选，未接入（`../mlgain-integrate-component/scripts/module_probe.py` 不导入它；同类功能见 `../mlgain-integrate-component/scripts/train_sanity_checks.py`:`frozen_audit`，用的是 torchinfo） |
| `src/lightning/pytorch/utilities/grads.py:22` `grad_norm` | 逐层梯度范数，用于确认新分支有梯度、定梯度裁剪阈值 | 备选，未接入（`../mlgain-integrate-component/scripts/train_sanity_checks.py` 不导入它；`../mlgain-integrate-component/scripts/probe_hooks.py` 有自写的逐模块梯度范数，与 Lightning 无关） |
| `src/lightning/pytorch/trainer/trainer.py:112` `overfit_batches`、`:128` `detect_anomaly` | 小样本过拟合、autograd 异常检测 | 备选，未接入（`../mlgain-integrate-component/scripts/train_sanity_checks.py`:`overfit_under_training_transforms` 是自写的过拟合循环，不经 Lightning Trainer；`detect_anomaly` 未用） |

工具清单另见 `references/workflow/paradigms/vision-dense.md`。

## 没拿什么及原因

- `StochasticWeightAveraging`、`BatchSizeFinder`、`ThroughputMonitor`：当前任务不需要。
- Fabric 整体迁移：训练入口通常由各模型库自带，不改写成 Fabric。

## 下次升级看哪些路径

- `src/lightning/pytorch/callbacks/spike.py`、`src/lightning/fabric/utilities/spike.py`
- `src/lightning/pytorch/callbacks/weight_averaging.py`（较新，接口可能还在变）
- `src/lightning/pytorch/callbacks/on_exception_checkpoint.py`、`lr_finder.py`、`model_summary.py`
- `src/lightning/pytorch/utilities/grads.py`
- 升级当前项目解释器里的 lightning 前，先确认封装它的框架声明的版本约束（本技能脚本不依赖 Lightning）。
