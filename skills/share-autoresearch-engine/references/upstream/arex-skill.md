# 上游卡片：AREX-Skill

## 链接与许可证

- 仓库：<https://github.com/VectorSpaceLab/AREX-Skill>
- 许可证：仓库根目录 Apache-2.0（`LICENSE`，副本在 `vendor/arex-skill-LICENSE`）；`cli/` 目录单独为 MIT（`cli/LICENSE`，版权 Mario Zechner，上游 README 第 344-356 行说明）。上游还声明每个技能以其 SKILL.md 的 license 字段为准；下面用到的三份 `cli/.../disco/skills/*/SKILL.md` 没有 license 字段，按所在目录 `cli/` 的 MIT 处理。
- 逐字副本 `vendor/arex-recover-paper-result.md` 位于上游 `cli/` 下，适用 MIT；`cli/LICENSE` 的 MIT 全文随副本保存在 `vendor/arex-skill-cli-LICENSE`，已在 `UPSTREAM.json` 的 vendored 条目登记。

## 吸收的版本

- commit `ac3fe1afa80fb9a09775ecfb2b6cc3ba850a2db6`（2026-09-03），吸收日 2026-10-22。
- 逐字副本：`vendor/arex-recover-paper-result.md` ← `cli/packages/coding-agent/src/disco/skills/recover-paper-result/SKILL.md`（152 行）。文件名故意不用 `SKILL.md`，否则 Codex 会把嵌套的 SKILL.md 当成技能列出。

下文 `disco/skills/` 指 `cli/packages/coding-agent/src/disco/skills/`。

## 拿了什么

| 上游位置 | 内容 | 状态 |
|---|---|---|
| `disco/skills/recover-paper-result/SKILL.md:16-43` | 恢复时的硬来源边界：只许读论文、模块文档和数据，禁止读原仓库 | 逐字副本 `vendor/arex-recover-paper-result.md`；规则本身备选，未接入（`../mlgain-integrate-component/references/paper-port-fidelity.md` 只链接该副本，没有写入来源边界；其第 3 节反而鼓励拿到作者实现时做等价测试） |
| `disco/skills/recover-paper-result/SKILL.md:44-64`、`100-148` | 预检与时间预算、结果 schema、验收标准、最小恢复运行 | 已写进文档（`../mlgain-integrate-component/references/paper-port-fidelity.md` 第 5 节：先最小可运行、缩减版与完整训练分开、结果 JSON 由脚本生成）；预检与时间预算、验收标准备选，未接入 |
| `disco/skills/recover-paper-result/scripts/validate_recovery_experiment.py`（191 行；`params_changed` 32、`existing_training_trace` 24） | 校验恢复实验真的训练过（有训练轨迹、参数确实变了、命令成功） | 已写进文档（`../mlgain-integrate-component/references/paper-port-fidelity.md` 第 5 节"声称训练过就要证明参数前后不同"）；`train_sanity_checks.py` 没有对应检查，脚本层面备选，未接入 |
| `disco/skills/plan-paper-skill-modules/SKILL.md:56-97` | 跨模块契约检查与模块计划 schema | 已写进文档（`../mlgain-integrate-component/references/paper-port-fidelity.md` 第 2 节对应表与覆盖门、第 5 节复现计划） |
| `disco/skills/analyze-paper-recovery/SKILL.md:47-96` | 恢复结果判定：接受（来源边界有效、指标为数值、有可执行命令证据、核心模块确实被调用、差距在容差内）或 refine（跳过核心组件、依赖原仓库代码、差距大且无解释、证据文件缺失等） | 已写进文档（`../mlgain-integrate-component/references/paper-port-fidelity.md`，只含其中两条：第 2 节缺组件记"移植未完成"、第 4 节模块确实进入 forward）；来源边界与差距容差判定备选，未接入 |
| `skills/repositories/repo-skills-router/SKILL.md`（48 行） | 分层路由：先按领域分区再进具体技能；技能记录固定来源 commit | 备选，未接入（只记在本卡片） |

## 没拿什么及原因

- `cli/` 的整个编码 Agent（disco 运行时）：与本机 Claude/Codex 重复。
- 其余 disco 技能（`create-paper-skills`、`distill-ml-knowledge` 等）：面向"把论文做成技能库"，不是本流程的模块移植。
- `skills/repositories/` 下的具体仓库技能：数量大、按仓库各自许可，未逐一核查。

## 下次升级看哪些路径

- `cli/packages/coding-agent/src/disco/skills/recover-paper-result/`（含 `scripts/`）
- `cli/packages/coding-agent/src/disco/skills/plan-paper-skill-modules/SKILL.md`
- `cli/packages/coding-agent/src/disco/skills/analyze-paper-recovery/SKILL.md`
- `skills/repositories/repo-skills-router/SKILL.md`
- `LICENSE`、`cli/LICENSE`（许可证变化会影响逐字副本能否保留）
