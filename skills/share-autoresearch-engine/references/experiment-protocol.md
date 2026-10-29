# Pipeline 执行协议：从 pilot 到 test

本页只写**模板如何落地** experiment；阶段定义、五个接口合同和每阶段门槛以 [标准流程](workflow/standard-flow.md) 为唯一真源。项目合同可以加严，不能放松标准流程的 fit/select/evaluate/test 边界。

## 0. S0：先选栈，不先写代码

首次选栈或实质换栈，先在 `stack-card.md` 写清：任务范式、数据形态、评价器、候选栈、适配点、bake-off 标准、放弃条件。模板见 [Stack Card 模板](../assets/stack-card.template.md)。

已有批准的选型、同一 runner 的小改，复用现有 card；任务/数据/评价器或候选栈实质变化才重写。S0 不替代 S1 的指标合同：任务和部署单元不明时，先澄清，不先做最终选栈。

## 1. Pilot：找值得跑满的配置

pilot 的目的不是出最终分，是排除明显不值的配置。

- 同一 split、同一验证集、同一评价器；
- 每次只改一个因素：LR、batch、crop、增强、weight decay、loss sigma；
- 每次 300–500 步，看**平滑后的 val loss**，不看单点；
- 先跑 baseline，再跑候选；baseline 不跑，不比较；
- 一个因素 2–3 个值即可，不做全网格；
- 总共 5–6 个 pilot 是量级，不是硬指标；按因素数量拆，不随机试。

### 曲线判读

| 形态 | 判断 | 动作 |
|---|---|---|
| train/val 都降，best 在 cap | 右删失，未证明收敛 | 预算允许就扩展；否则标右删失做固定预算比较 |
| val 先降后升，train 继续降 | 过最低点，典型过拟合 | 取最低点，停止加预算 |
| val 平台，train 降 | 可能过拟合/容量过剩 | 取平台起点，检查正则 |
| 两者都平台 | 当前配方收敛 | 可进入比较，别再加步数 |
| 剧烈震荡 | 优化不稳/LR 过大/数据问题 | 先降 LR、查异常样本 |
| val 降但部署指标不涨 | 选点指标与报告指标不一致 | 记录两者，诊断，不用 test 选 |

### 预算阶梯

```text
1000 → 2000 → 4000 → 8000
```

- “best 在 cap 且平滑曲线仍在降”时，预算允许就翻倍；预算不允许时标 `RIGHT_CENSORED`，可做同预算比较，但不写“已收敛”；
- 翻倍后仍 best at cap，写 `RIGHT_CENSORED`，不写“已收敛”；
- 看到 val loss 最低点并回升后，停止加预算；
- 预算是安全上限，不是固定 epoch 数。

## 2. “训练到过拟合”的准确含义

不是把 train loss 刷到 0，也不是最后一个 checkpoint 就是模型。

准确含义：

1. 训练预算足够长，val loss 已经出现最低点并开始上升；
2. 这证明最低点存在，不是被 cap 截断；
3. 恢复最低点的权重；
4. test 只测一次。

若 val loss 一直降到 cap，不能说过拟合，也不能说收敛；只能说“预算不足，最低点未知”。

## 3. 选点规则

- 主选点指标：`val loss`（项目合同另有规定除外）；模板固定为加权 `val/loss` 最小。
- 同时记录：部署指标、单视图指标、阈值；多任务逐任务 loss/metric 也要记录。
- 选最低 `val loss`；并列时取更早 step，并记录并列数。
- 不按 test 选 checkpoint、阈值、集成权重、解码器。
- 若 `val loss` 最低的模型部署指标更差，先诊断：
  - 单视图 vs 多视图/集成；
  - 选点 loss 与部署 metric 的定义差异；
  - 阈值是否只在 select 段选；
  - 是否是 seed/图像级方差。
- 诊断结果写成“选择指标不一致”，不写成“过拟合”或“模型更好”。
- 多任务首版只支持共同 `val/loss` 最小化，这是明确的总损失折中，不是每个任务各自最优；逐任务 checkpoint 未实现，不能声称支持。

## 4. HPO

- 工具：Optuna（单机首选）或 Ray Tune（多机/大规模）；Lightning 只提供接口，不是 HPO 系统。
- 搜索顺序：LR → batch/crop → 正则/增强 → loss 参数；不要一次搜全部。
- 搜索空间：写清上下界、log/linear、条件参数；不搜无意义的组合。
- 预算：每个 trial 用短预算，promising 的 trial 再加预算；Hyperband/ASHA 优先于网格。
- trial 上限：按验证集大小定；试验太多会过拟合 val。
- 确认：HPO 选出的配置要用独立 seed 复跑；有条件用 nested CV 或新 holdout。
- 记录：study name、sampler、pruner、trial 数、搜索空间、best trial、失败 trial。

## 5. 探索轨与主张轨

同一句“更好”必须标明是哪一轨：

| 轨道 | 预算 | 允许的结论 | 不允许的结论 |
|---|---|---|---|
| 探索轨 | 可以不等预算，先找优势 | “这个方向有希望”“工程上更强” | “全面领先”“科学上更好” |
| 主张轨 | 同 split、同预算、同调参预算、同集成规则 | “同预算下更好/无差异/更差” | 用探索轨的结果冒充主张轨 |

公平性不是第一步，但它是**主张的门槛**。先冲优势可以；一旦要写论文/对外结论，必须补同预算 baseline，或明确标注“engineering-only，不是公平比较”。

## 6. 比较与采纳

- 同 split、同预算、同评价器、同阈值规则；
- 主张轨至少 3 seeds；报均值、标准差、逐库方向；探索轨可少 seed，但不得写成主张；
- 先看候选间差异、并列/接近程度、seed 或独立单位方差；再看排名是否稳定；
- 图像任务按图像配对 bootstrap；时序按时间块/实体；
- 与 baseline 比，不与“上次的偶然高分”比；
- 结论只写 有用/无用/有害/不可判；
- 提升小于方差地板时，不写“提升”。

## 7. test guard

- test 只在协议冻结后开一次；开发阶段 `check_run.py` 只做开发准入，最终 test 用独立回执；
- 冻结前写 `FREEZE.json`：代码 commit、生效 config hash、数据 hash、split、checkpoint、阈值、集成规则；
- test 结果写一次，不覆盖；已授权读取的 test 结果可进最终报告，但不得回流选择；
- test 不能用于选 checkpoint/阈值/模型/集成权重；
- 若 test 已开过，后续实验标“test 已污染”，不得冒充首次测试。

## 8. 每个 run 的 manifest

至少：

```yaml
git_commit:
config_sha256:
resolved_config_path:
resolved_config_sha256:
data_sha256:
split_seed:
train_seed:
budget_max_steps:
best_step:
best_val_loss:
deployment_metric:
test_read: false
```

`config_sha256` 是原始 YAML；`resolved_config_*` 是 CLI 覆盖后的生效配置。只记录前者不能复现最终运行。没有 manifest 的 run，不进入比较表。模板见 [Run Manifest 模板](../assets/run-manifest.template.yaml)。

## 9. 验收门

| 门 | 通过标准 |
|---|---|
| 数据 | 样本叠图、标签对齐、归一化只来自 train |
| smoke | 记忆探针达到预期下限；真实增强下有学习信号；断梯度必失败 |
| 恢复 | checkpoint strict reload；resume 后 step0 输出一致 |
| 基线 | 同口径 baseline 已跑；positive control 复现 |
| 选点 | val loss 最低；best 不在 cap，或已标右删失的固定预算比较；并列数已记录 |
| 比较 | 同主预算轴；≥3 seeds 起步；报告区间/方差 |
| 溯源 | manifest 完整；resolved config 可核验；test_read=false |
| test | 冻结后一次；结果不覆盖 |

任何一门没有结果，写“不可判”，不写“有效”。
