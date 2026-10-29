# 基础模型矩阵、排行榜与冠军移交

用于模型家族选型：已经真正测过哪些模型、哪些结果可以同榜、下一批应该测哪些模型。明确组件假设可直接进入[组件工作流](component-integration.md)，无需为得到“稳定冠军”反复跑基线；其结果只按局部比较的证据等级报告。

## 1. 先按证据等级盘点，不先数文件

同一个模型可能只有 import/smoke，也可能完成多折多 seed；配置变体也不等于新模型家族。逐 lane 登记以下等级：

| evidence_tier | 含义 | 能否进入正式排名 |
|---|---|---|
| `confirmed_rank` | 完整 development protocol、规定重复、独立复算 | 可以，作为稳定冠军证据 |
| `screen_rank` | 同 split/metric/预算的 family screen | 只能形成筛选榜，不能冒充稳定冠军 |
| `effect_only` | 与强基线做过局部或机制对照，但协议不同/控制不全 | 不能与主榜混排 |
| `contract_smoke` | 只证明能加载、前向或接线 | 不能报告性能排名 |
| `not_rankable` | 真运行过但完成率、失败或协议不足 | 保留结果，不分配正式 rank |
| `blocked` | 数据、标签、split 或依赖未满足，未执行 | 不得算“已测试模型” |

回答“测了多少模型”时至少同时给三个数：注册候选数、进入同口径矩阵数、取得正式排名数。配置 trial、seed、fold 和模型家族分开计数。

## 2. 先划 lane，再排模型

只有同时共享以下条件的候选才能处于同一 lane：任务/标签空间、输入模态、split、主指标与方向、训练预算级别、数据可见边界。不同数据集、目标、模态或 full-budget/screen 不能用一个总 rank 混排。

跨 lane 和跨场景只汇总：相对 incumbent 的归一化改善、重复通过率、实际改善达标率、失败率与 BETU；禁止把 mIoU、F1、RMSE、MAE 的原始数值互相排名。

## 3. 选择基础模型家族

每个 family screen 通常选择 3–5 个有意义家族，不用模型数量制造完整感：

1. 当前可信 incumbent 或最简单统计基线；
2. 一个强经典/树/地质统计基线；
3. 一个主流深度网络，归纳偏置与数据结构相符；
4. 有真实权重和合法接口时，加入预训练/基础模型；
5. 只有任务需要时，加入领域专用架构。

候选必须写清 `model_id`、family、代码/权重来源、为何适合该数据、推理时需要的输入以及预算。不要用“最新”“更大”“论文说有效”代替适配理由。优先复用可信 pipeline，只交换模型定义。

## 4. 家族选型的四段顺序（明确组件任务可直接走组件分支）

1. **Family screen**：同 lane、同预算筛 3–5 个家族。
2. **Champion confirmation**：前 1–2 名按完整 fold/seed 重跑，确认稳定冠军。
3. **Adjacent innovation**：只在冠军上改变 1–2 个设计原语；按[组件工作流](component-integration.md)做放置、接线、探针和单变量消融。
4. **Independent promotion**：从原始预测重算，过门才更新 incumbent。

基础模型矩阵未完成时，不把组件缝合结果称作“最好模型”；family screen 与 confirmation 不共用一个 rank。

## 5. 结构化清单

从 `assets/model-matrix.template.json` 复制项目清单。每个 lane 至少登记：

- `lane_id`、任务、主指标方向；
- split 单位、数量与状态；
-当前 incumbent；
- historical candidates 及 evidence tier；
- planned candidates、family、role、执行状态和适配理由；
-同 lane 预算与下一步动作。

运行：

```bash
python3 ~/.claude/skills/share-autoresearch-engine/scripts/validate_model_matrix.py <matrix.json>
python3 ~/.claude/skills/share-autoresearch-engine/scripts/render_model_matrix.py <matrix.json> --output <report.md>
```

校验器拒绝占位符、NaN/Inf、重复 ID、跨 lane 原始分数总排名、把 smoke/blocked 项标成正式 rank，以及 family screen 少于三个模型家族。

## 6. 人类可读输出

报告固定回答：

1. 每个 lane 注册/已运行/可排名/已确认各多少模型；
2. 当前排名与指标，明确哪些结果不可比较；
3. 当前 incumbent 的证据等级；
4. 下一批精确模型名单和先后顺序；
5. 下一步是家族确认还是明确假设的组件实验。

“没有稳定冠军”是合法结论；blocked 候选不算失败模型，未晋级路线不等于赛道失败。
