# research-dl-pipeline-base — DL autoresearch 方法论引擎

## 来源
- **执行层（核心 loop）**：[karpathy/autoresearch](https://github.com/karpathy/autoresearch)（2026-03-07，66k+ stars，原版面向 single-GPU nanochat LLM 训练）
- **泛化**：从 LLM 泛化到 DL 多任务（适用程度按"窄 benchmark loop"标准评估，复杂多 metric / 长训练 / 多 cell 任务**需配合治理层**）
- **灵魂**：trial-and-error 高频试错 + Kaggle 当 4 库（模型 / 算法 / 知识 / 领域数据库）
- **治理层**：项目实战沉淀（独立验证 / 架构 ablation / leakage 防御 / per-cell / 多智能体 / 诚实分级）

## 三层架构

```
┌──────────────────────────────────────────────────┐
│ 治理层 — 思考与质量控制                            │
│   核心 10 条方法论 + 多智能体 + evidence trail    │
└──────────────┬───────────────────────────────────┘
               │ idea ↓  │ ↑ lesson
┌──────────────────────────────────────────────────┐
│ 灵魂层 — 试错精神 + Kaggle 资源                    │
│   trial-and-error-growth + kaggle-as-toolbox     │
└──────────────┬───────────────────────────────────┘
               │ exec ↓  │ ↑ metric
┌──────────────────────────────────────────────────┐
│ 执行层 — Karpathy loop                            │
│   single-file modify → fixed budget → keep/discard│
│   via git branch + TSV + NEVER STOP              │
└──────────────────────────────────────────────────┘
```

## Router / 子能力路由

| 用户意图 | 读取 |
|---|---|
| 通用 DL autoresearch / 实验推进 | 本文件 + `references/core-methodology.md` |
| 找数据源 / 评估数据真实性 | `references/sub-skills/share-data-discovery/REFERENCE.md` |
| 时序 foundation model / TimesFM | `references/timesfm/REFERENCE.md` |
| 大栅格 / 云原生数组 / Zarr | `references/zarr/REFERENCE.md` |

## 5 个核心起点（任意一个出发都能驱动 skill）

### 1. 试错与成长（灵魂）
"猜测 → 实验 → keep/discard → 再猜"。不要先想透再动手。一晚跑 100 个 5min 实验 > 想 1 天再跑 1 个大的。失败也是 evidence。
→ [trial-and-error-growth.md](trial-and-error-growth.md)

### 2. Karpathy 核心 loop（执行）
single-file modify → fixed time budget → keep/discard via git branch + TSV log → NEVER STOP。任意 DL 任务套此脚手架。
→ [core-loop-karpathy.md](core-loop-karpathy.md)

### 3. Kaggle 当 4 库用（资源）
**模型库**（top kernel + 公开 weights）/ **算法库**（top 5-10 writeup）/ **知识库**（discussion + comments）/ **领域数据库**（300k+ 公开 dataset）。新 task 第一件事查 Kaggle，不查 = 重新发明轮子。
→ [kaggle-as-toolbox.md](kaggle-as-toolbox.md)

### 4. 迁移学习优先（起点策略）
任意 DL 模态默认先试 frozen foundation model + 下游 head，再考虑 from-scratch。
→ [transfer-learning-first.md](transfer-learning-first.md)

### 5. Evidence Trail L1→L2→L3
所有想到的（包括直觉否定的）入 INDEX.md。L1 brainstormed → L2 filtered → L3 validated。论文 method 章节直接溯源。
→ [evidence-trail.md](evidence-trail.md)

---

## 治理层 10 条方法论（详见 [core-methodology.md](core-methodology.md)）

| # | 方法论 | 核心 | 详细 |
|---|---|---|---|
| 1 | 独立验证不诱导 | Verifier 不读其他 agent 结论 | [independent-verification.md](independent-verification.md) |
| 2 | 架构 ablation | 多实例任务必跑 N-way PK（共享 vs 独立 vs cluster） | [architecture-ablation.md](architecture-ablation.md) |
| 3 | 迁移学习优先 | frozen foundation > from-scratch | [transfer-learning-first.md](transfer-learning-first.md) |
| 4 | 沙盒先行 | 方法学改动先沙盒跑通再合主线 | [sandbox-protocol.md](sandbox-protocol.md) |
| 5 | Apple-to-apple | 同 split / 同特征 / 同评测口径才比 | core-methodology §5 |
| 6 | 机制 vs 现象 | 数字可信，机制是假设需证伪 | core-methodology §6 |
| 7 | Leakage 警觉 | "太好"涨幅默认怀疑 + 7 类排除 | [leakage-checklist.md](leakage-checklist.md) |
| 8 | 多 round 累积 | 每 round 互补不重叠，归档 raw report | [round-based-exploration.md](round-based-exploration.md) |
| 9 | 多实例 per-cell 思维 | N 个实例 = N 个 task，per-cell 配置 | [per-cell-strategy.md](per-cell-strategy.md) |
| 10 | 诚实分级标注 | ✅ 实测 / 🟡 估计 / ⚠️ leaky / 💭 机制 | core-methodology §10 |

## 多智能体协作矩阵

| 角色 | 工具 | 职责 |
|---|---|---|
| Main | 当前主控会话 | 决策整合 / 沙盒实测 |
| Sub-agent | Claude subagent | 数据 / 评测层深挖 |
| Strategist | 隔离子智能体 / WebSearch / academic-search APIs | 文献 / 跨方向综述 |
| Verifier | 独立子智能体；跨模型仅用户点名 | 独立验证（不诱导）|

详见 [multi-agent-protocol.md](multi-agent-protocol.md)。

---

## 执行层 vs 治理层 — 边界明确（解决潜在矛盾）

| 场景 | 走执行层（fast）| 走治理层（careful）|
|---|---|---|
| Hyperparam / 单变量调参 | ✅ Karpathy loop 直接跑 | — |
| 改 data loader / split / metric | — | ✅ 沙盒 + leakage check |
| 改 train.py 单文件小步 | ✅ NEVER STOP | — |
| 涨幅"太好"（>5σ） | — | ✅ Verifier + sanity check |
| 第一周冲分 | ✅ 量取胜 | — |
| 投稿 / 上线 final | — | ✅ apple-to-apple + evidence trail |
| 多 round 跨 agent 协作 | — | ✅ 不进 NEVER STOP loop |

**冲突仲裁**：执行层 NEVER STOP 是指**不主动征询人**，但**遇到 leakage 嫌疑 / crash 反复 / metric 失效要立即停**（这是 stop conditions，不矛盾）。沙盒不破坏 Karpathy loop — 沙盒是 git branch + TSV 之外的**目录隔离**，加层不冲突。

---

## Mode A vs Mode B (节奏二选一)

🔥 **Karpathy 灵魂不变 (Mode A NEVER STOP), 加 Mode B 防局部最优**:

| 维度 | Mode A (NEVER STOP, 默认) | Mode B (human-rhythm, 触发) |
|---|---|---|
| 默认触发 | 默认走 | 用户喊触发词 |
| 灵魂 | Karpathy 高频试错不打断 | 防局部最优 + human-in-the-loop |
| 跑法 | guess → edit → run → keep/discard 循环不停 | 跑几个 → checkpoint → 列 alternatives → 用户拍 → 继续 / 切方向 |
| stop conditions | leakage / crash / metric 失效 | 同 + checkpoint 到点 |
| 适用 | 第一周冲分 / hyperparam 单变量调参 / 量取胜 | 多 round 跨 agent / 投稿 final / 卡在局部最优感 / 重大方法学改动后 |

**Mode B 触发词**: "human checkpoint / 防局部最优 / 像人一样调 / 慢点跟我对一下 / 别一个人冲 / 切 Mode B / 暂停 autoresearch / 跳出 hill / 换个方向看看".

**Mode B 节奏 (AI 自己 detect, 不等用户每次喊)**:
- 跑了一批实验后 (cluster of runs)
- 连续 keep 多次 (暗示 hill-climbing 同山)
- 新方向起步前 (改 backbone / loss / data 等大变量前)
- metric 大幅变化 (跳涨或断崖)
- 多个 alternative 已死 (跟困局协议互补)
- 用户配置的时间 budget 用完一轮

**Mode B checkpoint 时 AI 必做 5 件事** (详见 [human-checkpoint-protocol.md](human-checkpoint-protocol.md)):
1. 暂停 loop, 报告状态 (近期实验 + 趋势 + 当前最佳)
2. **强制列至少 3 个 alternative directions** (必须真正不同 — 换 backbone/loss/data, 不能换 hyperparam 凑数)
3. ROI 评估每个 alternative (套 cost-benefit-rubric)
4. 给用户决策选项 (继续 / 切 alt / 你给新方向 / 重启 / 暂停)
5. 等用户拍板, 不主动猜

**跟现有规则边界**:
- 跟 Mode A 并列, 不替换. 用户喊才进 Mode B
- 跟困局协议互补: Mode B 是**主动**节拍, 困局是**被动**触发
- 优先级: leakage/crash/metric 失效 > 困局协议 > Mode B checkpoint > Mode A NEVER STOP 默认

---

## 触发执行顺序（每次会话）

```
新接手项目?
├── 是 → Kaggle 4 库扫 1h（kaggle-as-toolbox）
│         + 读 task_plan / INDEX
│         + 嫁接 top kernel 当 baseline
└── 否 → 读 INDEX → 选 1 个 L2_queued

进 Karpathy loop（默认 Mode A 5min/exp）
↓
guess → edit train.py → run → keep/discard → 写 TSV + INDEX 行
↓
卡住? → stuck-protocol（Kaggle / Verifier / academic-search）→ 回 loop
↓
metric "太好" → leakage 7 类检查
↓
重大方法学改动 → 沙盒先行 + 多智能体 round
```

---

## L1→L2→L3 漏斗（evidence trail）

| Level | 含义 | 占比 |
|---|---|---|
| L1 brainstormed | 想到过 | 100% |
| L2 filtered | 值得做 | 5-20% |
| L3 validated | 实验证 | L2 的 30-50% |

详见 `references/evidence-trail.md`。

---

## 性价比 rubric（开做前算）

```
ROI = E[Δscore] × confidence × downstream_unlock / (cost + risk × downside)
ROI ≥ 3 + risk < 30% → L2_queued 做
```

数字校准基于经验启发，不是普适公理。详见 [cost-benefit-rubric.md](cost-benefit-rubric.md)。

---

## 困局协议（卡 ≥ 3 次同类失败 / >4h 无方向）

5 步：自反思 → Verifier → Strategist → academic-search / Kaggle → 综合重挑 L2。
→ [stuck-protocol.md](stuck-protocol.md)

---

## 项目级 wrapper 接入

```yaml
# .claude/skills/<project-name>/SKILL.md
---
name: autoresearch-<project>
description: "通用 DL autoresearch 方法论引擎 + TimesFM 零样本时序预测 + Zarr 大栅格存储 + **探索证据链 L1/L2/L3 三级筛选**（可选，详见 references/evidence-trail.md）。Karpathy autoresearch loop + R7-R11 治理（独立验证/ablation/leakage/per-cell/多智能体）。触发词：autoresearch/自动调研/推进研究/试错/下一步实验/卡在哪、Kaggle 抄作业/特征工程/架构对比/深挖/独立验证、时序预测/TimesFM/零样本预测/FPV/光伏预测/气候时序/能源负荷/time series forecasting、zarr/分块数组/ERA5/CMIP6/大栅格/Dask 并行、探索证据链/L1 L2 L3/筛选漏斗/exploration log/方法学落盘。"
---

# 项目特化（数据路径 / 当前 phase / 推进队列 / 项目级 lessons）
通用方法论一律走全局 skill。
```

例：`autoresearch-pv` 是多站光伏预测项目的 thin wrapper。

---

## References 索引

**灵魂层**
- [trial-and-error-growth.md](trial-and-error-growth.md) — 试错精神 + 成长曲线
- [kaggle-as-toolbox.md](kaggle-as-toolbox.md) — Kaggle 当 4 库用

**执行层**
- [core-loop-karpathy.md](core-loop-karpathy.md) — Karpathy autoresearch loop（DL 通用化）

**治理层**
- [core-methodology.md](core-methodology.md) — 10 条方法论 checklist（详细 protocol 入口）
- [transfer-learning-first.md](transfer-learning-first.md) — 任意模态迁移学习优先
- [independent-verification.md](independent-verification.md) — 不诱导验证模板
- [architecture-ablation.md](architecture-ablation.md) — N-way PK 模板
- [sandbox-protocol.md](sandbox-protocol.md) — 沙盒先行
- [leakage-checklist.md](leakage-checklist.md) — 7 类 leakage
- [per-cell-strategy.md](per-cell-strategy.md) — 多实例 per-cell 配置
- [round-based-exploration.md](round-based-exploration.md) — 多轮深挖
- [multi-agent-protocol.md](multi-agent-protocol.md) — 4 角色协作

**配套工具**
- [evidence-trail.md](evidence-trail.md) — L1→L2→L3 漏斗速查
- [cost-benefit-rubric.md](cost-benefit-rubric.md) — ROI 计算
- [stuck-protocol.md](stuck-protocol.md) — 困局 5 步
- [lessons-learned-meta.md](lessons-learned-meta.md) — 校准直觉的元教训（含"多模型族都失败时自上而下排查"）
- [human-checkpoint-protocol.md](human-checkpoint-protocol.md) — Mode B human-rhythm 节拍 + 防局部最优强制列 alternatives

## 已知 limitation（诚实分级）

- **泛化范围**：本 skill 在窄 benchmark loop（single-metric / single-file / fixed budget）泛化最强；复杂任务（多 metric / 多 cell / 长训练 / 多模态）需配合治理层裁剪
- **数字（ROI 表 / 校准系数）**：经验启发，不是普适公理
- **多智能体**：在 quota 充裕时最优，单 Claude 时降级为 single-agent loop
- **常见 DL 议题**（seed / HPO / augmentation / NaN / training stability）：本 skill 暂未覆盖深度，参考社区 best practice + Kaggle discussion
