# 调参：架构改动之后怎样公平地重调，怎样让搜索可续跑

条件：改了结构/损失/数据后要判断改动值不值；基线配方疑似没调好；要做超参搜索；搜索可能被中断。
不变量：只在 select 段上选；预算同时计入完成、剪枝、失败和中断前消耗；改动与对照的干扰超参对称重调。
方法真源：Google《Deep Learning Tuning Playbook》（逐字副本 [vendor/tuning_playbook-README.md](../upstream/vendor/tuning_playbook-README.md)，CC-BY-4.0）；工具：Optuna（[卡片](../upstream/optuna.md)）。

## 顺序（改结构后）

1. **分变量**：科学变量（本次要比较的：是否加模块）、干扰变量（学习率、warmup、权重衰减、正则强度、步数——两边各自重调）、固定变量（其余，写进结论的限定条件）。同名超参在不同分支里是两个超参。原文 playbook 中 "Identifying scientific, nuisance, and fixed hyperparameters" 一节。
2. **先修优化问题**：学习率扫 0.3×–3× 旧最优（对数网格）；最优点贴边界就扩范围；比最优高一档时发散说明不稳定 → 试 warmup、梯度裁剪（按梯度范数 90 分位，超过一半更新被裁就降学习率）、零初始化残差。原文约 844–882、1817–1986 行。
3. **步数**：先不加正则、用恒定学习率估一个够用的最大步数；所有 trial 固定步数，事后从 top-N 检查点里按 select 指标挑，不靠提前停训决定结论（早停截断零初始化分支，见 [选择卫生](../selection-hygiene.md)）。原文约 1186–1254、1508–1548 行。
4. **探索再利用**：先准随机（QMC）探索看边界与不可行区，再用 TPE/贝叶斯冲分；发散的 trial 记为不可行，不删除。原文约 1111–1148、1663–1800 行。
5. **看曲线与隔离图**：每组最优 trial 都看训练/验证曲线（过拟合、步间方差、结束时是否还在升）；对每个科学变量取干扰变量上的最优，画隔离图。原文约 901–1056 行。
6. **采纳前复跑**：把最优配置重跑 N 次估重训方差；增益要超过两边各自的波动带，并抵得上复杂度。原文约 1057–1110 行；配对比较见 [受控比较](../../../mlgain-integrate-component/references/controlled-comparison.md)。

预算很小时：< 10 次只调学习率；10–25 次加 β1；更多再加其他。

## 可续跑搜索：`scripts/hpo_study.py`

包装项目已有训练命令，不接管训练器：

```bash
# 用装了 optuna 的项目解释器（optuna 在脚本顶部导入）
<project-python> ~/.claude/skills/share-autoresearch-engine/scripts/hpo_study.py --help
<project-python> .../hpo_study.py create --storage sqlite:///runs/hpo/study.db --study S --space space.json --metric ap --direction maximize --budget 24 [--fixed NAME=VALUE] [--enqueue base.json]
<project-python> .../hpo_study.py run    --storage sqlite:///runs/hpo/study.db --study S --log-dir runs/hpo/logs -- <训练命令>   # 训练命令读 $HPO_PARAMS_JSON，写 $HPO_METRICS_JSON
<project-python> .../hpo_study.py report --storage sqlite:///runs/hpo/study.db --study S
```

参数名以 `--help` 为准。`create` 把搜索空间、指标、预算与固定参数存进 study，之后以不同设置再次 `create` 会被拒绝，防止重启后配置漂移。

- 存储：SQLite（`--storage sqlite:///…/study.db`），重启 `load_if_exists`；心跳 + `RetryHeartbeatStaleTrialCallback`：被系统杀掉的 trial 自动重新排队（共享服务器上常见），但只有预算还有剩余时才会再跑，否则保持 WAITING，`report` 里可见。用 SIGKILL 杀掉 runner 时它启动的训练子进程不会跟着停，需按 PID 处理；多个 worker 并行时总数最多超出预算 worker 数减一。
- 预算：完成、剪枝、失败和运行中的 trial 都占名额（`MaxTrialsCallback` 与 `run` 的计数一致），跨重启不重置；运行中的 trial 在心跳过期转为失败后仍占名额，排队（WAITING）的配置要有空余名额才会跑；runner 在第一次心跳前被杀的 trial，过了宽限期由下一次 `run` 标为失败（输出 `failed_unbeaten_now`）。失败 trial 记录日志路径，不吞异常。
- 起点：`--enqueue` 先放旧最优和基线配置；`--fixed` 用 `PartialFixedSampler` 固定科学变量只调干扰变量。
- 采样：前 N 个 QMC，之后 TPE（multivariate、并行时 constant_liar）。
- 剪枝：默认不剪。按中间值剪枝的剪枝器会剪掉起步慢的零初始化分支；需要提前淘汰时只用配对的 `WilcoxonPruner`，且只上报 select 段逐样本分数。
- 记录：每个 trial 挂运行清单（`run_manifest.py`）路径与 git HEAD；`report` 输出最优、全部 trial 表与参数重要性。

## 训练过程里的保护（借鉴）

- 发散回滚：损失出现 NaN 或突增时回到上一个检查点、学习率乘 0.25 再继续，并记录（AutoDL 冠军方案的做法，[卡片](../upstream/autodl.md)）；回滚次数计入该 trial 的失败信息。
- 检查点：固定步数训练时保留按 select 指标排序的 top-N 检查点与可续跑存档，同配置多 seed 的结果按配置身份汇总（timm `CheckpointSaver`、`sweep.py aggregate_repeats` 思路，[卡片](../upstream/timm.md)；配置身份见 `scripts/run_manifest.py` 的 `config_identity`）。
- 有 Lightning 训练器时可直接挂 `SpikeDetection`、`EMAWeightAveraging`、`LearningRateFinder` 等回调（[卡片](../upstream/lightning.md)）。

## 不要

- 在评测集或测试集上调任何超参（含增强策略、阈值、步数）。
- 拿为旧结构调好的超参直接比较新结构（测的是"旧超参适合旧结构"）。
- 几步训练就宣布架构优劣；慢热的候选延长训练，检查早期排名是否可靠。
