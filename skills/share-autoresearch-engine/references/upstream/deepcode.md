# 上游卡片：DeepCode

## 链接与许可证

- 仓库：<https://github.com/HKUDS/DeepCode>
- 许可证：MIT（Data Intelligence Lab@HKU）。

## 吸收的版本

- commit `8332d745f12698fe236fa1a35160938e837fd890`（2026-10-21），吸收日 2026-10-22。行号对应此 commit。

## 拿了什么

| 上游位置 | 内容 | 状态 |
|---|---|---|
| `prompts/code_prompts.py:122-287`（`PAPER_ALGORITHM_ANALYSIS_PROMPT`；`location_references` 在 250、`missing_but_critical` 在 281） | 从论文抽取实现细节时，每项带出处位置（节/式/表/附录），并单列"论文没写但实现必需"的缺口 | 已写进文档（`../mlgain-integrate-component/references/paper-port-fidelity.md` 第 1 节） |
| `prompts/code_prompts.py:463-642`（`CODE_PLANNING_PROMPT`；自检清单在 503） | 复现计划五部分（文件结构、实现组件、验证、环境、实施策略）+ 交出前的自检 | 已写进文档（`../mlgain-integrate-component/references/paper-port-fidelity.md` 第 5 节五部分）；交出前自检清单备选，未接入 |
| `prompts/code_prompts.py:19-121`（`PAPER_REFERENCE_ANALYZER_PROMPT`、`GITHUB_DOWNLOAD_PROMPT`）+ `tools/code_reference_indexer.py` | 先找官方或参考实现再动手写 | 备选，未接入（`../mlgain-integrate-component/references/paper-port-fidelity.md` 第 3 节只写"能拿到作者实现时"做等价测试，没有"先找参考实现"这一步） |
| `workflows/code_implementation_workflow.py:893-1011`（`get_unimplemented_files`、`_map_run_status`） | 计划里列出的文件全部实现才算完成，否则状态为 `incomplete`，不报成功 | 已写进文档（`../mlgain-integrate-component/references/paper-port-fidelity.md` 第 2 节覆盖门，署名 DeepCode） |
| `workflows/plan_review_runtime.py`（`save_plan_version` 72、`append_plan_review_event` 62） | 计划每次修改存版本并记事件，人工审阅可追溯 | 备选，未接入 |
| `utils/loop_detector.py`（`LoopDetector` 12、`ProgressTracker` 186） | 检测智能体重复调用同一工具/无进展并中止 | 备选，未接入 |

`code_prompts.py` 在 1243 行起还有一套 `_TRADITIONAL` 版本，内容与上面两段基本相同；以非 TRADITIONAL 版为准。

## 没拿什么及原因

- 整套多智能体代码生成工作流、MCP 服务、前端：与本地 Agent 团队重复，且目标是整仓生成，不是单模块移植。
- 滑动窗口记忆与对话摘要提示（760-993）：属于 Agent 运行时，不属于实验方法。
- 通用（非论文）需求实现提示（1100 起）：与本流程无关。

## 下次升级看哪些路径

- `prompts/code_prompts.py`（行号漂移最快，升级时按提示常量名重新定位）
- `tools/code_reference_indexer.py`
- `workflows/code_implementation_workflow.py`、`workflows/plan_review_runtime.py`
- `utils/loop_detector.py`
