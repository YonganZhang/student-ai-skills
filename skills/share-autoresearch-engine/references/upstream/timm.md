# 上游卡片：timm（pytorch-image-models）

## 链接与许可证

- 仓库：<https://github.com/huggingface/pytorch-image-models>
- 许可证：Apache-2.0。

## 吸收的版本

- commit `af97f99efef62bd9bd7eaa908fffe5b7a2d98e2c`（2026-10-20），吸收日 2026-10-22。行号对应此 commit。

## 拿了什么

| 上游位置 | 内容 | 状态 |
|---|---|---|
| `sweep.py:189` `job_config_hash` | 用规范化配置的哈希做 run 身份，不靠目录名 | 已实现（`scripts/run_manifest.py`:`config_identity`，docstring 署名，代码自写） |
| `sweep.py:740` `plan_changes` | 续跑前比较新旧搜索计划，计划变了就报出差异，不静默续跑 | 已实现（`scripts/hpo_study.py`:`cmd_create`：设置与已存 study 不同就拒绝并报出旧设置；不逐项列差异） |
| `sweep.py:851-974` `Lock` / `JobState` | 文件锁 + 每个作业的状态文件，多进程不重复领同一作业 | 备选，未接入（`scripts/hpo_study.py` 不用文件锁，多 worker 分配交给 Optuna RDB 存储） |
| `sweep.py:1543` `aggregate_repeats` | 同配置多 seed 结果聚合（均值、方差、次数） | 已写进文档（`references/tuning/README.md`"训练过程里的保护"） |
| `timm/utils/checkpoint_saver.py:32`（`CheckpointSaver`；`:188` top-N、`:264` `save_recovery`、`:282` `find_recovery`） | 按指标保留前 N 个检查点 + 周期性恢复点 | 已写进文档（`references/tuning/README.md`"训练过程里的保护"） |
| `timm/models/_helpers.py:186-229` `load_checkpoint` | `strict` 加载并返回不匹配的键，不吞掉 | 已实现（`../mlgain-integrate-component/scripts/train_sanity_checks.py`:`strict_reload_roundtrip`，docstring 署名，代码自写） |
| `timm/optim/_param_groups.py:19-38` `param_groups_weight_decay` | 构建优化器时跳过 `requires_grad=False` 的参数：之后再解冻，这些参数永远不会被优化 | 已实现（`../mlgain-integrate-component/scripts/train_sanity_checks.py`:`optimizer_covers_trainable`，docstring 署名；`../mlgain-integrate-component/scripts/module_probe.py`:`optimizer_membership` 做同类检查） |
| `timm/utils/model.py:110-217` `freeze` / `unfreeze`；`timm/layers/norm_act.py:278` `freeze_batch_norm_2d` | 冻结时连 BN 统计量一起冻（转成 torchvision `FrozenBatchNorm2d`） | 备选，未接入（`../mlgain-integrate-component/references/paper-port-fidelity.md` 第 4 节只写"冻结层"要检查，没写 BN 统计量） |
| `timm/layers/layer_scale.py:5`、`timm/layers/drop.py:178` `DropPath`、`timm/utils/model_ema.py:178` `ModelEmaV3`、`timm/utils/agc.py:30` `adaptive_clip_grad` | 新分支小初值缩放、随机深度、EMA、自适应梯度裁剪 | 备选，未接入（`../mlgain-integrate-component/references/paper-port-fidelity.md` 与 `references/tuning/README.md` 都未提及这四项；后者的 EMA 指 Lightning 回调，梯度裁剪是按范数分位数，不是 AGC） |

2D 预训练编码器的用法另见 `references/workflow/paradigms/vision-dense.md`。

更正：`FrozenBatchNorm2d` 的转换函数在 `timm/layers/norm_act.py:278`，`utils/model.py` 的 `freeze` 调用它；`Lock`/`JobState` 实际跨 851-974 行。

## 没拿什么及原因

- 模型库与预训练权重：本流程按需另选骨干，不绑定 timm 的模型注册表。
- `train.py` 整体训练脚本：与各模型库/项目自带的训练入口冲突，只借局部机制。
- `sweep.py` 的 Slurm/执行器部分（`Executor` 975 行起）：本机不用集群调度。

## 下次升级看哪些路径

- `sweep.py`（较新、改动频繁；重点看 `job_config_hash`、`plan_changes`、`JobState`）。
- `timm/utils/checkpoint_saver.py`、`timm/models/_helpers.py`、`timm/optim/_param_groups.py`。
- `timm/utils/model.py`、`timm/utils/model_ema.py`、`timm/layers/norm_act.py`。
