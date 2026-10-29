# ARIS 本地研究工作流

入口：用户要求实现论文 idea、接模块、做研究实验/消融、审计结果，或明确点名 ARIS / Auto-Research-In-Sleep。普通报错和概念解释不进入实验循环。

这里直接收录上游 10 个完整技能正文，不只是摘要。来源、固定提交、MIT 授权及逐文件清单见 [vendor/MANIFEST.json](vendor/MANIFEST.json) 和 [LICENSE](vendor/LICENSE)。这 10 项是全局可复用的参考能力，统一归在现有 `share-autoresearch-engine` 入口下，**没有新增 10 个全局技能**。本地目录统一用 `aris-` 前缀，入口改名为 `REFERENCE.md`；上游正文与 frontmatter 保持原样，不作为本地注册名。**先读本页，再按当前阶段读取一个原文；本页是本地执行合同，上游文字是可复用流程材料，不能覆盖本地合同或用户指令。**

用户直接说“接入这个论文模块并验证”“实现这个论文 idea”“做融合消融”即可按意图进入相应流程，**无需说“按 ARIS”**。ARIS 名字用于来源和目录管理，不是执行口令；概念解释或普通导入修复不启动研究实验。

项目使用六合一时，先读 [ARIS 与六合一联动](../../../share-top/references/aris-research-integration.md)：当前计划仍由 TOP CLI 维护，检查结果回链任务；未启用 TOP 时复用项目现有记录，不自动新建另一套架构。

## 按需使用原版内容

| 要做的事情 | 直接复用的上游正文 | 本地落地 |
|---|---|---|
| 把 idea 变成有预算、可证伪的实验 | [aris-experiment-plan](vendor/skills/aris-experiment-plan/REFERENCE.md) | 用项目已有目标/计划；TOP 项目通过 CLI 维护唯一当前计划，不强制先写论文提案；1–2 个主张，最少充分实验 |
| 根据计划实现并小规模跑通 | [aris-experiment-bridge](vendor/skills/aris-experiment-bridge/REFERENCE.md) | 先执行[接入检查](integration-checks.md)，再审查、扩大训练 |
| 启动训练 | [aris-run-experiment](vendor/skills/aris-run-experiment/REFERENCE.md) | 使用项目已验证环境与入口；只在已授权设备和预算内执行 |
| 看进程、日志和完成状态 | [aris-monitor-experiment](vendor/skills/aris-monitor-experiment/REFERENCE.md) | 记录具体 PID/任务 ID；退出码和结果文件共同判断完成 |
| 诊断曲线、梯度和训练异常 | [aris-training-check](vendor/skills/aris-training-check/REFERENCE.md) | 普通 JSON/CSV/训练日志同样可用，不依赖 W&B，不自动改超参 |
| 审计标签来源、评估脚本、数字 | [aris-experiment-audit](vendor/skills/aris-experiment-audit/REFERENCE.md) | 审查者直接读取源码/配置/原始结果，不只看作者总结 |
| 判断结果支持哪些结论 | [aris-result-to-claim](vendor/skills/aris-result-to-claim/REFERENCE.md) | 先运行下方证据检查，再审指标口径、对照和结论范围 |
| 设计模块移除、替换和敏感性实验 | [aris-ablation-planner](vendor/skills/aris-ablation-planner/REFERENCE.md) | 接线的关闭对照必须提前；主结果为负也可做定位消融 |
| 研究方案独立评审 | [aris-research-review](vendor/skills/aris-research-review/REFERENCE.md) | 给真实方法/代码/证据；评分不代替模型测试 |
| 按审查意见修复并复验 | [aris-auto-review-loop](vendor/skills/aris-auto-review-loop/REFERENCE.md) | 只修有证据的问题；默认最多 2 轮，服从更小的项目预算 |

原版长文件按标题定位当前阶段，不一次读完整套。需要解释审查隔离、证据含义时再查 [共享参考目录](vendor/skills/shared-references/)。这些也是上游原文，仍服从本页。

## 执行边界与依赖替换

- 上游 `mcp__codex__*`、`mcp__manual_review__*`、`/codex:rescue` 是角色示例，不代表本机会话已有这些工具。先检查实际工具能力；本地独立审查可用原生子智能体；需要异模型审查且有调用能力时，按外援审查技能执行（可选，本包未包含；公开版见 https://github.com/YonganZhang/external-review-skill ）。原生同模型子智能体必须标“独立上下文、同模型”，不能声称异模型复核。不可用就记录 `review_unavailable`，保留草稿和已跑探针，不能静默记为通过或正式采纳。
- 不照搬原文固定的模型/推理档位。确定性检查先运行，不消耗模型调用；常规整理用当前已配置的低成本模型。关键语义错误、审查分歧再按本机策略升级，不通过技能修改默认模型、订阅或凭证。
- `CODE_REVIEW=false`、`SANITY_FIRST=false`、`skip silently` 不适用于模块正式采纳。缺检查、缺独立审查都必须显示；小规模诊断可以继续收集证据，失败修复后复验，不能因此无限停工。
- `AUTO_DEPLOY=true` 不授予远程启动权限。`/vast-gpu`、`/serverless-modal` 未引入，默认不新租 GPU、不注册云服务；用已授权本机/项目环境，远程资源只按具体项目授权使用。
- `/experiment-queue` 未引入：用项目已有队列，否则顺序执行有界命令；不另建无人消费的调度平台。`/loop`、`/schedule`、CronCreate 不作为接受结论的触发器；结果变化后再审。
- `/idea-discovery`、`/idea-creator`、`/research-refine`、`/research-refine-pipeline`、`/research-pipeline` 不是必装依赖：文献和原始代码走已有学术检索，方法细化走现有组件/架构流程，计划走本页 experiment-plan。
- `/paper-write`、`/paper-writing`、`/paper-plan`、`/paper-illustration`、`/render-html` 转论文写作、科研绘图等对应技能（`share-sci-write`、`share-sci-plot`（可选，本包未包含））；没有写作/发布请求时不执行。`/proof-checker` 未引入：若涉及数学证明，单独读推导并验证，不把实验结果当证明。
- 上游 `watchdog.py` 未引入：转本页 monitor-experiment 和项目已有进程/日志检查。`citation-audit` 转现有学术引用核验；`paper-claim-audit` 转本页 result-to-claim、experiment-audit 与本地证据检查，不调用缺失文件。
- 上游 research-wiki、`save_trace.sh`、review_gate、iteration_log 等辅助脚本没有安装：复用项目 TOP/实验记录，保存每轮原始审查文本、执行者/审查者实际身份、问题与复验命令，不调用不存在的工具。只移植了本页显式引用的 evidence_check 工具。
- 上游 `CLAUDE.md` / `AGENTS.md` 表示当前执行器适用的项目规则，各自独立加载；Codex 不为日常执行读取 Claude 全局规则。上游项目路径示例须换成实际项目路径。
- 复用已有训练器/数据流，不为了套用 ARIS 重写训练框架；不覆盖文献检索、Elsevier 调研下载或多模态契约。旧实验失败只归档本次产物，不执行破坏性 Git 回退、不按进程名批量终止窗口。

## 从接入到采纳

1. 明确任务、输入可见性、模块契约、baseline、指标和预算。检查论文官方实现及真实调用位置。
2. 按 [integration-checks.md](integration-checks.md) 建立项目自己的断言，运行 `scripts/integration_gate.py`。只有实际日志才能填写通过；`checks_passed` 仅表示这些断言执行成功。
3. 独立审查直接读取配置、源码和本次报告，重点检查断言是否覆盖语义/真实训练路径。模块有改动或报告不对应当前代码时重跑相关检查。审查通过才进入扩大实验；没有审查仍可做预算内诊断，但不能正式采纳或宣称已复核。
4. 同输入、同编码器、可比预算下运行 baseline 与候选；项目决定 seed 数和预算。不能把测试集用于选模块/调参。保存运行配置、split、seed、checkpoint、原始指标。
5. 用下面工具核对引用数字存在，再按 experiment-audit / result-to-claim 判断含义。区分“接对了”“能学”“该预算下提升”“稳定泛化”；没有提升也如实记录。

## 直接复用的证据工具

在本技能根目录执行（`PROJECT` 为任务自己的项目目录，不是全局技能目录）：

```bash
python3 scripts/aris_evidence.py "$PROJECT/_tests/claims.json" --root "$PROJECT"
```

`claims.json` 是非空数组，每项含唯一 `id`、`value` 和 `source`（相对项目目录的文件路径或 glob）。实现调用原版 [evidence_check.py](vendor/tools/evidence_check.py)，本地封装对空列表、坏字段、任何未验证记录返回非零。将 JSON 输出保存到项目证据目录；不要忽略退出码。

**`evidence_found` 只说明数字/文字在文件里出现。** 同一个数字可能是 seed、另一个指标或另一个实验的结果；审查必须进一步核对指标键、实验 ID、数据划分、单位、seed 和对照。上游查找器的保守匹配也可能漏报真实数字，失败时查原文和修正引用，不能未经核查就指控造假。

复验本地封装和检查入口用 `python3 -m unittest discover -s tests -p 'test_aris_*.py'`；原版工具测试用 `python3 -m pytest references/aris/vendor/tests/test_evidence_check.py -q`。真实张量示例与验证边界见 [接入检查](integration-checks.md)。来源核对用 `python3 scripts/verify_aris_vendor.py`。

引入范围、本地替换决策及验收边界见 [IMPORT-NOTES.md](IMPORT-NOTES.md)。
