# 多任务：共享 backbone + 多 head

参考模板已实现一个**最小**多任务 runner：共享 backbone、每任务一个 head、每任务独立 loss/metric、单优化器、固定非负权重、共同 `val/loss` 选点。它已通过 CPU 端到端 smoke 和单元检查；这不等于多任务一定优于单任务，也不等于多卡/异步/复杂调度已验证。

## 支持边界（首版）

**支持**

- 同一输入、同一 batch，所有任务标签齐全；
- 共享 backbone，`nn.ModuleDict` 注册每任务 head；
- 每任务独立 loss、独立 metric；
- 单优化器，固定非负 loss 权重；
- 单设备/单进程监督学习；
- dict batch：`{"x": tensor, "y": {task: tensor}, "sample_id": tensor}`；
- `target_dtypes` 可为任务声明 `float32` / `float64` / `int64`，默认 `float32`。

**明确不支持**（配置/实现不承诺，启动前拒绝或需另写适配）

- 任务缺标签、部分任务无标签、异步 loader、动态任务采样；
- PCGrad / GradNorm / 自动权重 / 多优化器；
- 每任务各自最优 checkpoint，或把不同 step 的 head/backbone 拼接；
- DDP/多节点正确性、生产检测器、多模态、RL；
- 未经验证的分类/分割指标聚合。首版只保证标量回归类 metric 的 batch 加权平均；F1/AUC 等需要 torchmetrics 累积，不能拿 batch 平均冒充。

## 结构

```text
batch["x"] ──> shared backbone ──> task_a head ──> loss_a
                              ├──> task_b head ──> loss_b
                              └──> task_c head ──> loss_c
```

```python
class MultiTaskModule(L.LightningModule):
    def __init__(self, backbone, heads, losses, loss_weights, metrics, lr):
        ...
    def forward(self, x):
        z = self.backbone(x)
        return {name: head(z) for name, head in self.heads.items()}
    def _shared_step(self, batch, stage):
        outputs = self(batch["x"])
        losses = {name: self.losses[name](outputs[name], batch["y"][name]) for name in outputs}
        total = sum(self.loss_weights[name] * losses[name] for name in losses)
        ...
```

实际实现：`assets/lightning-template/pipeline/{data,models,module,train}.py`；配置样例：`assets/lightning-template/configs/multitask.yaml`。

## 配置

```yaml
data:
  tasks: [recon, edge]
  target_dtypes: {recon: float32, edge: float32}   # 可选；默认 float32
model:
  name: multitask
  kwargs:
    backbone:
      name: small_unet
      kwargs: {in_channels: 1, base: 8, return_features: true}
    heads:
      recon: {type: conv2d, kwargs: {in_channels: 8, out_channels: 1, kernel_size: 1}}
      edge:  {type: conv2d, kwargs: {in_channels: 8, out_channels: 1, kernel_size: 1}}
module:
  type: multi_task
  tasks: [recon, edge]
  losses: {recon: mse, edge: mse}
  loss_weights: {recon: 1.0, edge: 0.5}
  metrics: {recon: [mae], edge: [mae]}
  lr: 0.001
```

选点规则只有一条：**最低加权 `val/loss`**，`checkpoint_monitor`/`checkpoint_mode` 自定义会被拒绝。这是共同折中，不是每任务最优；`BudgetGuard`、`CurveAudit`、`check_run.py` 和 checkpoint 必须引用同一规则。

## 最小验收

参考模板的 `tests/smoke.py` 与 `tests/test_multitask.py` 覆盖：

- 两个非同义任务的 CPU 端到端训练；
- 每任务 loss/metric 日志列存在；
- 每个 head 和共享 backbone 都收到非零梯度；
- 不同 head 输出形状独立；
- strict reload 后每任务输出一致；
- 非法/全零/负权重、任务 key 不匹配、未知 metric、样本 id 长度错误均失败；
- `best.ckpt` strict reload 可加载；
- `check_run.py` 对 `BEST_AT_CAP` 默认阻断。

未覆盖：GPU/DDP、真实检测/分割指标、分类 dtype/shape 全组合、任务缺标签、复杂调度。别把 smoke 当 parity 或泛化证据。

## 失效模式

- **梯度冲突**：总 loss 降但单任务退化；记录每任务梯度范数，再考虑 GradNorm/PCGrad（首版未实现）。
- **任务采样失衡**：一个任务样本多，主导训练；首版要求同一批样本齐全，不解决采样。
- **loss 尺度不同**：MSE 与 CE 直接相加前先归一化或做权重扫描。
- **选点冲突**：任务 A/B 的 best step 不同；首版只报共同 `val/loss` 折中，不偷偷用总和冒充每任务最优。
- **head 容量不匹配**：共享 backbone 太小；先做单任务 baseline。
- **指标聚合错误**：宏/微/按任务平均写清；F1/AUC 必须用累积实现。
- **target 类型错误**：分类标签用 `int64` 并确认 loss 期望的 shape；默认 float32 不是万能约定。

## 最小实验顺序

1. 每个任务单独跑单任务 baseline；
2. 共享 backbone + 多 head，loss 等权；
3. 只改 loss 权重；
4. 只改采样；
5. 最后才加 GradNorm/PCGrad 等复杂方法。

一次只改一层，否则无法归因。

## 来源

- LightningModule hooks: https://lightning.ai/docs/pytorch/stable/common/lightning_module.html
- torchmetrics: https://lightning.ai/docs/torchmetrics/stable/
- GradNorm: https://arxiv.org/abs/1810.02281
- PCGrad: https://arxiv.org/abs/2006.04120
- Multi-task learning survey: https://arxiv.org/abs/1706.05098

## 边界

- 多任务不适合“任务之间毫无共享结构”的硬拼；先问共享 representation 是否合理。
- 多任务不是免费正则；它可能降低每个任务的上限。
- 本文件描述的是已跑过最小 smoke 的实现，不是已通过 parity 或生产验收的多任务系统。
