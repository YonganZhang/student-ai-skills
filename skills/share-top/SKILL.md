---
name: project-top
description: "项目目标、进度、计划、验收、交接与六合一；介绍、梳理或更新项目方法论，衔接方法思维导图。"
---

# TOP — 项目进度与六合一

TOP 让下一个会话或另一个 AI 知道四件事：这个项目想弄清什么、弄清了什么、现在在试什么、为什么这么做。真源只放在项目文件里，工具只负责读写计划和少量校验。原则是**第一次就做对**：开工时写清验收标准，完成时附一次证据，不靠事后多道检查补救。命令全集、Hooks、Git 联动和可选工具见 [runbook](references/share-top-runbook.md)。

## 最小可行版本（必需）

| 部分 | 内容 | 规则 |
|---|---|---|
| `AGENTS.md`（Claude/Codex 共读） | 项目身份、不变量、真源指针、验证命令 | ≤60 行；不写当前状态和历史 |
| `_wiki-methodology/_top/_task_plan.md` | **问答格式**（默认）：目标、现在（CLI 生成）、问答目录（每个问题一句答案，CLI 从工作本生成） | 只经 `plan` 命令改；给人看的目录，不是日记 |
| `_wiki-methodology/_top/_questions/Q<n>.md` | 每个问题的工作本：答清标准、答案修订、尝试、旧编号、笔记 | 结构区只经命令改；`为什么问`、`怎样算答清`、`笔记` 可直接编辑 |
| `_wiki-methodology/_top/_logs/` | plan 自动日志、笔记、复盘和交接 | 长内容写这里，计划里只放链接 |

旧的**目录格式**（阶段 → 步骤 + `_plan_details.md`）仍然能读能写，见 [plan-writing.md](references/plan-writing.md)；改成问答格式见 [qa-plan.md](references/qa-plan.md)「迁移」。

其余都是**可选模块**，真需要时才启用（`init-research.sh --with …`）：`_decisions/`、`_codemap.md`（≤5KB）、`_meta/_registry.yml`、`_meta/_data_registry.yml`、`_wiki/`、`_tests/`、`_pipelines/`。六列定义与模块边界以 [canonical-six-columns.md](references/canonical-six-columns.md) 为准。

- **代码**：CodeGraph 管结构（`codegraph explore`），`_codemap.md` 写一页纸的用途和入口，决策记忆记理由（`record for-file` 按文件找回；本文 `record` 指 `python3 ~/.claude/skills/share-top/scripts/sixone-cli.py record` 子命令，非独立短命令）。
- **Git 是骨架**：提交、trailer（`Task:`/`Decision:`/`Handoff:`）和 tag 记录"发生了什么"；TOP 只记 Git 记不下的意图、当前坐标和决策理由。约定见 [git-version-lifecycle.md](references/git-version-lifecycle.md)。
- **什么进 Git**：按 [git-workflow.md](references/git-workflow.md) 的追踪分类判断，操作与追踪细则也在那里；未提交的内容堆多了，用 `track` 分拣。

## 计划：问答式，短命令 `plan`

一个项目就是一串**问题**。人读"问题 + 答案"看懂整个故事；AI 在每个问题的工作本里记尝试、细节和笔记。`plan` 是短命令（`~/bin/plan` 软链到本技能的 `scripts/plan`），查看出几行人话，修改回一两行；`--json` 出原始 JSON；`plan help` 一屏速查。

```bash
plan                              # 目标、正在弄清、当前判断、正在做、下一步、需要你、问答目录
plan Q4 [全部] | plan P5.38       # 一个问题的工作本 / 迁移前的旧编号去了哪
plan ask "问题？" --done-when "怎样算答清"          # 加问题（写给人：≤20 字大白话）
plan answer Q4 "结论在前的一句话" --ev <证据>       # 答完关闭问题（--keep-open 是阶段性判断）
plan reopen Q4 "原因" [--because Q3.11] [--invalid Q4.8]   # 发现错了：立即撤回答案
plan flag Q5 "要重新确认什么"                        # 上游变了，下游打 ⚠
plan add "做什么" [--to Q4] [--from Q2.4..Q2.6] [--because Q3.11]   # 尝试（写给自己，可技术化）
plan start Q4.3 | plan done Q4.3 "结果" --ev … [--supersedes Q4.1] [--commit]
plan block Q4.3 "原因" [--you] | plan cancel Q4.3 "原因" | plan focus Q5 [--next …]
plan note "一句话" [--on Q4.3] [--fail|--learn] | plan check | plan upgrade [--apply] | plan init "目标"（已有空计划用 plan goal "目标"）
```

**写法**（细则、反例、非线性的记法见 [qa-plan.md](references/qa-plan.md)）：
- **只有长周期的工作进计划**。短的、碎的、跟长期目标无关的事（查个东西、一次性小改、顺手修环境）完全不进计划，改了文件、提交了代码也不用记、不用解释。服务某个问题的实施细节并进已有尝试，只有新结论、换路线、重要卡点才记。
- **问题按独立的验收和答案来拆**，不按尝试次数拆；答案结论在前、带证据；给人看的文字不写路径、编号、参数。
- **做完的结果不改写**：回头重做/重跑就新加一个尝试并写 `--from` / `--because`；新结果确认后才 `--supersedes`；发现错了用 `reopen` 立即撤回答案。
- **焦点和下一步显式**：`start` 自动设焦点；下一步用 `plan focus --next` 写明，不靠程序猜。
- 改别的项目要用 `-p <路径|窗口号>`；别的项目归别的窗口管。

## 流程

**方法论任务**：用户介绍、设计或优化项目方法，或本轮改变了核心输入/模块/公式/依赖时，先读[方法论工作流](references/methodology-workflow.md)。Wiki维护方法合同，图从合同派生，Plan维护进度；需要讲清输入、模块、输出或接入关系时，默认用 `content-technical-roadmap` 的可编辑方法框架图解释；“思维导图/方法思维导图/技术流程图”均按这个意图进入，不要求用户使用规范名称。方法变化当轮回填，草案、已采用方法与验证证据分开。单点释义、进度询问或不改变方法关系的小修改不强制新建文档或图。

1. **开工**：先 `plan` 看在哪、焦点问题是什么，再跑 `plan check` 看版本和结构；新问题写清怎样算答清，新尝试需要时写 `--gate`。改公式、参数、主要步骤或策略前，重看 `plan Q<n>`；改关键文件前看 `record for-file`（编辑时 hook 也会提示）。
2. **中途**：进展、失败、教训用 `plan note` 记一句话（≤300 字，长复盘写进 `_logs/` 再链接）。
   - 卡住时按次数升级，每次失败都 `plan note --fail --on <尝试>`：第 1 次找根因；第 2 次换方法，不重复失败过的动作；第 3 次回头质疑假设，必要时 `reopen` 撤回旧答案。同一尝试第 3 条失败时 CLI 会提示停下找用户。
   - 得到会影响后续工作的结论、取舍或失败经验时才记录；可复用发现用 `record add finding`，尝试心得用 `plan note --learn`。同一事实只记一处，不按阅读次数或轮次写笔记。
   - 需要用户拍板或动手（登录、付款、签字、sudo、选方案）时 `plan block <尝试> "等你…" --you`，首屏（及接入的计划看板）才会显示"需要你"。
3. **收尾**（推进了长周期的尝试时；短碎改动不用）：
   1. 核对实际结果、验证证据和对应改动，用 `plan done <ID> "结果" --ev … --commit` 保存尝试并本地提交；没做完就 `plan note` 记进展、卡点和下一步；
   2. 问题答清后用 `plan answer <QID> "结论" --ev …` 保存答案；一次尝试完成不等于问题答清。焦点问题答清后 `plan focus` 选下一个；
   3. 改了入口或数据时，才更新已启用的登记（启用了知识树又改了文档：同一次提交里更新 `_meta/_doc_summaries.yml` 的条目，再 `doctree build`）；未提交的内容多就先 `track` 分拣；
   4. 在回复里说明更新了哪些真源。

## 梳理六合一（用户说"梳理一下六合一架构 / 整理计划 / 把计划理一理"）

1. 先跑 `plan check` 和 `plan`，看计划是问答格式、目录格式还是旧格式。
2. **目录格式或旧格式**：按 [qa-plan.md](references/qa-plan.md)「迁移」改写成问答格式：归并成问题、每个旧编号写对照、细节搬进工作本笔记，`plan rewrite 草稿 --to qa` 预览，确认后 `--apply`。
3. **已经是问答格式**：逐条处理 `plan check` 的提醒——问题或答案太长、混了路径编号就 `plan rename` / 重新 `answer`；缺"怎样算答清"就补；镜像过期任何写入都会重建；跑题的问题另开项目或 `drop`。
4. 顺带检查最小可行版本的其余部分：`AGENTS.md` ≤60 行、只写身份和指针；日志在位。
5. 本地提交 `_top/`。回复里贴出"目标 + 问答目录"，也就是用户在 `plan` 首屏会看到的样子。

## 升级旧计划（提示里出现"旧格式"时）

模板和格式会升级，旧项目不会自己跟上；接触到就顺手升级，不等用户说。

- **空模板**（目标还是占位符、没有任何任务）：直接换成 `templates/minimal` 里的问答格式空计划，保留已有目标，本地提交 `_top/`。
- **用过的旧计划**（目录格式，或更早的 `P122.E42`、`Current Coordinate` 格式）：用户的事优先。另派一个子智能体在后台按 [qa-plan.md](references/qa-plan.md)「迁移」改写，只写 `_top/`。`plan rewrite … --to qa` 预览没有错误、`dropped_open` 里的每条都有去处，就直接 `--apply` 并本地提交，不用问用户；回复里一句话说明。
- 别的窗口正在推进的项目（有进行中的尝试、近一小时有计划日志）不替它迁移，留给那个窗口。

## 版本与升级（项目 TOP 自己的版本）

每个问答计划的根文件都带一个只增不减的 `top-version`（例如 `<!-- plan-format: qa · top-version=1 -->`）。它标识计划结构，不是项目的版本；只有需要迁移的结构变化才升版，普通文案调整不升。

- 新项目、`plan rewrite` 和空模板自动写当前版本。
- 接触一个已有项目先跑 `plan check`；提示 `TOP_VERSION_MISSING` 或 `TOP_VERSION_OLD` 时跑 `plan upgrade`。
- **没有版本号不能直接补数字**：`plan upgrade --apply` 会先按当前结构检查内容，只有没有硬错误才标记为当前版本。检查不过就先用 `plan check` 修内容。
- 旧版本只有在有对应迁移器时才 `--apply`；没有迁移器就停下来，不猜着改。
- 计划版本高于本 skill 时**报错并拒绝写入、不降级**：先更新 skill/CLI。
- 版本只升不降；已是最新时命令不改文件。迁移旧格式仍走 `plan rewrite … --to qa`。
- 不做全局巡检：每个窗口接触自己的项目时处理；别的窗口正在推进的项目不抢着升级。
- 升版时按顺序：改 `qa_format.PLAN_VERSION` → 同步 `templates/minimal` 和文档示例 → 补 vN→vN+1 迁移器及测试 → 用 `plan upgrade` 预览后再改真实项目。模板版本有测试守护，不会悄悄落后。

## 精简工作本（提示里出现"工作本过大"时）

上层只放摘要，原文下沉一层，AI 需要时再去查：计划只有问题和一句话答案；工作本放尝试和笔记；`_logs/` 放原文。

- 只在超过预算时做（工作本约 16KB，提示会点名），不定期做。
- 把工作本"笔记"里较早的小节逐节换成一两句摘要，原文原样移到 `_logs/<日期>-Q<n>-notes-archive.md`，摘要后附 `→ 原文：_logs/<文件>#<小节标题>`。答案和尝试是结构区，只经 plan 命令改，不动。
- 旧格式的大计划先升级成问答格式，再按这里精简；做完本地提交 `_top/`。

## 不变量

- 当前状态只有一个 owner：工作本里的问题状态、答案修订和尝试。目录里的问题摘要、`## 现在`、问题标题后的记号都是 CLI 生成的镜像，不手改、不在别处复制。
- 完成必须附证据（或写明无产物的原因）；答案必须附证据。写入在项目锁内进行，一次改动若让计划多出错误就整体拒绝。
- 一个事实只有一个真源，别处只放链接。
- 没有问题（或没有结构化任务）的计划是**轻量模式**：hint、doctor、compact 都不对它提维护要求。
- Hooks 只读、只提示：不改计划、不标完成、不替 AI 选任务、不自动提交；收尾提醒只在有进行中的尝试时出现，不要求解释"为什么不记"。用户当前请求优先，提示不是恢复旧任务的指令。
- 只对已启用的模块：改了 pipeline 接线后跑 `verify-pipeline`。

## 按需路由

| 场景 | 读取 |
|---|---|
| 问答式计划：写法、非线性记法、命令、文件格式、迁移 | [qa-plan.md](references/qa-plan.md) |
| 旧目录格式的写法与命令 | [plan-writing.md](references/plan-writing.md) |
| 命令全集、收尾细则、Hooks、TOP × Git、可选/旧工具、doctor/compact | [share-top-runbook.md](references/share-top-runbook.md) |
| 计划 schema、JSON 字段、CLI 参数与校验码 | [sixone-cli-design.md](references/sixone-cli-design.md) |
| 改动后该更新哪个真源 | [update-trigger-matrix.md](references/update-trigger-matrix.md) |
| 介绍、设计或优化方法；同步方法正文与框架图 | [methodology-workflow.md](references/methodology-workflow.md) |
| 知识树（可选跨列导航）：启用、新文档归到哪、摘要写法与过期、体检 | [knowledge-tree.md](references/knowledge-tree.md)（`doctree place / build / check`） |
| 查设计理由 / why、记录可复用决策 | [decision-memory.md](references/decision-memory.md) |
| Git 骨架：追踪边界、`track`、`.gitignore` 模板、trailer、git hooks、tag、交接、worktree、快照 | [git-version-lifecycle.md](references/git-version-lifecycle.md) |
| 交接 / 换窗口接手 | [交接与恢复](references/absorbed/mattpocock-handoff.md) |
| 论文模块接入、Auto Research 实验收尾 | [aris-research-integration.md](references/aris-research-integration.md) |
| 复杂功能的需求—任务—证据覆盖 | [spec-kit-coverage.md](references/absorbed/spec-kit-coverage.md) |
| 查现成代码 / registry / pipeline | CodeGraph + `_codemap.md`、[registry](references/registry-architecture-philosophy.md)、[pipeline](references/pipeline-registration-paradigm.md) |
| 测试方法 | [test-trunk-branch-leaves.md](references/test-trunk-branch-leaves.md) |
| 本项目日志、指标与验收证据在哪里；交接观测入口 | [项目观测入口](references/observability-check.md)；通用排障和补充观测能力由 `dev-toolkit`（可选，本包未包含）维护 |
| 旧/自定义 TOP 升级 | [share-top-upgrade-old](references/sub-skills/share-top-upgrade-old/REFERENCE.md)、[upgrades/](references/upgrades/README.md) |
| whole picture 网页 | [share-whole-picture](references/sub-skills/share-whole-picture/REFERENCE.md) |
