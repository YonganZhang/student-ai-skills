# Per-Cell 思维 — 多任务 ≠ 一锅煮

## 核心原则
项目有 N 个 cells（数据集 × horizon × station × metric × ...）就是 N 个独立 task。**默认假设"一个模型包打"是错的**，先做 per-cell ablation 再决定共享 vs 独立。

## Cell 拆分维度（按项目套用）

| 维度 | 例子 |
|---|---|
| 数据集 | guowang / GEFCom / SKIPPD |
| 时间 horizon | 15min / 1h / 4h / 24h / 72h |
| 实例 / station / 用户 | site_1 ~ site_8 / cell_1 ~ cell_8 |
| 评测 metric | RMSE / MAE / MAPE |
| 时段 | day / night / season |
| 子人群 / 设备 | 不同传感器 / 客户分群 |

例：3 数据集 × 3 horizon × 8 站 = 72 cells，每个本质是不同 task。

## 4 种共享策略（per-cell ablation 必跑）

| 策略 | 描述 | 数据效率 | 灵活性 |
|---|---|---|---|
| A. **Single global** | 1 个模型 + 类别 ID 当特征 | ★★★★ 最省 | ★ 最差 |
| B. **Per-cell independent** | 每 cell 独立模型 | ★ | ★★★★ |
| C. **Global stacked** | 全局训练 + per-cell calibration head | ★★★ | ★★★ |
| D. **Cluster** | 相似 cell 分组（K-means + 几何/容量）| ★★ | ★★★ |

## 决策实施

```
# Step 1: 跑 4 路 PK on val（同 split, 同 features）
results = {A: ..., B: ..., C: ..., D: ...}

# Step 2: 看每 cell 的最优策略
best_per_cell = {cell: argmax(results, cell)}

# Step 3: 根据频率决定主策略
if mode(best_per_cell) > 60%:
    use_dominant_strategy + override_outliers
else:
    hybrid（per-cell 配置矩阵）
```

## 实战例（多站光伏预测项目 R11）

国网 8 站 × 4 架构 PK：
- A 全局: 0.7959
- B 8 站独立: **0.8986** ← 最优
- C global stacked: 0.8501
- D cluster: 0.8703

8 站中：5 站偏好 B，2 站偏好 D，1 站偏好 C → **混合策略**
最终 +0.103 vs 单 A。

## Per-cell 还可以差异化

不只是模型选型，**每 cell 可独立选**：
- **特征集** / lag set（短 horizon 用 lag1-4，长 horizon 用 lag24+）
- **超参数**（容量小 cell 减 LGB 深度防过拟合）
- **训练数据**（时段 / 季节 / cluster）
- **后处理**（不同 cell 不同 clip / blend 权重）

## 触发条件

- 多 horizon / 多 station / 多任务的 cell 数 ≥ 5
- 数据规模差异大（最大 cell vs 最小 cell > 10×）
- 物理 / 业务 domain 差异大（如 8 站不同容量 / 不同地理）
- 当前 baseline 卡住，怀疑"一锅煮"过度

## 反模式

- 🔴 默认 A 策略 ride 到底，不跑 4-way PK
- 🔴 cluster 用 K-means 不用 domain knowledge（容量 / 几何 / 仪器）
- 🔴 找到最优策略就 freeze，不试 per-cell hybrid
- 🔴 per-cell 独立但**特征也独立设计**，无法 apple-to-apple

## 跟 architecture-ablation.md 的关系

per-cell-strategy = **何时该 ablation**（多 cell 项目都该）
architecture-ablation = **怎么跑 ablation**（4-way PK 模板）
