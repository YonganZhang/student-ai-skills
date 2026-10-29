# 性价比 Rubric — 通用 ROI 估算

## 触发
任何 L1 → L2 升级前必跑。算不出来 → 默认 KEEP_L1。

## 公式

```
Cost   = work_hours × hourly_rate ($30/h 默认锚) + compute_cost + data_cost
Benefit = E[Δscore] × confidence × downstream_unlock_value
Risk   = P(failure) × max_downside
ROI    = Benefit / Cost

Verdict =
  KEEP_L1                  if ROI < 1
  L2_deferred_priority     if 1 ≤ ROI < 3
  L2_queued (做!)          if ROI ≥ 3 AND Risk < 30%
  L2_deferred_dependency   if 前置依赖未完成
```

## Cost 估计参考表（通用）

| 改动类型 | 典型 work_hours |
|---|---|
| 一行参数 / 后缀改动 | 0.3 h |
| 加几列特征 | 1~2 h |
| 加 lag/rolling 特征（已有模板）| 0.5 h |
| 改 custom loss / objective | 4 h |
| 跑一次 baseline 评测 | 0.1~0.5 h |
| 自动调参 1000 轮 | 6 h（后台）|
| 接入新 backbone 模型 | 4~12 h |
| 写新评测器 + 单测 | 2 h |
| Bootstrap / CI 评测 | 2 h |
| 实现 SOTA 论文模型 | 6~24 h |
| 沙盒架构 ablation 4-way | 4 h |
| 重读题目 / 重审 spec | 1 h |
| 数据找补 + hash 校验 | 3 h |
| 多智能体 round（Sub+Strategist+Verifier）| 2~4 h（人监工时）|

## Benefit 估计参考表（示例先验，不是通用常数）

下表数值来自表格型时序预测任务（0–1 量纲的 skill/R² 类指标），只用于排序和量级直觉。换任务、换指标时，先用本项目的 seed 噪声底和"预测 Δ vs 实际 Δ"记录（见 `lessons-learned-meta.md` 校准流水）重标 E[Δscore] 与 confidence，不直接套用。

| 改动类型 | E[Δscore] | confidence |
|---|---|---|
| 修真 bug（leakage / NaN / cap leak）| +0.005~+0.02 | 90% |
| 加 1 个强物理特征 | +0.001~+0.006 | 50% |
| 累积变量差分 / 简单衍生 | +0.0005~+0.005 | 70% |
| 自动调参 | +0.003~+0.005 | 80% |
| 替换核心 loader 数据源 | -0.03~+0.01 | 30% |
| 上 NN 首次（domain task） | -0.02~+0.05 | 40% |
| 上预训练 backbone（frozen） | +0.005~+0.02 | 70% |
| Stacking ensemble | -0.02~+0.005 | 40% |
| 改架构（独立 vs global） | -0.01~+0.10 | 50% |
| 重读 spec / 修偏差 | 不涨分但防失分 | 100% |
| Bootstrap CI | 不涨分但加置信 | 100% |

**downstream_unlock_value**：
- 修 spec / 评测口径 → ×3（unlock 所有 baseline 可信度）
- 数据完整性修复 → ×2（unlock 模型可上场）
- 普通特征 → ×1

## Risk 评估

| 改动类型 | P(failure) | max_downside |
|---|---|---|
| Hygiene（不动模型）| 5% | -0.001 |
| 加新特征 不删旧 | 10% | -0.01 |
| 替换核心 loader | 30% | **-0.03** |
| 改 loss/objective | 30% | -0.02 |
| 上 NN 首次 | 50% | -0.05 |
| 自动调参 | 5% | 0 |
| 沙盒架构 PK | 5% | 0（沙盒不污染主线）|

## 校准判断

- **单变量 EDA 相关推断的涨幅通常大幅高估**（示例：一个光伏预测项目实测高估 5–60 倍）；方向往往对，量级常差一个数量级。
- 没有本项目校准记录时，confidence 取保守值；首批实验跑完后按 `lessons-learned-meta.md` 的校准流水更新，不沿用固定折扣。
- 跑过的失败实验也写 lesson，并记入"预测 Δ vs 实际 Δ"，让下次同类估计有据可依。

## 决策模板

```markdown
## 探索 NNN: <题目>
Cost: <X> h × $30 = $<Y>
Benefit:
  - E[Δscore]: +<Z>
  - confidence: <P>%
  - downstream_unlock: ×<M>
  → V = Z × P × M
Risk:
  - P(failure): <Q>%, max_downside: -<D>
ROI = V / Y = <R>
Verdict: <KEEP_L1 / L2_queued / L2_deferred_priority>
Reason: <一句话>
```

## 反模式

- 🔴 "试试就试试" → 没估 cost
- 🔴 LLM 说"很 promising" 跳过 rubric
- 🔴 confidence 默认 70%（应是 30-50%）
- 🔴 不算 max_downside（一次跌分让 baseline 整个不可信）
- 🔴 不算 downstream_unlock（重读 spec 看似无分但 ×3）
