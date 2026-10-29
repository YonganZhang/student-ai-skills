# 来源与本地验收记录

2026-09-16：按用户授权直接引入 ARIS 10 个技能正文及必要参考/证据工具。原版清单见 [MANIFEST](vendor/MANIFEST.json)，执行入口见 [README](README.md)。

- accept：实验计划/实现桥接、先小试、训练监控、独立审计、结果与主张核对、消融、评审循环；原版正文及MIT授权直接保留。
- adapt：调用实际可用的本地审查方式；先确定性工具后模型判断；项目预算/数据边界；普通日志替代强制W&B；缺项、失败、审查不可用明确报告；所有命令经项目适配。
- reject-with-reason：固定昂贵模型与推理档位、静默跳过审查、自动租云/部署、无限修复循环、破坏性回退；这些不能保证接入质量且超出当前授权。
- Codex与Claude分别维护入口，新工具/原版文件是各自独立副本；保留双方已有差异、文献与Elsevier能力。没有复制认证、会话或MCP运行态。

两边各18项本地测试通过（各含4项真实PyTorch行为用例），上游工具12项通过；45个来源文件核对通过。入口/引用检查通过，无本次新增孤儿脚本。原生独立Codex子智能体复审通过（独立上下文、同模型，不是异模型）。

证据目录：用户工作区 tmp/2026-09-16-aris-integration/，包含 report.md、local-tests.log、claude-local-tests.log、audit-summary.json、loader-check.json、independent-review.md。

未运行任意实际研究项目或GPU/分布式模型；新增路由用例只做作者检查，没有声称模型盲测通过。后续每次接入仍须项目断言、原始证据和独立审查。

2026-09-16 管理整理：10 个参考目录统一为 `aris-*`，manifest 记录上游名到本地名的映射，正文/hash 不变；新增自然语言默认路由及 TOP 双向链接。accept：前缀管理与单一入口；adapt：使用双方自己的 TOP CLI 路径与原有入口；reject-with-reason：不新建 10 个全局注册、不复制另一套当前计划、不增加自动后台同步。

2026-10-22 本地缺口：vendored `shared-references/resumable-runs.md` 与 `integration-contract.md` 提到的 `tools/run_state.py` 未随 ARIS 引入（原文不改，保持逐字副本）。本地可续跑做法：运行清单用 `scripts/run_manifest.py`，超参搜索的断点续跑用 `scripts/hpo_study.py`（Optuna SQLite + 心跳重排），见 [调参](../tuning/README.md)。
