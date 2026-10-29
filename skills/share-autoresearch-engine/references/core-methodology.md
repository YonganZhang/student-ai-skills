# 核心 10 条方法论 — 详细 Checklist

> SKILL.md 主文件已列 10 条概要；本文档是每条的"开干前 checklist + 反模式速查"。

## 1. 独立验证不诱导

**checklist**:
- [ ] Verifier prompt **不含** Claude/Gemini 已写的结论文档
- [ ] 给 Verifier 原始数据 + 当前 score，不给猜想
- [ ] 输出格式：claim by claim 标"一致 / 部分 / 不一致"
- [ ] 对比时不删 Verifier 反对意见

**反模式**: "Codex 你看下我们的 finding 对不对"（已诱导）

→ [independent-verification.md](independent-verification.md)

---

## 2. 架构 ablation 4-way PK

**checklist**:
- [ ] A=baseline / B=最简变种 / C=global stacked / D=cluster
- [ ] 同 split / 同特征 / 同评测口径
- [ ] per-cell 看哪种最优（不只看 overall avg）
- [ ] 沙盒目录跑，不动主 pipeline

**反模式**: 只跑 A vs B，跳过 C/D；用不同特征跑等于无 ablation

→ [architecture-ablation.md](architecture-ablation.md)

---

## 3. 迁移学习优先

**checklist**:
- [ ] 先 timm/transformers 找通用 backbone
- [ ] frozen + PCA 128/256 + 下游 head
- [ ] 数据 < 100k → frozen，> 1M → fine-tune
- [ ] image 上采样到 backbone 期望的 224×224

**反模式**: "domain 太特殊通用模型不行" → 先试再说

→ [transfer-learning-first.md](transfer-learning-first.md)

---

## 4. 沙盒先行

**checklist**:
- [ ] 新建 `<exp_dir>/exp_<round>_<topic>/`
- [ ] 数据用 `frozen_splits_v2/` 与 v1 并存
- [ ] 跑通有数字 + 跨 metric 一致 + 7 类 leakage 检完才升级
- [ ] 用户 review 通过才合主 pipeline

**反模式**: 直接改主 pipeline；沙盒跑通就喊"完成"无 leakage check

→ [sandbox-protocol.md](sandbox-protocol.md)

---

## 5. Apple-to-apple 对照

**checklist**:
- [ ] 同 split（train/val/test 完全一致）
- [ ] 同特征集（差异部分单独标）
- [ ] 同评测口径（cap / month aggregation / metric）
- [ ] 同架构对比（不要把 LGB single 跟 ENS+autoresearch 混比）

**反模式**: 用 v1 ENS+AR 的 0.93 跟 v2 bare LGB 的 0.90 比 → 实际是 ensemble 没跑

---

## 6. 机制 vs 现象分离

**checklist**:
- [ ] 数字标 ✅（实测 reproducible）
- [ ] 机制标 💭（猜测，待证伪）
- [ ] 论文 method 章节只用 ✅；机制走 discussion
- [ ] reviewer 反问机制 → 回 falsification 实验或承认未证

**反模式**: "phantom 是 SCADA 偏置" 当结论 → 论文被击垮

---

## 7. Leakage 警觉

**checklist**:
- [ ] 涨 > 0.03 + 跨 horizon 一致 → 默认怀疑
- [ ] 跑 shuffled val sanity check
- [ ] 7 类 leakage 全过
- [ ] target shift 方向 / scaler train-only / NWP issue_time / merge_asof tolerance

**反模式**: AR +0.04 不查 leakage 直接上 production

→ [leakage-checklist.md](leakage-checklist.md)

---

## 8. 多 round 累积深挖

**checklist**:
- [ ] 每 round 3 路 agent 互补不重叠
- [ ] raw report 归档 `raw-llm-reports/<date>-<agent>-round<N>.md`
- [ ] master list / INDEX 加新 finding
- [ ] 每 round 至少 1 个红色发现 / 红色 falsification

**反模式**: 每 round 都查 EDA；3 agent 跑同类任务

→ [round-based-exploration.md](round-based-exploration.md)

---

## 9. Per-cell 思维

**checklist**:
- [ ] 列 cell 表（数据集 × horizon × station × ...）
- [ ] cell 数 ≥ 5 + 物理差异大 → 必跑 4-way PK
- [ ] 每 cell 可独立选特征 / 超参 / 训练数据 / 后处理
- [ ] 输出 hybrid 配置矩阵

**反模式**: 默认 1 模型包打 ride 到底

→ [per-cell-strategy.md](per-cell-strategy.md)

---

## 10. 诚实分级标注

**checklist**:
- [ ] ✅ 实测（reproducible）
- [ ] 🟡 估计（标 ±50% 误差区间）
- [ ] ⚠️ leaky / oracle（明确"非 deployable"）
- [ ] 💭 机制猜测（标"待证伪"）
- [ ] 论文 / 报告 / INDEX / master list 一致用此 4 级

**反模式**: "实际 +0.04" 不标其实是 leaky → 论文 reviewer 击垮

---

## 一行决策树

```
新方向 → INDEX 加 L1 行
→ rubric 估 ROI → ROI ≥ 3 升 L2_queued
→ 沙盒新建 exp_<round>_<topic>/
→ 跑实验 → 7 类 leakage 检 → 跨 horizon 一致检
→ 标可信度 → 升 L3_validated_keep / reject
→ 写 lesson + 衍生
→ 校准下次 confidence
```
