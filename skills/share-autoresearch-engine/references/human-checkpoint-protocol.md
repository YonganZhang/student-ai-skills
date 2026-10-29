# Mode B human-checkpoint protocol — 防局部最优

> 跟 Mode A (Karpathy NEVER STOP) 并列共存, 不破坏现有灵魂
> 解决: NEVER STOP 高频试错容易陷入局部最优, 用户希望"像人一样调"

---

## 真根因

Mode A (NEVER STOP) 是 Karpathy 灵魂 — 高频试错不被打断. 但**长 loop 跑下来 AI 容易在当前 baseline 周围微调, 陷入 hill-climbing 局部最优**:
- 连续 keep 几次 → 当前 hill 上爬得更高 → 视野更窄
- 没机会跳到别的 hill 看
- AI 单靠自审难以 detect "在局部最优", 因为局部最优特征就是"所有近邻都更差"

目标：**像人一样调节**——隔一段停下来看全局、主动列出别的方向，而不是让 AI 在当前 baseline 附近自动微调、陷入局部最优。

**Mode B 不是覆盖 Mode A, 是并列模式**. 用户场景化选择.

---

## Mode A vs Mode B 对比

| 维度 | Mode A (NEVER STOP, 默认) | Mode B (human-rhythm, 触发) |
|---|---|---|
| 默认触发 | 默认走 | 用户喊触发词 |
| 灵魂 | Karpathy 高频试错 | 防局部最优 + human-in-the-loop |
| 跑法 | guess → edit → run → keep/discard 循环不停 | 跑几个 → checkpoint → 列 alternatives → 用户拍 → 继续/切方向 |
| stop conditions | leakage / crash / metric 失效 | 同 + checkpoint 到点 |
| 适用 | 第一周冲分 / hyperparam 单变量调参 / 量取胜 | 多 round 跨 agent / 投稿 final / 卡在局部最优感 / 重大方法学改动后 |
| 节奏 | 一气跑 | 节拍式 (跑几个 - 停 - 报告 - 用户决) |

---

## Mode B 触发词 (用户喊)

- "human checkpoint / 加 checkpoint / 像人一样调 / 慢点 / 我要看着改 / 别一个人冲"
- "防局部最优 / 跳出 hill / 换个方向看看 / 不要只在这条线上调"
- "暂停 autoresearch / 暂停 loop / 别 NEVER STOP 了"
- "Mode B / 切 Mode B / 节拍跑"

或者 Mode A 跑一段后用户突然喊 "暂停" → 自动切 Mode B 起 checkpoint.

---

## Mode B 节奏 — 啥时候触发 checkpoint

满足任一即 checkpoint (AI 自己 detect, 不等用户喊):

1. **跑了一批实验后** — cluster of runs 完成 (几个 candidate 已 keep/discard 一波)
2. **连续 keep 多次** — 暗示可能在 hill-climbing 同一座山 (≥ 几次连续 keep + 都是 hyperparam 微调)
3. **新方向起步前** — 准备改 backbone / loss / data 等大变量前
4. **metric 大幅变化** — 跳涨或断崖, 不管好坏都该 checkpoint
5. **多个 alternative 已死** — 当前方向多次失败时 (跟困局协议 5 步对应)
6. **时间到** — 用户配置的时间 budget 用完一轮

---

## Mode B checkpoint 时 AI 必做 5 件事

### 1. 暂停 loop, 报告状态

```markdown
🛑 Mode B checkpoint
近期 N 个实验:
  - exp_001: <change> → <metric> → keep
  - exp_002: <change> → <metric> → discard (原因)
  - ...

趋势: <metric 在升 / 稳 / 跌 / 震荡>
当前最佳: <候选 ID + metric>
```

### 2. 强制列至少 3 个 alternative directions

**这是防局部最优核心机制**. AI 即使觉得当前方向好,也要列至少 3 个 alternatives:

```markdown
## 如果换方向, 候选:

### Alt A: <换什么大变量>
- 思路: ...
- 改动幅度: <小/中/大>
- 预估 ROI: <按 cost-benefit-rubric>
- 风险: ...

### Alt B: <另一个完全不同方向>
...

### Alt C: <第三个>
...
```

**硬约束**:
- alternatives 必须真正不同 — 不能换 hyperparam, 必须**换 backbone / loss / data setting / metric formulation / problem framing 等大变量**
- 不能用"小调"凑数 (例:lr 从 1e-3 到 5e-4 不算 alternative)
- 至少含一个"反直觉"方向 (强迫 AI 跳出当前局部)

### 3. ROI 评估每个 alternative

调用 cost-benefit-rubric.md, 给每个 alt 算 ROI = E[Δscore] × confidence × downstream_unlock / (cost + risk × downside).

### 4. 给用户决策选项

```markdown
## 用户决策

(a) 继续当前方向 (跑 N 个再 checkpoint)
(b) 切到 Alt A / B / C 之一
(c) 你给新方向 (你说我跑)
(d) 我看走偏了 — 重启 (回某个 commit / 换 baseline)
(e) 暂停 autoresearch (停下来你想想)
```

### 5. 等用户拍板, 然后切回 Mode A 或继续 Mode B

不主动猜用户选什么. 等明确回复.

---

## Mode B 跟现有规则的边界

| 现有规则 | 跟 Mode B 关系 |
|---|---|
| Mode A NEVER STOP | 并列, 不替换. 用户喊才进 Mode B |
| 困局协议 (卡 ≥ 3 次同类失败 / >4h 无方向) | Mode B checkpoint 是**主动**节拍, 困局协议是**被动**触发. 互补不冲突 |
| 执行层 vs 治理层边界表 | Mode B 主要走治理层节拍, 但执行层 single-file 跑法不变 |
| 多智能体协作矩阵 | Mode B checkpoint 可以触发多智能体复审 (Verifier / Strategist) 列 alternatives |
| L1→L2→L3 evidence trail | Mode B alternatives 必须落 L2_queued, 用户选的进 L3_validated |
| ROI rubric (ROI ≥ 3 + risk < 30%) | Mode B 评估 alternatives 时强制套这个 rubric |
| 诚实分级 | Mode B 报告趋势时强制 honest assessment (不粉饰当前最佳) |

---

## 实操示例

### 场景: 用户切 Mode B 跑光伏预测项目

用户: "切 Mode B, 我看你这两小时一直在调 lr 没换方向, 我怕走偏了"

AI 行为:
1. 暂停当前 Karpathy loop
2. 报告近期 7 个实验 (5 个 lr 微调 + 2 个 weight decay 微调, 4 keep 3 discard, metric 涨 0.3 → 0.34)
3. **强制列 3 alternatives**:
   - **Alt A**: 换 backbone — Transformer → 当前是 LSTM
   - **Alt B**: 换 loss — quantile loss → 当前是 MSE
   - **Alt C**: 加物理先验 — 嵌太阳辐照度 PDE constraint
4. ROI 评估 (per cost-benefit-rubric): Alt A ROI=4.2, Alt B=3.1, Alt C=5.5 但 risk 高
5. 给用户决策选项 (a-e)

用户选 Alt C → AI 切回 Mode A 跑 Alt C 方向. 跑几个后再 checkpoint.

### 场景: 多 round 投稿 final

Mode A 跑了一周冲分到 0.42. 切 Mode B 准备投稿前 final round.

AI 行为:
1. checkpoint 报告: "已 plateau 3 天, 最近 keep 比率 < 20%, 暗示 hill 顶"
2. 列 alternatives: 换 evaluation protocol / 加 ablation 强化 / 切到更难数据集
3. ROI: Alt B (加 ablation) 高 — 投稿需要
4. 用户拍 Alt B → 治理层走

---

## 反例 (Mode B 写错的样子)

🔴 checkpoint 时 AI 只报 "当前 metric 0.42 不错, 继续? (y/n)" — 没强制列 alternatives
🔴 alternatives 都是 lr / batch_size / weight_decay 这种小调 — 不是真 alternative
🔴 AI 自己挑 alt 不问用户 — 违反 human-in-the-loop 灵魂
🔴 用户没喊 checkpoint, AI 自己 trigger checkpoint 中断 Mode A — 不是 Mode A bug, 是设计冲突

---

## 跟 Karpathy 灵魂的关系

Mode A NEVER STOP **不变**, **不删**, **不弱化**. Karpathy 灵魂是"高频试错量取胜", 这是 Mode B 跑完 checkpoint 用户拍板"继续当前方向"时回归的状态.

Mode B 是**节拍 wrapper**, 不是替代. 类比: Mode A 是冲刺, Mode B 是冲刺之间的换气. 短跑选手不能光冲不换气, 长跑选手不能不冲只换气.

---

## 触发优先级 (跟其他 protocol 同时满足时)

1. **leakage / crash / metric 失效** → 立即停 (执行层 stop conditions, 最高)
2. **困局协议** (卡 ≥ 3 次同类失败 / >4h 无方向) → 走 5 步重挑
3. **Mode B checkpoint** (节拍到 / 用户喊) → 暂停 + 列 alternatives + 用户拍
4. **Mode A NEVER STOP** (默认背景) → 不被打断, 除非上面 3 个触发
