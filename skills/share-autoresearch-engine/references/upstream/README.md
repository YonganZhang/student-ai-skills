# 上游来源索引（深度学习流程升级，2026-10-22）

放什么：本技能在 2026-10-22 深度学习流程升级中吸收的 8 个仓库与 6 个工具的来源卡片，以及两份逐字副本（`vendor/`）。不放什么：其他批次的上游（ARIS、K-Dense 等仍按 `../../UPSTREAM.json` 原条目与各自目录管理）。

版本与路径的唯一真源是技能根目录的 `UPSTREAM.json`；本表和卡片是给人读的说明，两者不一致时以 `UPSTREAM.json` 为准并回来修正本表。

## 索引

吸收日均为 2026-10-22。"吸收版本"对仓库是本地浅克隆的 HEAD，对工具是当天默认分支 HEAD（括号里是 2026-10-22 核对过的已安装版本，见卡片）。

| 名称 | GitHub | 许可证 | 吸收版本 | 方式 | 拿了什么 | 真实落点（已实现或已写进文档） | watch |
|---|---|---|---|---|---|---|---|
| [Tuning Playbook](tuning-playbook.md) | [google-research/tuning_playbook](https://github.com/google-research/tuning_playbook) | CC-BY-4.0 | `7554a51` | vendored + semantic | 边界判定、看曲线、隔离图、重跑估方差、准随机→贝叶斯、训练步数、回看选检查点、不稳定性处理 | `vendor/tuning_playbook-README.md`、`references/tuning/README.md`、`scripts/hpo_study.py` | 是 |
| [Optuna](optuna.md) | [optuna/optuna](https://github.com/optuna/optuna) | MIT | `2b50cfc` | tool（直接调用 + 文档） | SQLite+心跳续跑、入队去重、部分固定采样、QMC→TPE、预算回调、参数重要性；Wilcoxon 剪枝只写进文档 | `scripts/hpo_study.py`、`references/tuning/README.md` | 是 |
| [timm](timm.md) | [huggingface/pytorch-image-models](https://github.com/huggingface/pytorch-image-models) | Apache-2.0 | `af97f99` | semantic | 配置哈希、计划变更即拒绝、严格加载、优化器成员陷阱；top-N 检查点与多 seed 聚合只写进文档 | `scripts/run_manifest.py`、`scripts/hpo_study.py`、`references/tuning/README.md`、`references/triage/README.md`、mlgain `train_sanity_checks.py` | 是 |
| [RD-Agent](rd-agent.md) | [microsoft/RD-Agent](https://github.com/microsoft/RD-Agent) | MIT | `484776c` | semantic | 假设/反馈/轨迹字段、五项打分、实现失败 vs 方向失败、失败台账、移植等价收紧、局部变量摘要（改写） | `assets/hypothesis-trace.schema.json`、`references/multi-agent-protocol.md`、`references/triage/README.md`、mlgain `paper-port-fidelity.md` / `train_sanity_checks.py` | 是 |
| [DeepCode](deepcode.md) | [HKUDS/DeepCode](https://github.com/HKUDS/DeepCode) | MIT | `8332d74` | semantic | 论文抽取带出处与缺口、五部分复现计划、计划组件全覆盖才算完成 | mlgain `paper-port-fidelity.md` | 是 |
| [AREX-Skill](arex-skill.md) | [VectorSpaceLab/AREX-Skill](https://github.com/VectorSpaceLab/AREX-Skill) | 根 Apache-2.0；`cli/` MIT | `ac3fe1a` | vendored + semantic | 恢复论文结果流程的逐字副本；最小运行、证明参数变化、模块计划与部分判定标准写进文档 | `vendor/arex-recover-paper-result.md`、mlgain `paper-port-fidelity.md` | 是 |
| [Auto-Research-Skills](auto-research-skills.md) | [brycewang-stanford/Auto-Research-Skills](https://github.com/brycewang-stanford/Auto-Research-Skills) | CC0-1.0（目录）；子模块各异 | `14ed777` | semantic（只借思路） | 反常结果排查、差分审计、最小运行、实验队列等思路；目录 `catalog/skills.csv` | `references/triage/README.md`、`references/workflow/standard-flow.md`、`scripts/hpo_study.py`、mlgain `paper-port-fidelity.md` | 是 |
| [AutoDL](autodl.md) | [DeepWisdom/AutoDL](https://github.com/DeepWisdom/AutoDL) | Apache-2.0 | `48db4eb` | semantic | 发散回滚、验证集搜增强反例写进文档；时间预算停止、对数时间 ALC、按图像 bootstrap 为备选 | `references/tuning/README.md` | 是 |
| [Lightning](lightning.md) | [Lightning-AI/pytorch-lightning](https://github.com/Lightning-AI/pytorch-lightning) | Apache-2.0 | `84df182`（核对已装 2.6.6） | tool | SpikeDetection、EMAWeightAveraging、LearningRateFinder 写进文档；其余回调与 Trainer 参数为备选 | `references/tuning/README.md`（脚本未接入） | 是 |
| [torchinfo](torchinfo.md) | [TylerYep/torchinfo](https://github.com/TylerYep/torchinfo) | MIT | `3eb5f38`（核对已装 1.8.0） | tool | `summary` 逐层表与 trainable 字段（`mode` 未用） | mlgain `train_sanity_checks.py`（`frozen_audit`，可选依赖） | 是 |
| [cleanlab](cleanlab.md) | [cleanlab/cleanlab](https://github.com/cleanlab/cleanlab) | Apache-2.0 | `7506257`（核对已装 2.9.0） | tool | 分割式标签问题查找（点渲染成圆盘 + 交叉拟合热图）；检测模块 | 备选，未接入（仅卡片；范式工具表列名） | 是 |
| [FiftyOne](fiftyone.md) | [voxel51/fiftyone](https://github.com/voxel51/fiftyone) | Apache-2.0 | `aacfc81`（未安装） | tool（暂不接入） | Keypoint / Heatmap 字段；无关键点评估器、依赖 MongoDB | 备选，未接入（仅卡片；范式工具表列名） | 是 |
| [DVC](dvc.md) | [treeverse/dvc](https://github.com/treeverse/dvc) | Apache-2.0 | `56e5982`（未安装） | tool（只借思路） | `dvc.lock` 内容哈希；本地只记录哈希，不做过期判定 | `scripts/run_manifest.py` | 是 |
| [Captum](captum.md) | [meta-pytorch/captum](https://github.com/meta-pytorch/captum) | BSD-3-Clause | `b89cccb`（未安装） | tool | 层激活与消融归因（热图包成标量目标） | 备选，未接入（仅卡片；范式工具表列名） | 是 |

各卡片"拿了什么"表的"状态"列只取三种值，按当前工作树核对：

- `已实现（文件:符号）`：该文件确实导入、调用或实现了这一项；
- `已写进文档（文件）`：该文档确实提到这一项；
- `备选，未接入`：只记在卡片里，供将来选用。

一行只部分落地时分开写（例如"已写进文档（…）；某子项备选，未接入"）。代码或文档改动后要回来改状态，不按计划写成已完成。

路径写法（本表"真实落点"列与各卡片"状态"列）：`references/…`、`scripts/…`、`assets/…` 相对本技能根目录；同级技能写作 `../mlgain-integrate-component/…`（同样相对本技能根目录），本表简写为"mlgain"；`vendor/…` 相对本目录。`UPSTREAM.json` 的 `local_paths` 只登记卡片本身和确实提到该来源内容的文件（含范式工具表），备选项写在 `note` 里。

## 怎样升级

1. 查上游变化（只读）：

   ```bash
   python3 ~/.claude/skills/share-skill-creator/scripts/upstream_watch.py --remote
   ```

   只输出吸收版本之后确有改动的路径；逐字副本还会比对文件哈希。
2. 读对应卡片的"拿了什么"和"下次升级看哪些路径"，只看与我们吸收内容相关的改动。
3. 值得吸收时，按 `share-skill-creator` 的 absorber 流程选择性吸收：逐字副本整份替换并重算比对；改写吸收的只改受影响的本地文件。
4. 更新 `UPSTREAM.json` 对应条目的 `absorbed_commit` 与 `absorbed_at`；上游搬路径时改 `paths` 并在 `note` 写旧路径。
5. 更新卡片：版本号、行号；把看过但决定不采纳的上游改动及原因写进"没拿什么及原因"。
6. 工具类条目同时核对当前项目解释器里的已安装版本，升级前先跑调用它的脚本的测试。
7. 跑 `upstream_watch.py --lint` 确认格式无误。
