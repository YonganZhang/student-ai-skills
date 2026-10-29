# 试错与成长 — autoresearch 灵魂

## 核心论点
autoresearch 不是"一次想清楚就跑对"，而是 **fail fast → keep what works → compound over time**。这就是 Karpathy 原版要求 NEVER STOP / 每 5 分钟一次实验的根本原因 — **growth comes from volume of attempts, not depth of pre-thinking**。

> "If they work, keep. If they don't, discard. And you're advancing the branch so that you can iterate." — Karpathy, autoresearch program.md

## 核心循环（一切起点）

```
guess → test → measure → keep/discard → guess again
```

**guess 不需要正确**，只需要 cheap to test。一晚跑 100 个实验，10 个 keep = 成功。这跟"先想透再动手"是相反方向。

## 试错的 3 种 mode

### Mode A: 高频小步（默认）
- 每实验 5-15 min（参 core-loop-karpathy.md）
- 改动 ≤ 1 个变量
- keep/discard 立即决定
- **量取胜**：100 次小实验 > 10 次大改

### Mode B: 中频中步（卡了切这个）
- 每实验 30-60 min
- 改动 1-2 个相关变量
- 过夜跑 20-30 个
- 切换到 Mode A 没新方向 / 直觉用尽时

### Mode C: 低频大步（破局用）
- 每实验数小时-1 天
- 改架构 / 数据源 / loss 等大变量
- 跑前必走 stuck-protocol 5 步
- 一周 < 5 个

**默认从 A 开始，卡住升 B，破局升 C，破局完降回 A**。

## 成长曲线（Growth = log(experiments))

- 前 10 个实验：定 baseline 找方向
- 10-50：靠"猜测 → 实验"快速排除掉低 ROI 方向
- 50-200：进入 plateau，需要外部输入（论文 / Kaggle / Verifier）
- 200+：每 +10 实验涨 0.001 量级

**plateau 应对**：不要硬猛刷，启动 stuck-protocol，找 Kaggle/papers，再回 Mode A。

## 跟"防 leakage / 谨慎"的矛盾解决

试错主张 fast，治理层主张 careful — **两者不冲突，分场景用**：

| 场景 | 试错快 vs 治理慎 |
|---|---|
| 改 hyperparam / 小特征 / 单文件 | 快（Karpathy 原版）|
| 改 data loader / split / metric | 慎（leakage 高发） |
| 涨幅"太好" | 慎（leakage 默认怀疑）|
| 第一次接入新数据集 | 慎（先 EDA / sanity）|
| 已稳定 baseline 上 sweep | 快 |
| 上线 / 论文 final | 慎 |

**铁律**：试错快但记 evidence；治理慎但不要把 careful 当作"不动手"的借口。

## 反成长的反模式

- 🔴 想 30 分钟才动手 → 不如直接试 6 个 idea
- 🔴 失败一次就 reflective 半小时 → 直接讨厌 reset 跑下一个
- 🔴 keep 后就停下"庆祝/总结" → autoresearch NEVER STOP，写进 results.tsv 就 next
- 🔴 觉得"这 idea 太蠢不试" → 蠢 idea 实际成本只 5min，值得试
- 🔴 不写 results.tsv → 同方向 3 周后又试一遍

## 试错的 evidence 沉淀

每次 keep / discard / crash 都写：
- INDEX.md 加 1 行 L3
- results.tsv 加 1 行
- discard 必写 1 句"为啥失败 + 下一步衍生"

不写 = 没成长。下次同方向你（或下一个 session 的你）会重蹈覆辙。

## 怎么"想得更猛"（Karpathy "think harder"）

当 results.tsv 满 50 行没新 keep：
1. 看哪些 keep 是接近的，**combine** 它们
2. 看哪些 discard 是相邻的，**radical 反方向**（如全 LR 都跌 → 试 LR ×100）
3. 读 Kaggle top notebook（见 [kaggle-as-toolbox.md](kaggle-as-toolbox.md)）
4. 用 学术检索技能 `share-nature-academic-search`（可选，本包未包含） / 官方 API 找 SOTA
5. 改 metric 看 train_loss / generalization gap，找新 angle
6. 试一个看似 unrelated 的方向（intuition pump）

## 关键 mindset

- **失败是 evidence**，不是浪费
- **猜错很 OK**，猜对反而可疑（要查 leakage）
- **成长 = 累积 keep + 累积失败 lesson**
- **Never ask "should I continue?"** — Karpathy 原话，autonomous 就是不停

## 实战 ROI

| 1 晚（8h） | 实验数 | 预期 keep | 预期成长 |
|---|---|---|---|
| Mode A 5min | ~100 | 5-15 | +0.005~0.02 |
| Mode B 30min | ~16 | 2-5 | +0.005~0.015 |
| Mode C 2h | ~4 | 0-2 | -0.01~+0.05 |

**新手默认 Mode A**：量大、回退便宜、防过度工程。
