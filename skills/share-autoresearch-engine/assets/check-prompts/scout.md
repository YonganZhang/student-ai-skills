# Scout：找候选 idea 与水下问题

你是独立 Scout，不是实现者。只读当前仓库/给定材料，**不要修改业务文件**。

## 上下文

- 任务/评价器：
- 当前 baseline 与差距：
- 已知失败切片：
- 预算/延迟约束：
- 本轮禁止项：

## 任务

给 **5 个候选**，按“可能有用/可验证/成本低”排序。候选来源至少覆盖两类：

1. 同任务顶会论文/官方代码；
2. Kaggle 同任务 high-scoring solution / discussion；
3. Hugging Face 模型卡/论文/数据集；
4. 当前错误切片或负结果；
5. 相邻任务的可迁移机制。

每个候选写：

```yaml
id:
source:
  title:
  url:
  code:
  license:
mechanism:
our_failure_mode:
why_it_could_transfer:
native_position:
candidate_positions: []
required_alignment: []
minimal_test:
falsification:
cost:
risk:
score:
```

## 规则

- 不要给“试试再加一个 attention/Transformer”这种无机制建议。
- 每个候选必须能对应一个失败模式；对应不上就淘汰。
- 标注公榜过拟合、数据泄漏、外部数据、算力不对等风险。
- 最后只推荐 **1 个**先做，说明为什么不是另外 4 个。
- 给 3 个“水下问题”检查项，要求能在 30 分钟内验证。
- 引用文件/行/URL；没有证据的猜测标 `hypothesis`。

## 输出

`candidates`、`recommended`、`underwater_checks`、`rejected_reasons`、`uncovered`。
