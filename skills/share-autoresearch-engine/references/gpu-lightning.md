# GPU 与 Lightning 执行合同

这是训练执行层的硬规则，不是“可选加速”。方法判断仍然先看
[training-core.md](training-core.md)；本页只规定**在哪里跑、用什么循环跑、怎样证明迁移没有换掉科学口径**。

## 1. GPU 是训练前提

- 所有深度学习训练默认在 CUDA GPU 上执行。CPU 只允许三类用途：数据检查、纯 CPU 单元测试、无梯度的推理/形状探针。
- CPU 跑 20 步不能当作“训练已迁移”“训练已通过”或“GPU 可用”的证据；最多写 `CPU_WIRING_ONLY`。
- 入口在创建优化器前检查 `torch.cuda.is_available()`；不可用直接退出，错误信息写 `CUDA_REQUIRED`，不要静默回退 CPU。
- 运行回执至少记录：`device`（如 `cuda:0`）、GPU 名称、总显存、`peak_allocated_bytes`、`torch`/`lightning` 版本、实际 optimizer steps。
- 多卡不是“越多越好”：先单卡把数据/损失/选点/重载对拍做对；DDP 只改变吞吐，不改变 split、阈值、选点或 test 合同。
- 显存上限按项目合同；不要用“能启动”代替“能跑完一个验证周期”。

检查：

```bash
python - <<'PY'
import torch
assert torch.cuda.is_available(), "CUDA_REQUIRED"
print(torch.cuda.device_count(), torch.cuda.get_device_name(0))
PY
nvidia-smi
```

## 2. Lightning 是默认训练执行层

除以下专用栈外，新训练和迁移训练默认用 PyTorch Lightning 的 `LightningModule` + `Trainer`，不再新写裸 `for batch in loader` 训练循环：

- LLM/VLM/Transformer 微调：HF Trainer/TRL；
- OpenMMLab 检测/分割且专用 recipe 已覆盖 ≥80%：MMEngine/MMDetection/MMSegmentation；
- RL、GAN、多 optimizer 强耦合、需要精细控制每步的研究循环：自定义循环，但必须在 stack card 写明例外，并单独做 GPU/重载对拍。

Lightning 负责：device 放置、AMP/精度、optimizer/scheduler 接线、梯度裁剪、日志、checkpoint、DDP、回调。科学口径仍由你负责：loss、split、选点指标、EMA、阈值、test guard 不能交给默认 `EarlyStopping`/`ModelCheckpoint` 自己决定。

参考实现：[assets/lightning-template/](../assets/lightning-template/)。它不是生产检测器；生产任务要接自己的 dataset、loss、evaluator 和选择规则。

## 3. 迁移验收：先 parity，再谈涨点

把原生循环迁到 Lightning 时，至少做下面五项；少一项就只能写“接线中”，不能写“迁移完成”。

1. **同输入 step-0 对拍**：同一模型、同一 batch、同一 eval 模式，原生 `_common_step` 与 Lightning 验证路径的 loss 差值在数值容差内（例如 `1e-6`，按 dtype 定）。
2. **真实 GPU 训练**：至少跑过一个验证周期（不是只跑 1–2 步），日志/回执出现 `cuda` 设备和非零峰值显存。
3. **选中权重 strict reload**：从保存的选中 checkpoint 重新构造模型，`load_state_dict(strict=True)`，重跑固定验证窗口，分数与保存时一致。
4. **优化器成员与更新**：预训练参数、新参数分组无漏无重；冻结参数不更新；新参数确有更新；AMP 下没有把 fp16 权重直接塞进 optimizer。
5. **同预算对照**：迁移前后同数据、同 split、同评价器、同主预算轴；至少一个数据集上比较 val 曲线和选中步。Lightning 本身不保证精度提升；迁移只应复现原口径。

对拍失败时先修接线（device、eval/train 模式、EMA、scheduler 步进时机、loss 归约、增强 RNG），不要用“Lightning 版更好/更差”解释。

## 4. 与历史冻结结果的关系

- 冻结的历史 run 是证据，不因换训练栈而重写、覆盖或重算。
- 新栈产出放新目录；旧 run 保持原 hash 和原 summary。
- 如果新栈只是复现旧协议，结果标签写“Lightning 复现”，不写“新模型”。
- 如果新栈同时改了模型/数据/预算，必须按新实验登记，不能与旧 run 混成同一张表。

## 5. 多 benchmark / 多任务：共享什么，独立什么

“一个统一模型”必须是可执行的定义，不能只是口头：

- **共享**：视觉/原子证据 encoder、模块 bank、接口契约、路由、预处理语义、日志与回执格式。
- **按任务独立**：输出 head（点热图、偏移、实例/组成、晶格/侧车、在线策略等）、loss 权重、解码器、阈值、选择指标。
- **权重**：允许每个 benchmark 独立训练 checkpoint（数据分布和标签空间不同）；如果要共享权重/联合训练，必须作为单独 ablation，用同预算、多 seed 证明不伤害单库，不能预设它是赢家。
- **禁止**：把点检测、实例组成、晶格、在线策略硬塞进一个静态分割 head 后宣称“统一模型”；这不是统一，是接口错配。

汇报时必须区分：

| 说法 | 含义 |
|---|---|
| 统一架构家族 | 共享 backbone/模块 bank/接口，各任务独立 head/checkpoint |
| 统一 checkpoint | 一套权重同时服务所有 benchmark；需要联合训练证据 |
| 单任务专用模型 | 各库各自结构，不共享 backbone/模块定义 |

没有联合训练证据时，只能写第一或第三，不能写第二。
