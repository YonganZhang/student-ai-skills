# AI 检查提示词

五个模板对应五类高风险动作。复制后填上下文，不要直接原样丢给模型。

| 模板 | 什么时候用 | 输出 |
|---|---|---|
| [scout.md](scout.md) | 找 idea、找水下问题、比赛方案复盘 | 5 个候选 + 1 个推荐 + 3 个检查 |
| [red-team.md](red-team.md) | 结果看起来太好/太差、要写结论前 | P0/P1/P2 + 反例 |
| [training-review.md](training-review.md) | 曲线异常、loss 不降、梯度/AMP/优化器可疑 | 口径/探针/P0-P2 |
| [pre-freeze.md](pre-freeze.md) | 冻结模型、跑最终 test 前 | release/hold + 缺项 |
| [postmortem.md](postmortem.md) | 负结果、事故、复现失败 | 实现失败/方向失败 + 回归 |

使用规则：

- 审查者只读；作者负责修改。
- 每条 finding 必须有文件/行/数字；没有证据降为 P2。
- 审查范围只给相关文件，不给全仓库；一次只问 3–5 个问题。
- 同一模型/同一上下文不自审；至少换一个上下文或提供方。
- 审查通过不等于科学结论；测试和证据才是判据。
- 外部 wrapper 要求 `COMPLETION_STATUS`；审查结论另用 `verdict`，不要把“完成”当成“通过”。
