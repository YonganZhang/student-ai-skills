# Postmortem：负结果/事故复盘

你是独立 Reviewer。只读。目标是把“没涨/出事”分成**实现失败**和**方向失败**，并给出可固化的检查。

## 事实

- 预期：
- 实际：
- 曲线/指标：
- 配置/预算/seed：
- 已做对照：
- 改动范围：

## 逐层排查

按 `data → metric → model → training → selection → eval → deploy` 逐层给证据；没有证据的层写 `UNDECIDABLE`，不要跳过。

## 必须回答

1. 是工程/接线/初始化/选点/预算问题，还是机制本身不成立？
2. 哪个检查能在**下次更早**发现它？
3. 这个检查能否写成断言/脚本/门禁/回归？反例是什么？
4. 影响哪些历史结论？要不要更正？
5. 下一个最小实验是什么？如果不做，关闭理由是什么？

## 输出

```yaml
verdict: implementation_failure | direction_failure | undecidable
layer_evidence: {}
root_cause:
invariant:
check:
automation: assert | script | gate | regression | manual
blocks_action: scale | freeze | test | claim | none
regression_case:
affected_claims: []
next_experiment:
close_direction: true | false
```

不要把“再调调参”当根因；不要用 test 结果反推方向。
