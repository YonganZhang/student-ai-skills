AppliesTo: claude
# 科研 autoresearch 探索证据链 (Evidence Trail)

## 适用场景
research-mode 项目（manifest=research），特别涉及 autoresearch / Kaggle / 数据科学探索 / 论文写作的工作。

## 核心原则
**任何方法学层面的改动 + 任何"曾经想过但否定"的方向，都必须落盘到 evidence trail**——不只为续命，更为将来写论文时能溯源。

> 为什么：写论文时要能讲清完整的探索漏斗——探索过多少方向、凭什么否定、凭什么留下、最后怎么选出方法；否定的方向不落盘，这条漏斗就讲不出来。

## 哪些算"方法学改动"（必须落盘）
- 数据预处理：清洗 / 去噪 / 归一化 / resampling / gap 处理
- 特征工程：构造 / 选择 / 编码 / 衍生 / 交互项
- 模型架构：选型 / 改动 / 组合 / 集成
- 调参：超参搜索方向 / 范围 / 策略
- 训练流程：loss / early stop / data augmentation / scheduler
- 评测：metric / val 切分 / 聚合 / 显著性
- 跨数据集 transfer 决策

## 三级筛选阶梯（论文 evidence chain 的本质）

科研发现的本质是从大量候选中筛出少数赢家。**正反两面都要留痕**：

| Level | 含义 | 典型占比 |
|---|---|---|
| **L1 brainstormed** | 任何来源（Kaggle / 论文 / EDA / 物理直觉 / 用户提议）"想到过"的方向 | 100% |
| **L2 filtered** | 凭领域知识/ROI/可行性判断"值得尝试"的子集 | 5~20% |
| **L3 validated** | 实际跑实验且通过显著性验证的赢家 | L2 的 30~50% |

最终 method = L3 + 必要 L2 解释。论文叙述 = "考察 N 条 → 过滤到 M → 实验 K → 留下 P"。

## 落盘约定（项目内）

```
wiki-methodology/
├── wiki/methods/explorations/
│   ├── INDEX.md                    ← 主表（强制，一行一条 entry）
│   └── NNN-<slug>.md               ← 每条探索详细文件（重要的开，简单的省略）
├── top/decisions/                   ← 重大方法学决策（ADR 风格）
└── top/findings/                    ← 阶段性总结（已有）
```

## INDEX.md 强制字段

| ID | 主题 | 数据集 | horizon | 来源 | status | 预期 Δ | 实际 Δ | verdict | 详细 |

**status 取值**：
- `L1_brainstormed` — 想到过，未筛选
- `L2_deferred_intuition` — 直觉否定（必须写 reason）
- `L2_deferred_dependency` — 等前置完成
- `L2_queued` — 已入实验队列
- `L3_running` — 实验中
- `L3_validated_keep` — 已验证并采用 ✅
- `L3_validated_reject` — 已验证但放弃 ❌
- `L3_inconclusive` — 跑完结果模糊（需要更多样本/CI）

## 单条 entry 模板（开 NNN-slug.md 时用）

```
# NNN: <主题>

status: L?_xxx | created: YYYY-MM-DD | updated: YYYY-MM-DD

## Hypothesis
<一句话说做什么、预期什么>

## Motivation
<为啥想到：Kaggle 链接 / 论文 / EDA 数字 / 物理直觉 / 用户提议>

## Source
<具体出处链接>

## Cost
<工作量估计>

## Predicted impact
<预期收益+证据>

## Implementation
<代码 path / commit hash>

## Result
<具体数字 / before-after / pre-rejected by intuition>

## Verdict + Reason
<KEEP / REJECT / DEFER + 详细原因>

## Sub-explorations triggered
<衍生 ID 列表>
```

## 触发时机（强制）
1. **用户/Claude 提出新方向** → INDEX.md 加 L1 行（即使 30 秒后就 L2 否定也要加）
2. **决定开做某事前** → 升 L2_queued + 详细 entry 文件
3. **实验完成** → 升 L3 + 填 result（成功失败都填）
4. **直觉否定某方向** → L2_deferred_intuition + 写 reason 到 INDEX
5. **阶段性回顾** → top/findings/ 写总结，引用 INDEX

## 论文 evidence chain（最终目的）

写 paper method 章节时按漏斗叙述：
- "我们考察了 N 条方向（Kaggle/论文/物理直觉/EDA）"
- "基于 X/Y/Z 标准过滤到 M 条值得实验"
- "跑了 K 个实验，P 条通过显著性检验"
- "最终 method = 这 P 条的组合 + 关键 L2 解释"

每条都能溯源到具体 INDEX 行 / entry 文件。

## 反例（违反这条规则就记下来引以为戒）
- 🔴 跑实验但只口头说"loss 升了→改回去"：未来无法溯源
- 🔴 直觉否定方向但只在脑子里想：下次提议又重头想一遍
- 🔴 INDEX.md 不维护：变成 entry 文件目录树，无法回答"目前总进度"
- 🔴 实验日志写在 commit message 里：commit 散落，无法横向对比

## Why
- 跨会话续命：智能体换会话/换 instance 后能秒进入状态
- 论文 evidence：投稿/答辩需要"我们考察过 N 个方向"的可追溯证据
- 防遗忘：科研做久了同一个直觉否定可能反复发生，落盘避免重蹈
- 团队协作：导师/合作者能快速看到决策树
