# 架构 Ablation：按任务选入口

本页有两个**独立入口**，按任务选一个，不互为前置：

- **入口 A：结构位置消融**——只用于改模型内部前向拓扑（加模块、换 block/neck/skip/head）。
- **入口 B：数据/站点级 4-way PK**——只用于改共享与训练组织（单模型包打/独立/stacked/cluster），不改模型内部结构。

只做 B 的任务（例如同一 LGBM 只比较共享与独立训练）不要求原生位置，也不要求位置消融。
只做 A 的任务在位置没判断前，不要先比模块族。

## 入口 A：结构位置消融（仅改模型内部拓扑）

先过[结构判断门禁](architecture-judgment-gate.md)。同一个模块，比较能区分假设的候选位置，其中一个是论文/原结构的原生位置；若只有原生位置，写明原因。

| 位置 | 典型接法 | 改变什么 |
|---|---|---|
| 输入/stem | 额外编码分支 | 输入表征，常与 backbone 冗余 |
| encoder block 内 | 残差/注意力/归一化 | 局部特征与优化路径 |
| bottleneck | ASPP/全局上下文/transformer | 感受野与全局信息 |
| decoder block 内 | 残差/注意力/融合 | 上采样细节与梯度 |
| skip 连接 | attention gate / 加权融合 | encoder 特征选择 |
| neck | BiFPN/FPN/HRNet 式融合 | 多尺度信息整合 |
| head | 质量头/辅助头/损失 | 输出合同与排序 |

位置实验先做，再做模块比较：

```text
A. 同一模块 × 能区分假设的候选位置（含原生；单位置须写明原因）  ← 先做
B. 同一已验证位置 × 多个候选模块                        ← 位置结果取得后再做
```

不要做：同一外挂接口 × 10 个模块，然后写“模块都没用”。

## 入口 B：数据/站点级 4-way PK（仅改共享与训练组织）

只决定“是否共享模型/如何分站”，不改模型内部前向结构；不要求模块、原生位置或位置消融。

## 何时触发
- 怀疑当前架构（"1 个模型包打 N 个场景"是否合理？）
- 跨数据集 transfer 决策前
- 长 horizon vs 短 horizon 共享/独立训练决策
- 多站 / 多 series 项目早期

## 4 种标准架构

| 架构 | 描述 | 适用情境 |
|---|---|---|
| **A. 单源包打** | 用 1 个 source / station 训的模型应用全局 | 当前 baseline |
| **B. 完全独立** | N 个 series / station 各训各的 | 数据量充足 + 站间异质 |
| **C. Global stacked** | 1 个大模型 + 类别 ID 共享参数 | 数据量贫乏 + 站间相似 |
| **D. Cluster** | 按相似度分组 K 个模型（K < N）| 折中：用 spearman 矩阵分簇 |

## 实施模板

```python
# 沙盒：exp_<round>_arch_ablation/run.py
# 同 split + 同特征 + 同超参，只换架构

def fit_predict(train_df, val_df, station, architecture, ...):
    if architecture == 'A_single':
        # 用 station_0 训，应用所有 station
        model = LGBM().fit(train_df[train_df.station==stations[0]][feat], target)
    elif architecture == 'B_independent':
        # 每站独立
        model = LGBM().fit(train_df[train_df.station==station][feat], target)
    elif architecture == 'C_stacked':
        # 全部 stack + station_id 类别
        train_df['station_id_cat'] = train_df['station'].astype('category')
        model = LGBM().fit(train_df[feat + ['station_id_cat']], target,
                           categorical_feature=['station_id_cat'])
    elif architecture == 'D_cluster':
        # 用 spearman 矩阵 + KMeans 分 K 簇
        cluster = clusters[station]
        cluster_data = train_df[train_df.station.isin(cluster_members[cluster])]
        model = LGBM().fit(cluster_data[feat + ['station_id_cat']], target)
    return model.predict(val_df...)


def main():
    results = {}
    for arch in ['A', 'B', 'C', 'D']:
        scores = []
        for station in stations:
            r = fit_predict(train, val, station, arch, ...)
            scores.append(r['rmse_score'])
        results[arch] = {'per_station': scores, 'mean': np.mean(scores)}
    return results
```

## 关键纪律

- **同 split** — 同 train / val / test 划分
- **同特征集** — 不要 A 用 5 特征 B 用 50 特征
- **同超参** — 默认值，禁止 per-arch 调参（混淆变量）
- **同 metric** — 同 cap 归一化 + 同评测函数
- **报 per-station × per-arch 表** — 不只看平均，看每站谁赢

## 解读规则

| 模式 | 含义 |
|---|---|
| B >> A（>+0.05）| 当前架构严重不当，必须切独立 |
| B ≈ C ≈ D（±0.005）| 架构差异很小，省事用最简单 |
| C > B（数据稀疏时）| 数据量是瓶颈，global 借同行数据 |
| D 比 B 强（明显站间相似）| cluster 是甜点 |
| 每站最佳架构不同 | hybrid 配置：每站选最佳，期望再 +0.005 |

## 实战例（多站光伏预测项目 R11）

国网 8 站 4h 1-RMSE/Cap：
- A. site1 包打 = **0.7959**
- B. 8 独立 = **0.8986** 🥇 +0.103
- C. global stacked = 0.8941
- D. 3-cluster = 0.8975 🥈

→ B 暴胜 A 0.103；B/C/D 内部差异 < 0.005；每站最佳架构不一（hybrid 估 +0.005）。

**论文叙述**：
> "We find single-source models suffer 10pt mean drop on cross-station evaluation, motivating per-station independence as the architectural baseline (B), with hybrid (per-station best architecture) yielding marginal additional gain."

## 快速决策树

```
怀疑架构？
├── N stations ≥ 5?
│   ├── 是 → 跑 4-way PK
│   └── 否 → 直接 B 独立 + C stacked 2-way PK
├── per-station 数据 < 5k?
│   └── C stacked 通常胜（global 数据量优势）
└── per-station 数据 ≥ 50k?
    └── B 独立通常胜
```

## checklist

- [ ] 沙盒目录建好
- [ ] 4 种架构代码各 1 个函数
- [ ] 同特征 / 同超参 / 同 split 写明
- [ ] per-station × per-arch 表
- [ ] mean 排名
- [ ] hybrid 上限估计
- [ ] 论文 method 章节素材
