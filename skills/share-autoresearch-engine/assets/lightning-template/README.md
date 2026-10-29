# Lightning 参考流水线

这是全局 `research-dl-pipeline-base` 路由下的**最小可运行参考实现**，不是生产检测器。它证明三件事：

1. 换数据：同一循环跑 2D 图像张量、1D 时序张量和共享 backbone 的多任务张量；
2. 换模型/head：只换 `config.model`，训练循环不动；
3. 选点/test 有可见产物：`best.ckpt`、`manifest.yaml`、`budget_guard.json`、`curve_audit.json`。

## 依赖与 GPU

```bash
python -c "import torch, lightning, yaml, numpy; assert torch.cuda.is_available()"
nvidia-smi
```

按你的实际环境替换解释器；全局文档不绑定某个 env。
**深度学习训练默认 `accelerator: gpu`；无 CUDA 时入口以 `CUDA_REQUIRED` 退出。** CPU 只用于 `tests/` 的单测和 wiring 检查，命令必须显式写 `--accelerator cpu`，输出带 `CPU_WIRING_ONLY` 警告，不能当作训练验收。
没有 Hydra 也能跑；配置用 YAML + argparse。Hydra 是可选的上层，用于多实验组合与 multirun；参考 https://hydra.cc/docs/intro/

**test 使用边界**：项目所有者可给长期授权，授权后直接对冻结模型做 evaluation，不再逐次申请/封存；test 不得用于训练、调参、阈值/checkpoint/集成选择或伪标签。每次评价写不可覆盖回执；详见 `references/experiment-protocol.md` 第 7 节。

## 快速开始

```bash
cd <skill>/assets/lightning-template
# 单测：CPU wiring only
python tests/smoke.py
# 真实 GPU：同一份数据，走默认 Lightning GPU 路径
python -m pipeline.train --config configs/points.yaml \
  --data-path /tmp/points.npz --output-dir /tmp/runs/points-gpu \
  --max-steps 20 --accelerator gpu --devices 1
```

GPU 跑完必须检查 `accelerator_receipt.json`：`status: GPU`、`device: cuda:0`、非零 `peak_allocated_bytes`，并记录 GPU 名称和显存。没有这个回执的 run 不能当 GPU 验收。

`tests/smoke.py` 生成图像、时序、多任务三个 `.npz`，各跑 20 步，检查产物、`last.ckpt`、strict reload、多任务逐任务日志列，并确认 `BEST_AT_CAP` 会被 `check_run.py` 拦住；它显式走 CPU，目的是不依赖本机显卡。
门禁与多任务单测：

```bash
python tests/test_gates.py
python -m unittest tests.test_multitask tests.test_resume_and_entry tests.test_test_read -v
```

`test_gates.py` 覆盖 eligible / BEST_AT_CAP / test_read=true / 验证点不足 / 缺 budget_guard / 伪造 `best_at_cap=false` / history 与回执 best 不一致 / STILL_DECREASING / data hash 不符 / 生效 config 或 resolved config 缺失、hash 不符。`test_multitask.py` 覆盖梯度、strict reload、非法权重、dtype/sample_id；`test_resume_and_entry.py` 覆盖续跑选点状态/lineage、预算变更拒绝、选点配方不变、只读输出目录预检、test flag 阻断、无结构调参放行和缺结构卡拒绝；`test_test_read.py` 覆盖同一进程重复读、既有 flag 和 test 文件与训练文件同路径。

## 单次训练

```bash
python -m pipeline.train \
  --config configs/points.yaml \
  --data-path /path/to/points.npz \
  --output-dir runs/points \
  --max-steps 2000 \
  --accelerator gpu \
  --devices 1
```

示例 config 声明 `structure.mode: baseline`，同时给出 `baseline_reason` 和 `baseline_sha256`（模型 + module type 的指纹）；改模型/head/位置时改成 `changed` 并传 `--structure-card CARD.json`（或 `structure.card`）。baseline 指纹不符、缺卡、卡过期、预算/seed 不符都会在创建优化器前退出。只用 `--validate-only` 可先校验不训练：

```bash
python -m pipeline.train --config configs/points.yaml \
  --structure-card CARD.json --validate-only
```

恢复：

```bash
python -m pipeline.train --config configs/points.yaml \
  --data-path /path/to/points.npz --output-dir runs/points \
  --max-steps 2000 --resume runs/points/checkpoints/last.ckpt
```

`--resume last` 会取 `output_dir/checkpoints/last.ckpt`；checkpoint 必须在同一 `output_dir` 内，外部 checkpoint 属于 warm start，不能当 resume。续跑只接受同一 run 的 `checkpoints/last.ckpt`，并核对 checkpoint 内部 `dirpath`、BudgetGuard 选点与磁盘 `budget_guard.json`；整目录复制会被拒绝；早于磁盘选点状态（`best_step`/`best_loss`）的旧 checkpoint 回退会被拒绝，但不声称拦截所有旧进度。结构卡与结构配置不变；学习率/seed 不算结构；loss、loss_weights、tasks、`data.target_dtypes` 等选点口径写 `selection_recipe.json`，同一 run 改它会被拒绝；预算变更需新建 run（changed 还要新卡）。每次续跑写独立的 `resolved_config.resume-N.yaml`，旧 `manifest.yaml` 备份为 `manifest.previous*.yaml`，旧证据不被覆盖。

时序：

```bash
python -m pipeline.train \
  --config configs/series.yaml \
  --data-path /path/to/series.npz \
  --output-dir runs/series \
  --max-steps 2000
```

## 数据格式

`.npz`：

```text
x_train, y_train
x_val, y_val
# 可选：x_test, y_test, sample_ids_train, sample_ids_val, sample_ids_test
```

shape 原样保留：

- 图像：`(N, C, H, W)`
- 时序：`(N, T, C)`
- 3D：`(N, C, D, H, W)` 只保留 shape；示例模型只有 2D/1D，3D 要自己加模型

多任务 `.npz`：

```text
x_train, y_train_<task>, x_val, y_val_<task>, y_test_<task>...
# 可选：sample_ids_train/val/test
```

`data.tasks` 声明任务；`data.target_dtypes` 可逐任务覆盖 dtype（默认 float32）。所有任务必须共用同一输入与同一批样本；缺标签、异步任务采样不在首版范围。详见 `references/multi-task.md`。

test 必须放在**单独文件**，并显式传 `--test-path` + `--allow-test`。`--allow-test` 是技术防误触开关，不是逐次用户授权：项目合同若已给长期 test 授权，直接在命令里传，不再申请，也不要求 `TEST_SEALED`。test 只用于冻结模型评价，不得用于训练/调参/选择。例如：

```bash
python -m pipeline.train --config configs/points.yaml \
  --data-path /path/to/points.npz --output-dir runs/points \
  --max-steps 2000 --test --allow-test --test-path /path/to/test.npz
```

`--test` 会在训练结束后用 `best.ckpt` 评价 test；`test_dataloader()` 要求显式 `test_read_flag`，用独占创建写 `test_read.flag`，同一对象第二次调用、并发第二个进程、训练入口见到既有 flag、以及 `check_run.py` 见到该文件都会阻断。这个 flag 防止同一 run 内重复读和误读，不是用户授权门；项目长期授权下可以新建 run 重新评价。test 文件还必须与训练文件不是同一 inode（含硬链接）；这是人工合同 + flag，不是密码学证明。

## 换模型 / 换 head

`pipeline/models.py` 里有 `MLP`、`SmallUNet`、`TCN`，仅作示例。换自己的模型：

1. 在 `models.py` 加一个 `nn.Module`；
2. 在 `build_model` 注册；
3. 改 `config.model.name` 和 `kwargs`；
4. 不改 `pipeline/train.py`。

换 head 就是在模型内部换最后一层；如果 head 有独立参数，写进 `kwargs`。多任务用 `model.name: multitask` + `model.kwargs.backbone/heads`；共享 backbone 用 `return_features: true`，每个 head 的 `in_channels` 必须匹配 backbone 输出通道。选点固定为加权 `val/loss`，不提供每任务 best。

## 换 loss / metric

`pipeline/losses.py` 里注册函数，config 写名字。当前 metric 是**逐 batch 计算再按 batch 平均**，适合 smoke；正式实验要用 `torchmetrics` 做精确累积，或把预测/标签收集后统一算。

## 产物

```text
runs/points/
  checkpoints/best.ckpt
  checkpoints/last.ckpt
  test_read.flag       # 只有读过 test 才出现
  budget_guard.json    # best step/loss, 是否 BEST_AT_CAP, 曲线历史
  curve_audit.json     # TURNED_UP / PLATEAU / BEST_AT_CAP / INSUFFICIENT / UNKNOWN / INVALID
  manifest.yaml        # git/config/data hash, seed, budget, test_read=false
  resolved_config.yaml # CLI 覆盖后的生效配置；manifest 记录其 hash
  resolved_config.resume-1.yaml  # 续跑段的独立快照
  structure_config.yaml # 结构相关字段（model + module type/structure）的稳定哈希
  selection_recipe.json # loss/tasks/loss_weights 等同 run 选点口径
  structure_gate.json  # changed 模式的卡/配置绑定
  structure_card.json  # changed 模式的卡快照
  structure_baseline.json # baseline 模式的无结构改动声明
  logs/csv/...
```

门禁：

```bash
python ../../scripts/audit_curve.py runs/points/budget_guard.json
python ../../scripts/check_run.py runs/points
```

`check_run.py` 在 `BEST_AT_CAP`、缺字段（含 `resolved_config_path` / `resolved_config_sha256`）、`test_read != false`、`test_read.flag` 存在、曲线 verdict 不是 `TURNED_UP/PLATEAU`、config/data/resolved config hash 不匹配时返回非零。固定预算比较可加 `--allow-censored`，但输出会标 `censored=true`，不得写成收敛；它要求 `config_path`/`data_path` 存在；复制 run 目录只用于只读检查，不能当作可续跑证据。

`--strict` 会把 `git_dirty=true` 也判为阻断；默认只 WARN，并在 JSON 里给 `claim_eligible=false`。data 文件超过 2 GiB 时不重算 hash，只 WARN（大文件全量 hash 会阻塞收尾）。

## 这个模板不解决什么

- 不提供业务检测器、阈值或集成适配；
- 不证明分布式 metric 正确；val 已加 `sync_dist=True`，但 2 卡只做过冒烟，不宣称生产正确；
- `test_read` 是独占 flag + inode 检查，不是密码学证明；同一 run 内防重复，跨 run 允许在长期授权下重评，但 test 结果不得回流选择；
- 没有自动 HPO、没有 Hydra multirun；
- 多任务只实现首版最小 contract，不支持缺标签、异步采样、PCGrad/GradNorm、每任务 best checkpoint；见 `references/multi-task.md`；
- 没有生产 Serving、没有数据版本管理；
- 替换已部署的检测器/生产模型前必须做同输入 parity，不得直接把参考模板当生产实现。

## 推荐阅读

- Lightning: https://lightning.ai/docs/pytorch/stable/
- Lightning checkpoint: https://lightning.ai/docs/pytorch/stable/common/checkpointing.html
- Hydra: https://hydra.cc/docs/intro/
- Optuna: https://optuna.readthedocs.io/en/stable/
- torchmetrics: https://lightning.ai/docs/torchmetrics/stable/
