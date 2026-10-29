# 上游卡片：Auto-Research-Skills（技能目录）

## 链接与许可证

- 仓库：<https://github.com/brycewang-stanford/Auto-Research-Skills>
- 许可证：目录仓库本身 CC0-1.0。它通过 110 个 git submodule 收录各家技能，**子模块未拉取**；`catalog/skills.csv` 的 `license` 列对多数条目为空。每个子模块的许可证要在它自己的仓库里核实，核实前只借思路、不复制文字。

## 吸收的版本

- commit `14ed77789191335932957a98824f161165189872`（2026-10-20），吸收日 2026-10-22。
- 依据文件：`catalog/skills.csv`（6090 行，列 `name,collection,path,repo_url,license,…`）。下表行号指该 CSV 的行。

## 拿了什么（全部为借思路）

| 目录条目（`catalog/skills.csv` 行 → 子模块路径） | 来源仓库 / 目录记的许可证 | 借来的想法 | 状态 |
|---|---|---|---|
| `investigating-anomalous-results` → `skills/science-superpowers/skills/investigating-anomalous-results/SKILL.md` | K-Dense-AI/science-superpowers / 空 | 反常结果先查实验本身 | 已写进文档（`references/triage/README.md`，"来源"一节署名） |
| `differential-audit`、`diagnose`、`credible-claims` → `skills/claude-code-my-workflow/.claude/skills/*/SKILL.md` | pedrohcgs/claude-code-my-workflow / 空 | 差分审计、诊断顺序、结论可信度分级 | 已写进文档（`references/triage/README.md` 的有序排查与"来源"一节；`references/workflow/standard-flow.md` S8 的结论四分类，未署名） |
| `compare`、`launch`、`debug`、`reproduce` → `skills/phd-skills/plugin/skills/*/SKILL.md` | fcakyon/phd-skills / 空 | 比较前对齐设置、启动前检查、复现流程 | 已写进文档（`references/workflow/standard-flow.md` S4 阳性对照复现、S5 体检通过才开实验、S8 配对比较；思路相近，未署名） |
| `safe-debug`、`minimal-run-and-audit` → `skills/rigorpilot-skills/skills/*/SKILL.md` | lllllllama/RigorPilot-Skills / 空 | 最小运行 + 审计再放大 | 已写进文档（`mlgain/references/paper-port-fidelity.md`（本包未包含） 第 5 节"先最小可运行，再完整训练"，未署名）；`train_sanity_checks.py` 只有单项检查，没有"最小运行再放大"流程 |
| `research-manager`（第 808 行）→ `skills/co-researcher/skills/research-manager/SKILL.md` | poemswe/co-researcher / 空 | 研究任务台账 | 已实现（`assets/hypothesis-trace.schema.json`；字段设计署名来自 RD-Agent，本条只是同类思路） |
| `ml-training-recipes`（第 109 行）→ `skills/ai-research-skills/10-optimization/ml-training-recipes/SKILL.md` | Orchestra-Research/AI-Research-SKILLs / MIT | 训练配方清单 | 备选，未接入（`references/tuning/README.md` 的调参顺序来自 Tuning Playbook，找不到可归于本条的内容） |
| `experiment-queue` → `skills/aris/skills/experiment-queue/SKILL.md` | wanshuiyin/Auto-claude-code-research-in-sleep（ARIS）/ 空（上游实为 MIT，已另有 vendored 条目） | 实验排队与续跑 | 已实现（`scripts/hpo_study.py`:`cmd_create` 入队、`cmd_run` 续跑；同类机制，由 Optuna 存储实现） |
| `paper-code-audit` → `skills/feynman/skills/paper-code-audit/SKILL.md` | companion-inc/feynman / 空 | 论文与代码逐项对照审计 | 已写进文档（`mlgain/references/paper-port-fidelity.md`（本包未包含） 第 2 节对应表，未署名） |

更正：`research-manager` 在目录里属于 `co-researcher` 集合（许可证空），不属于 `ai-research-skills`；`ai-research-skills` 里同名的是 `ara-research-manager`（第 160 行，MIT，`22-agent-native-research-artifact/research-manager/`）。原吸收清单把两者混写，具体借的是哪一个待确认；两者都只借思路。

## 没拿什么及原因

- 子模块正文：未拉取，许可证多数未知。
- 目录里的其他约 6000 条技能：与深度学习实验流程无关或重复。
- `benchmarks/`、`systems/` 子模块：未评估。

## 下次升级看哪些路径

- `catalog/skills.csv`（条目增删、许可证列补全）
- `.gitmodules`（子模块指向与固定 commit 变化）
- 要把某条从"借思路"升级为复制前：先在其来源仓库核实许可证，再按 absorber 单独登记一个来源。
