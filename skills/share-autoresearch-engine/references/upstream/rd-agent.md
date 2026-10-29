# 上游卡片：RD-Agent

## 链接与许可证

- 仓库：<https://github.com/microsoft/RD-Agent>
- 许可证：MIT（Microsoft Corporation）。本地没有逐字复制的代码；按思路改写的地方在代码注释里署名（见下表最后一行）。

## 吸收的版本

- commit `484776c211e4fbbeef03e0ec00d6bbee7362a4f4`（2026-09-23），吸收日 2026-10-22。行号对应此 commit。

## 拿了什么

| 上游位置 | 内容 | 状态 |
|---|---|---|
| `rdagent/core/proposal.py:24-320`（`Hypothesis`、`ExperimentFeedback`、`HypothesisFeedback`、`Trace`） | 假设字段（理由、预期、组件）、反馈字段（是否替换最优、理由、观察）、假设 DAG | 已实现（`assets/hypothesis-trace.schema.json`：字段改写，`parents` 构成 DAG，`description` 署名）；已写进文档（`references/multi-agent-protocol.md`"台账"条） |
| `rdagent/scenarios/data_science/proposal/exp_gen/proposal.py:98-275` | 从轨迹提炼"挑战"（最多五条、少而精）；假设按 alignment / impact / novelty / feasibility / risk_reward_balance 五项打分 | 已实现（`assets/hypothesis-trace.schema.json`:`scores` 五项）；已写进文档（`references/multi-agent-protocol.md`"提案格式"条：不超过 5 个挑战、五项打分） |
| `rdagent/scenarios/data_science/proposal/exp_gen/prompts_v2.yaml:302-364`（`hypothesis_critique`，关键句在 320、332） | 区分实现失败（值得改进后重试）与方向失败（多次尝试因本质不适合而失败） | 已写进文档（`references/triage/README.md`"把排查变成门禁"、`references/multi-agent-protocol.md`"裁决分两类"）；`assets/hypothesis-trace.schema.json` 的 `verdict` 含 `implementation_failure` |
| `rdagent/scenarios/data_science/dev/prompts.yaml:1-80`（`exp_feedback`） | 六步判定：格式 → 评测对齐 → 结果比较 → 相近分数看代码 → EDA → 总体可接受 | 备选，未接入（`references/workflow/standard-flow.md` S8 与 `references/triage/README.md` 的有序排查思路相近，但没有写入这六步） |
| `rdagent/components/coder/data_science/pipeline/prompts.yaml:86-117`（coder 侧）、`:262-270`（eval 侧 Debug Mode Compliance） | 调试模式：取 10% 数据跑最少轮次，计时并外推全量耗时 | 备选，未接入（`mlgain/scripts/train_sanity_checks.py`（本包未包含） 没有对应功能） |
| `rdagent/components/coder/model_coder/eva_utils.py:32-50`、`evaluators.py:20` | 移植等价检查：形状 + 数值。其阈值 `MAE < 0.1` 太松；改为同一 `state_dict` 下按 dtype 设容差 | 已写进文档（`mlgain/references/paper-port-fidelity.md`（本包未包含） 第 3 节）；`mlgain/scripts/module_probe.py`（本包未包含） 没有作者实现对照函数（其 `step0_parity` 比的是插座开/关，不是移植等价） |
| `rdagent/components/coder/CoSTEER/knowledge_management.py:104-139`、`:231-247`（`failed_task_info_set`、`fail_task_trial_limit`） | 失败台账：同一任务失败超过次数上限就不再重试 | 已写进文档（`references/multi-agent-protocol.md`"裁决分两类"：方向失败写入失败台账，同类提案先查）；"超过次数上限不再重试"备选，未接入（`assets/hypothesis-trace.schema.json` 没有失败计数字段） |
| `rdagent/components/coder/data_science/model/eval_tests/model_test.txt:44-79`（`get_original_code` + `debug_info_print`） | 函数返回时取出局部变量，定位静默错误 | 已实现（`mlgain/scripts/train_sanity_checks.py`（本包未包含）:`debug_locals`）：按思路重写，不是复制。原版用 `sys.settrace` 在返回事件里打印全部局部变量的 repr，并靠 `get_original_code` 解开 joblib 缓存包装；本地版用 `sys.setprofile`（只收调用/返回事件）并恢复原有 profiler，把局部变量摘要（shape/dtype/min/max/是否有限）存进 `wrapper.last_locals`，没有取 `get_original_code`。docstring 注明改写来源与 MIT/Microsoft 版权 |

更正：调试模式的 10% 数据与耗时外推在 pipeline `prompts.yaml` 的 86-117 行（coder 提示）；220-300 行是 `pipeline_eval` 评审提示，其中 262-270 行检查是否遵守调试模式。

## 没拿什么及原因

- 整个 RD-Agent 运行框架（LLM 编排、Kaggle 场景、Docker 执行环境）：与本机现有 Agent 团队重复。
- 知识库 RAG 检索（`CoSTEERRAGStrategy`）：本地只记失败台账，不做向量检索。
- `MAE < 0.1` 的数值等价阈值：太松，见上表。

## 下次升级看哪些路径

- `rdagent/core/proposal.py`
- `rdagent/scenarios/data_science/proposal/exp_gen/`（`proposal.py`、`prompts_v2.yaml`）
- `rdagent/scenarios/data_science/dev/prompts.yaml`
- `rdagent/components/coder/data_science/pipeline/prompts.yaml`
- `rdagent/components/coder/model_coder/`、`rdagent/components/coder/CoSTEER/knowledge_management.py`
- `rdagent/components/coder/data_science/model/eval_tests/model_test.txt`（`debug_locals` 的思路来源）
