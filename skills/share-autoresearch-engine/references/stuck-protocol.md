# 困局求助 5 步协议

## 触发条件（任一即可）
- 同类问题 ≥ 3 次 L3_validated_reject
- 单次实验跑 > 4 h 仍无方向
- baseline 1 周不动
- 直觉说"应该有效"但实测 N 次都失败
- 用户问"你卡在哪里 / 还有啥招"

## 5 步协议

### 1. 自反思（5 min）
- 在 INDEX.md 写一行 hypothesis：是不是 root cause 诊断错了？
- 列已尝试方向 + 各自失败原因
- 问自己：是**特征不够 / 模型不行 / 数据有问题 / 评测错位**？

### 2. Verifier 第一次（不诱导独立验证）
- 派一个隔离子智能体独立 review 当前 hypothesis；只有用户点名跨模型时才走外部 CLI
- **不喂结论**，只给"原始数据 + 当前 score"，让它自己跑代码下结论
- 重点问"你觉得 root cause 是什么"

### 3. Strategist 第二次（外部知识）
- 派另一隔离子智能体结合 WebSearch / academic-search 找类似问题的解法；需要跨模型 Strategist 时按 外援审查技能（可选，本包未包含；公开版见 https://github.com/YonganZhang/external-review-skill ） 调 Gemini
- WebSearch + Kaggle CLI / Kaggle 网页找 starter notebook
- "这类问题 Kaggle / 论文里别人怎么解"

### 4. academic-search 第三次（前人 SOTA）
- 用 学术检索技能 `share-nature-academic-search`（可选，本包未包含） / 官方论文 API / WebSearch 找原论文和 SOTA 方法
- 读 method 章节看是否提到 trick

### 5. 综合 → 重新挑 L2
- 把三方意见列在 INDEX 一行
- 从所有 L1 候选里重挑最强方向（可能是之前忽略的）
- 升 L2_queued + 写明"这次为什么会有效"

## 反模式

- 🔴 卡住后**继续猛跑**同类实验 → 第 4 次仍 reject
- 🔴 求助前不写当前 hypothesis → Verifier 没法独立验证
- 🔴 给 Verifier 喂 Claude 的结论 → 一致性偏差，验证失效
- 🔴 三步只走一步（"Codex 说不行就放弃"）→ 各 LLM 角色不同
- 🔴 综合后**再挑同方向**（换皮不换里）→ 死循环

## 实战例（多站光伏预测项目 R10-R11 转向）

R10 baseline 国网 4h 卡 0.8999 一周不动：
1. 自反思：是不是"1 模型包打"假设错了？
2. Verifier (Codex)：跑独立 8 站 LGB → 各站独立 +0.10
3. Strategist (Gemini)：建议 cluster + per-station custom features
4. academic-search：找到 8 站独立训练在 multi-site PV forecasting 是常态
5. 综合 → L2_queued: P10 8 站独立架构 → 实测 +0.103 暴胜

**关键**：用户最初的"1 个模型怎么可能包打"质疑就是触发器。

## 触发示例

| 情境 | 走哪步 |
|---|---|
| 加了 5 个特征都 -0.001 | 步 2-3（root cause 是 mult-collinear？特征类型错？）|
| autoresearch 跑 1000 轮不涨 | 步 4（前人怎么调？是不是模型容量上限？）|
| Domain model from-scratch 不收敛 | 步 4 → 步 3（试 pretrained-first）|
| baseline 1 周不动且无新方向 | 五步全走 |
