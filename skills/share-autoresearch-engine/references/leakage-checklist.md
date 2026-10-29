# Leakage 检查表 — 7 类常见 leakage

## 触发原则

任何"太好"数字（远超直觉 + baseline 跳变 > 5σ + 跨 horizon 一致性破裂）默认假设 leakage，必须排除。

本表查的是**特征**泄漏，触发信号是"数字太好"。若症状相反 —— 数字很吵、seed 间排名不稳、
换个 seed 冠军就变 —— 那是**选择**泄漏（权重/阈值/后处理超参在模型拟合过的数据上选），
本表的直觉不会报警，见 `selection-hygiene.md`。

## 7 类 leakage 类型

### 1. Target shift 错向（最常见）
**症状**: target shift 用 `shift(+H)` 而非 `shift(-H)`
**结果**: 用 t+H 时刻 power 当 features → 完美预测
**检查**: 查 `df['target'] = df['power'].shift(-H)` 应该是 -H

### 2. Cap / Scaler 跨集计算
**症状**: 用 train+val+test 全数据算 cap/scaler，再 normalize
**结果**: val/test 的统计信息泄露到 train
**检查**: 任何 `df['power'].max()` 必须 train-only

### 3. Future NWP / 未来辐照
**症状**: 把 t+H 时刻的"实测"NWP 当 future forecast 用
**结果**: 实测 NWP 含未来真实信息
**检查**: NWP 必须是 issue_time ≤ t 的 forecast，不是 t+H 时刻 ground truth

### 4. Residual lag 用了未来 target
**症状**: AR 残差校正中 val residual lag 用了 val target
**结果**: 大幅虚高（+0.04~0.06）
**检查**: residual_lag(t) = obs(t-H) - LGB_pred(t-H)，不用 obs(t) 的信息

### 5. merge_asof 容差让 future 漏入
**症状**: `tolerance='inf'` 或大容差 + `direction='nearest'`
**结果**: 时间 t 拿到 t+ε 时刻的 NWP/特征
**检查**: tolerance 必须 < H，direction='backward' 优先

### 6. Rolling 跨 split 边界
**症状**: 在 concat(train, val) 后做 rolling，再分回去
**结果**: train rolling 末尾用了 val 数据
**检查**: 明确rolling支持范围与推理可用性，禁止中心窗口偷读未来；历史输入是否可跨分区按任务声明

### 7. Feature engineering 用 全集 fit
**症状**: PCA / LabelEncoder / TF-IDF 在 train+val 上 fit
**结果**: val 信息影响 transform
**检查**: fit 只用 train，transform 用 train+val

## 实战例：AR 残差校正 leakage（多站光伏预测项目 R11）

```python
# 🔴 leaky 写法
vl_res_obs = vl_ok['target'].values - vl_pred_no_ar  # 用了 val target!
ar_X_vl = np.column_stack([np.roll(vl_res_obs, k) for k in range(1, ar_order+1)])
# 结果: 国网 4h NO_AR=0.8999 → WITH_AR=0.9393 (+0.039) ← 假涨

# ✅ 正确写法（recursive prediction）
# At time t, predicting target at t+H
# residual_lag(t) = power_obs(t-H) - LGB_pred_for_(t-H)_made_at_(t-2H)
# 即用 t-H 时刻已经发生过的真实残差
```

## 防 leakage 的 7 个铁律

1. **train-only fit**：任何 cap / scaler / encoder / PCA / etc 必须 train-only
2. **任务匹配**：未来预测按时间留出；已见实体历史插值可使用预先分配的连续时间块，完整窗口隔离。训练批次shuffle不等于划分随机化，详见[划分合同](split-design-contract.md)。
3. **target shift 反查**：写 shift(-H) 后，跑一遍 head 看 target 是否在未来时刻
4. **NWP 必带 issue_time**：feature 是 forecast 不是 truth
5. **merge_asof 检查**：default `direction='backward'`，明确 tolerance 不超过 H
6. **rolling支持**：按声明任务检查原始支持交集与可用时间；使用块划分时清除跨块窗口
7. **辨认"太好"**：跨 horizon 单调一致涨 > 0.05 + 一次实验 baseline 跳变 > 5σ → 默认怀疑

## 自检 prompt（写完代码必跑）

```
我刚写完 X 实验，得到 score = Y。
检查 7 类 leakage:
1. target shift 方向？
2. scaler / cap 是 train-only 吗？
3. NWP 用的是 forecast 还是 truth？
4. lag/residual 用了未来值吗？
5. merge_asof 容差 ≤ H 吗？
6. rolling 跨 split 边界吗？
7. 有 fit 用了 train+val 吗？

如果任何一条不确定，跑 sanity check：把 val features shuffle 后再训，score 应该崩到 baseline。
不崩可能是输入未被使用、基线占主导或存在泄漏，需要进一步定位；不能单凭此项定罪。
```

## Sanity check 实施

```python
# Shuffle val features, score should crash
val_shuffled = val.copy()
val_shuffled[features] = val_shuffled[features].sample(frac=1).values
shuffled_score = evaluate(model, val_shuffled)
# shuffled_score 应接近 random / baseline，不能接近原 score
```

## 论文叙述

如果 reviewer 问"你的 +0.05 是 leakage 吗？"，回答：
> "We tested 7 leakage classes per the autoresearch-engine checklist (Section X). Sanity check via shuffled val confirms model relies on features (shuffled score: 0.65 vs original 0.92). Specifically, residual correction uses only causally available lags (t-H, t-2H, ...)."
