# share-top 演化记录

> 主 SKILL.md 是手册（"怎么做"），本文件是日记（"什么时候加了什么"）。两者分离避免互相污染。

---

## 2026-10-23 项目计划结构版本

- 问答计划根文件新增 `top-version=<n>`（由 `qa_format.PLAN_VERSION` 定义）；版本只增不减，标识计划结构，不随文案改动。
- `plan check` 报 `TOP_VERSION_MISSING` / `TOP_VERSION_OLD`，更高版本计划报 `TOP_VERSION_NEW` 并拒绝写入；SessionStart 提示缺失或落后版本。
- 新增 `plan upgrade [--apply]`（短命令和 `sixone-cli.py plan upgrade`）：无版本时先按当前结构检查内容，无硬错误才标记；旧版本需要迁移器；新版本不降级。
- 新模板、`plan init`、`plan rewrite` 自动写当前版本；报销项目已作为首个试点升级到 v1。
- 不做全局巡检：各窗口接触自己的项目时处理。

## 2026-10-22 开发阶段外援审查按范围触发

- `dev-mode-handbook.md` 的 SW-5、WF-2、流程图和场景示例统一为：长周期且需整体复核的阶段、重要或核心阶段需要外援，普通小阶段由主控检查；阶段名称、单纯耗时和普通元反思不触发外援。提供方与轮次沿用外援入口和渐进式审查；论文返修的四家 AI 试审流程保留。

## 2026-10-18 知识树（可选派生导航）

- 新增 `scripts/doctree.py` 及 `doctree_model / _scan / _check / _render / _place`：项目有 `_meta/_doc_tree.yml` 才生效，按主题生成 `TREE.md`、节点页和平铺 `CATALOG.md`，文档不搬不改；`references/knowledge-tree.md`。
- 一个字段一个主人：节点在 `_doc_tree.yml`，逐份文档的 `topics`/`summary` 只在 `_meta/_doc_summaries.yml`，不读文档头部的树字段。摘要记 `source`（reviewed/auto）和 `reviewed_sha`，`check` 报 `SUMMARY_MISSING`/`SUMMARY_STALE`/`SUMMARY_AUTO`，复核后 `summaries stamp`。
- build 与 check 共用一份生成物清单，只清理带派生标记的页；手写 `INDEX.md` 不替换。topic-brief / topic-doctor 只在启用时多出 `tree` 与 `TREE_*`。
- 起因与证据：一个大项目的试点（约 600 份文档、110 份上树）与 Codex、Gemini 对设计稿的审查；推广到别的项目前还要做同语料、同摘要的独立导航对照。
- 实现审查后加固：`summaries stamp` 走项目锁、锁内重读、只改目标条目的两个值（其余字节原样），写前发现表被改过就退出 3；配置类型错误和非 UTF-8 一律走配置错误（退出 2）；节点 id 必须是简单名字，输出路径须在项目内且互不重名；新节点建议挂在最近节点的父节点下。表的读写移到 `doctree_summaries.py`。

## 2026-10-16 问答式计划（`plan-format: qa`）成为默认

- 起因：计划看板上的计划人读不懂。审计 63 个项目：计划被当成 AI 的工单账本（一个请求一步，某论文阶段 40 步、24 步跑题），"下一步/卡点"是机械推出来的空话，要人拍板的事没有位置。用户选定"问答目录"：一个项目是一串问题，人读问题和答案。
- 新增 `scripts/qa_format.py`（零依赖解析/渲染）、`top_qa.py`（视图、校验、项目锁写入）、`top_qa_cli.py`（`plan` 文本视图与写命令）、`top_qa_migrate.py`（`plan rewrite --to qa`）；`references/qa-plan.md`。
- 三层：目录 `_task_plan.md`（目标、顺序、焦点、下一步；问题摘要是镜像）、工作本 `_questions/Q<n>.md`（问题的真源：答清标准、答案修订、只追加的尝试、旧编号、笔记）、证据层不变。
- 非线性：做完的结果不改写；`add --from/--because` 记重跑来源，`done --supersedes` 显式替代，`reopen Q --invalid` 立即撤回答案并标作废，`flag` 给下游打 ⚠。焦点和下一步显式（`start` 设焦点，`focus --next`），不再从文件里猜。
- 只有长周期的工作进计划：会话开始不再报"N 个提交没记进计划"（所有格式）；收尾提醒只在有进行中的一步时出现，不再要求"说明为什么不记"。
- 兼容：旧格式与目录格式照常读写；`parse_plan()` 把问答计划的尝试当只读任务给 git hook（`Task: Q4.3`）、卡片和状态工具；旧写命令对问答计划一律拒绝。经 Codex 审查（`自己-待处理的事情` 项目 `_reports/_foreign_aid/20261016T034619__codex__306682/`）后定稿。
- 试点（两个项目迁移）后补：用迁移前的旧编号写入（`plan done P6.4 …`、`--on P6.4`）时，拒绝信息直接给出新编号，免得还拿着旧上下文的窗口卡住。

## 2026-09-26（续二）— 短命令 `plan`：看得省、改得省、跨项目统一

**做了什么**：
- 新增 `scripts/plan` + `top_plan_cli.py`，软链到 `~/bin/plan`：查看出几行人话（25 号实测：看当前阶段约 500 token，`plan show` 的 JSON 约 2200 token），修改回一两行，`--json` 出原始 JSON；`plan help` 一屏速查；常见英文错误翻成可照做的中文。
- 项目选择统一：不写 = 当前目录的项目；名字片段 / tmux 窗口号 / 路径；git worktree 归到主项目；改别的项目只接受路径或窗口号。`plan ls` 各项目一行。
- 老写法原样转给 sixone-cli；hook 与全局规则改为指向 `plan`；SKILL.md 精简并加「梳理六合一」流程。

**为什么**：用户希望计划的增删改查尽量 CLI 化以省 token，并能统一地查看别的项目。实测发现"查"才是大头：JSON 比计划文件本身还大。

---

## 2026-09-26（续）— 两层目录、每个阶段都能点开、标题写逻辑层

**做了什么**：
- 目录格式只有 阶段 → 步骤 两层：更深的步骤报 `PLAN_STEP_TOO_DEEP`，`plan add --parent <步骤>` 与 `--id P1.1.1` 被拒绝，补内容用 `plan insert`。
- 每个阶段都要有步骤：`migrate` 对标 ✅ 却没步骤的阶段报 `PLAN_PHASE_NO_STEPS` 错误，`validate` 对没有步骤（也没有归档步骤）的阶段给同名警告；`plan show` 的阶段带 `archived_steps`，卡片点开已收起的阶段也能看到步骤。
- 新增细节文章约定 `_top/_plan_details.md`（按阶段分节放技术细节、数字、编号、证据、旧编号对照），`plan show` 给出 `details`，卡片加"细节"标签页。
- 新警告 `PLAN_TITLE_TECHNICAL`：标题里有路径、编号、小数/百分比或成串英文术语。
- `plan-writing.md` 重写写法：三层内容（标题=逻辑层人话、小结=承上启下可带关键技术点、细节=细节文章）。

**为什么**：25 号试点后用户反馈：做完的阶段点不开（改写时按旧 SOP 省略了步骤）、三层嵌套没必要、标题仍偏技术——要人一眼看懂主线，碎片细节可以追问 AI。

---

## 2026-09-26 — 计划改成"目录"：人一眼能看懂主线

**做了什么**：
- 新的默认计划格式（目录格式）：`## 目标` / `## 现在`（CLI 生成：第几阶段、正在做、下一步、卡点）/ `## 各阶段`（`### P<n> <名称> <✅🔄⏸⏳✕>` + 一句承上启下的小结 + 一句人话的步骤）/ 关键问题 / 决定 / 错误。编号、依赖、验收、证据移进行尾 `<!-- -->`，渲染后看不见。
- 新命令：`plan goal`、`plan phase add|edit|cancel`、`plan migrate`（AI 写目录格式草稿 → 预览 → `--apply` 替换，旧原文进 `_logs/plan-history/` + 软链 `_task_plan.before-migrate.md`，旧计划里被丢下的未关闭任务须 `--accept-dropped` 确认）；`plan add --parent <阶段>`；`plan archive` 对目录格式收起已完成阶段的步骤、保留标题和小结。
- `plan show` 给核心字段（`phase`、`phases`、`blockers`、`questions`、`decisions`、`now_stale`、`format`；旧格式给 `migrate_hint`）；`validate` 加可读性警告（阶段 >7、标题过长、缺阶段小结、小结过长、阶段步骤过多、`## 现在` 被手改）。
- hook：目录格式计划的【TOP 主线】/【TOP 当前】/【TOP 恢复卡】只给目标、第几阶段 + 小结、正在做、下一步、卡点、24 小时内失败，不再塞"心得/上次进展"这类碎片。
- 新 `references/plan-writing.md`：人话、承上启下、只写往哪走；增删改查表；旧计划改写 SOP。最小模板换成目录格式。

**为什么**：用户在计划看板上看不懂各项目的计划、把握不住主线；对照上游发现 PWF 的计划本质是一份目录，而我们的旧计划把"往哪走"（计划）、"查到什么"（findings）、"做过什么"（progress）混在一个文件里，AI 每轮提示也被零碎笔记占满。

**兼容性**：旧格式（Active Work）照常解析、校验、读写，命令与 JSON 字段只增不删；旧计划不自动迁移，由各项目窗口按 SOP 用 `plan migrate` 改写。

---

## 2026-09-24（续三）— 吸收 planning-with-files：改计划、卡住升级、防遗忘

**做了什么**：
- `plan insert`（插在某任务子树之后，新 ID `<AFTER_ID>a/b…`，`--rewire` 改依赖）与 `plan replan`（取消 + 串联替代任务 + 依赖改到最后一个替代 + 自动 fail 笔记），都返回三行 `change_summary`。
- 3 次失败协议：同一任务第 3 条 `note --kind fail` 返回 `escalate: true`；SKILL.md「中途」写入修 → 换方法 → 重新想 → 找用户、不重复失败动作、每看两次资料就写盘。
- hook：【TOP 当前】加下一步与 24 小时内的上次失败（≤200 字）；压缩后（SessionStart compact，PreCompact 同出一份诊断副本）给【TOP 恢复卡】（≤800 字）；`git config top.stopGate true` 时对有 gate 的进行中任务用更强的收尾措辞（仍不拦截）。`plan show` 新增 `last_fail`。
- 最小模板改为阶段式（目标 → 下一步 → 阶段 → 决策 → 错误；阶段 = 父任务）。

**为什么**：PWF 的计划一眼能看懂、卡住时有明确的升级纪律、压缩后能接上；我们保留项目级 CAS、Git 骨架、完成附证据与每轮一行省 token。吸收对照与刻意不吸收的部分见 [absorbed/planning-with-files.md](absorbed/planning-with-files.md)。

**兼容性**：命令与 JSON 字段只增不删；已有计划不迁移；完成门默认关闭；hook 注册不变。

---

## 2026-09-24（续二）— Git 是骨架：CodeBook 退役，任务/决策/交接/里程碑挂到 Git

**做了什么**：
- CodeBook 退役：代码一块 = CodeGraph（结构）+ `_codemap.md`（一页纸入口）+ 决策记忆（理由）。`deposit` 只返回 `retired=true` 与迁移提示、不再写 `last_verified_hash`；`init-research.sh --with codebook` 只提示不创建；brief/affected 不再要求回写 CodeBook；已有 `_codebook/` 当普通文档只读（`doctor --full` 仍可读旧新鲜度）。
- 全局 git hooks（`git-hooks/`，`install.sh install|uninstall|status`，只动 `git config --global core.hooksPath`）：每个标准 hook 名先原样执行仓库自己的 `<git-common-dir>/hooks/<名>`（参数/stdin/退出码不变），再 fail-open 做 TOP 附加动作：`prepare-commit-msg` 给任务期间的提交补 `Task:`（`task/<ID>` 分支用分支名；主 worktree 用唯一 in_progress；merge/squash/amend/rebase/cherry-pick 跳过）、`commit-msg` 防止清空编辑器后只剩 trailer 被提交、`post-commit` 有 `.codegraph/` 时后台 `codegraph sync`。
- `plan complete --commit --decision <路径>`：`Decision:` trailer，决策文件与证据引用的仓库内未忽略文件（含无斜杠文件名、仓库内绝对路径）进同一提交；提交后短 SHA 回写当天日志那一行（`commit=<sha>`，日志因此多一处改动，随下一次计划提交入库）。
- `record for-file <项目> <文件> [--symbol X]`：按正文/“涉及代码”的路径、模块、符号和 `git log -- <文件>` 的 `Decision:` trailer 找相关决策/经验，最多 3 条，带 `superseded_by`；决策模板与 `record add decision` 增加“涉及代码”一节和 `--supersedes`。
- `scripts/top-edit-hint.py`（PreToolUse，Claude Edit|Write|MultiEdit|NotebookEdit，Codex apply_patch）：编辑 TOP 项目文件前以 `hookSpecificOutput.additionalContext` 提示命中的决策，不拦截，每文件每会话一次，约 0.1 秒。
- `plan show` 新增 `activity`（Git 的 Task 提交 + note）与 `last_handoff`；`unrecorded.commits` 只数不带 `Task:`/`Handoff:` 的提交（带的计入 `task_commits`），计划有未提交改动时以其修改时间为界。新增 `plan handoff`（`Handoff:` trailer）、`plan milestone`（annotated tag `top/<phase>`，从不移动已有 tag）；`plan compact` 在计划于 HEAD 干净时把原文所在提交写进历史索引。

**为什么**：机主要求六合一与 Git 紧密联动——Git 已经是版本与主线的记录器。实测 CodeBook 多数盖章过期、30 天内改代码前查过决策的会话只有 7 个、带 Task/Decision trailer 的提交 30 天仅 9 次：靠人记得去维护/查询不可靠，改为由提交与编辑时的 hook 自动挂钩。

**兼容性**：CLI 命令与 JSON 字段只增不删（`codebook_nodes_to_rewrite` 保留）；`deposit` 退出码 0；全局 hooks 需用户自行安装，未安装时一切照旧；仓库自己设了本地 `core.hooksPath` 时全局 hooks 不生效。

## 2026-09-24（续二）— 提交带对话号；提交前拦大文件与凭证

- 全局 `prepare-commit-msg` 追加 `Session: <provider>:<会话号>`，TOP 项目默认、其它仓库 `top.sessionTrailer true` 开启，公开仓库设 `false`（已给 9 个公开远端的本机仓库设好）。
- 全局 `pre-commit` 在仓库自己的 hook 通过后拦超过 50 MB 的文件与像真凭证的新增行；`TOP_ALLOW_LARGE=1` / `TOP_ALLOW_SECRETS=1` 单次放行；检查器出错不拦。
- tests/conftest.py：测试与机器的全局 git 配置、当前 AI 会话隔离。

## 2026-09-24（续）— 瘦身留原文；CodeBook/pipeline 印记移出默认 doctor

- `plan compact --apply` 先把瘦身前的完整计划原样存到 `_logs/plan-history/<时间>-before-compact.md`，并在 `_top/` 放固定软链 `_task_plan.before-compact.md` 指向最近一份；瘦身后的计划在历史索引里写明原文位置，`plan show` 给出 `before_compact` 字段。冲突回滚时连同原文快照与软链一起撤销。
- 默认 doctor 不再检查 CodeBook 新鲜度与 pipeline 印记（老项目上长期 stale 无人处理，淹没真问题）；需要时 `doctor --full`。

## 2026-09-24 — 精简：第一次就做对，收尾 4 步

**做了什么**：
- 计划减肥：`plan validate` 加体积预算警告（计划 >30KB、任务行 >500B、scope >300B、note/Latest learning >300 字，附建议命令）；新增 `plan compact`（默认预览，`--apply` 把按日期的流水段/超长历史原样移到 `_logs/<日期>-journal-archive.md`，计划末尾留短索引，CAS 写入 + 解析结果不变校验）；SessionStart 提示在计划超预算时加一句；runbook“改公式/参数前重读 task_plan.md”改为重读 `plan show`。
- 可选字段：`depends_on=A,B`（与 `dep=` 等价）、`plan add --depends-on`、`plan next`（依赖都已关闭的待办）、`plan add --gate "<验收>"`（show/start 的 next_hint 带出）、`plan complete` 对未引用 gate 的证据给 `gate_reminder`（不拦截）。
- 检查收敛：`sixone-cli.py doctor` 默认只查死链、登记路径存在、plan validate、未记录改动（`--full` 为旧版全量体检）；收尾改为 4 步；top-lint / finding-doctor / topic-closeout / top-gate / tidy / v4-cleanup / audit-rot / lint-fs 降为可选/旧工具；“我在哪”统一以 `plan show` 为准。无引用的 `fs-snapshot.sh`、`resolve-path.sh` 已退役（未随本包发布）。
- 六列只保留 canonical 一套定义；最小可行版本 = AGENTS.md（≤60 行）+ `_task_plan.md` + `_logs/`，其余为可选模块；新项目默认只建必需部分（`templates/minimal/`，`init-research.sh --with` 启用可选模块）。
- 轻量模式：没有结构化任务的计划，hint 不给收尾提醒、doctor 只给 info、compact 不动它。

**为什么**：实测计划被当日记（最大 328KB，坐标+当前任务只占小部分）、检查器 8 个以上且约一半项目长期报警无人理、一次普通改动要 18~20 步收尾。检查不产生质量；开工写清验收 + 完成时一次证据才产生质量。

**兼容性**：现有计划不需迁移；`dep=` 写法不变；`topic-doctor.py` 直接调用时默认行为不变（新增 `--core`）；旧工具都还在。

## 2026-09-23 — references / sub-skills 类层化

**做了什么**：按 `share-skill-creator/references/memory-to-sop.md`「内容分层」清理 references/ 与 references/sub-skills/：单项目约定移出（逐字原文另行存档，未随本包发布），历史来由移到本节，无来源目标值改写为判断标准。顶层 scripts/、tests/、core/、templates/、profiles/、SKILL.md 与 references/absorbed/ 未动（sub-skills 自带的模板只改了注释与头部说明）。

**为什么**：换一个项目，skill 规则仍要成立；单项目参数、日期和事故叙事留在规则里，会被当成通用约束。

以下是从规则正文移出的来由（行号指提交 `a6fec44` 的版本）：

- `six-in-one-philosophy.md:3` — 理念由用户 2026-06-09 多轮口述沉淀。
- `fs/runtime-facts-protocol.md:1,9-10,46-50` — 协议 2026-06-13 设立；起因是一个试点项目一轮内因 stale log 路径卡死录像 480s×2、因 persona 真源误判改了死配置（2026-06-12 两次）。正文改为去项目化反例。
- `skill-vs-prompt-decision.md:1,76-81` — 2026-05-08 设立；起因是一个试点项目把"测试引导 5 场景"塞进 system_prompt（1782 chars），重构为 skill 后 prompt 降到 896 chars。原 "1000 字符" 阈值同时改为内容类型判断。
- `lint-armor.md:3-4,117-124` — 2026-05-17 用户问"如何让 registry / wiki / 代码三者对齐每次 100% 可验证"而设立（任务 P3.5.j）。v1：10 道门，用户砍掉 L7/L10 → 8 道门；v2.1：吸纳 Codex + Gemini 审查，加 L5b stub_only（warn）、L8 archival_gate_check 由任意 bash 改为纯 Python 白名单、migration_status 强枚举；同日推到全局 share-top。
- `pipeline-registration-paradigm.md:36,60,121,127` — 印记自动失效机制 2026-06-15 移植自 CodeBook hash-trust；§11 "完整 inventory + 扣子默认视图" 于 2026-06-09 经 Codex + Gemini 两路审议定稿，"默认视图列全部函数必腐烂回噪音" 是两方共同警告。
- `research-discipline.md:6,171` — 2026-05-20 用户从软件模式手册 v2 挑出 3 条跨用规则改写为科研版。
- `dev-mode-handbook.md:5,476-482,488-492` — v2 经 Codex GPT-5.5 + Gemini 3.1 Pro Preview 双审清洗（2026-05-20）。v2 变化：新增 AR-1~4 通用架构范式（从原 §6 项目案例区抽出）、SW-2 补判定边界、QF-5 改为按项目类型选 e2e 形态、核心条目补 TDA 四件套、§7 升级为 4 Recipe、删除项目日记残留。来源是一个互动小说类软件项目 Phase α MVP 完工后的 42 条元协议（映射表已移出）。本次另把 SW-4 "覆盖率 ≥ 80%" 与 SW-6/WF-6 "N/10 自评分" 改为可数证据。
- `test-trunk-branch-leaves.md:101,113-115,149` — 反例表来自 2026-05-13 用户痛点；阶段定位机制来自同日用户设想，原话：「我不用 AI 自己定位视频哪一帧哪一秒,我只要 AI 自己知道是哪个阶段就行了。它为什么知道是哪个阶段呢?它可以去查 workflow 里面的阶段进展嘛。」；反模式速查沉淀于 2026-05-13 实战 Run 6-10。
- `registry-architecture-philosophy.md:3-19,119,174,191,206,227,238,250,259` — v1 由 2026-05-22 用户元层质疑触发（"为什么 cc 自己面对问题不查注册架构?…反哺 share-top skill"），沉淀一个项目的 8 个坑；v1.1（同日）综合 R10+R11+R12 三路审议：原则 11 自举验证（R12 subagent）、原则 12 唯一标识（R10 Codex）、原则 13 物理对齐（R11 Gemini）、原则 14 证据新鲜度（R10 Codex），"deprecated 必有继任者" 升为原则 7 硬约束（本次写回原则 7 正文）；原则 4 的 wip、原则 8/9 来自 Gemini R09；原则 15 于 2026-05-27 从一个 pipeline 项目实战提炼。
- `sub-skills/share-whole-picture/references/legacy-whole-picture-guide.md` — 旧指南 v1（2026-05-17）首次沉淀，v1.1 同日吸纳 Codex + Gemini 三方审查（Data+Renderer 两层、未确认标记、CSS 炫技禁令、商业扩展）；R1–R31 编号规则多由 2026-05-17/18 用户 audit 与拍板形成（如"第六架构不需要实时更新"、"picture 是查验 + 学习工具,不是 changelog"、平行节点不连线）。本次重写为类层版本，原文存档。
- `sub-skills/share-whole-picture/templates/details_native_picture.html:4`、`binary_tree_deep.html:2` — 2026-05-17 实测：mermaid click / JS 抽屉在用户手机失败后改用原生 details。
- `sub-skills/share-top-upgrade-old/references/migration-tools/README.md:53-57` — `rename_wiki_to_underscore.py` v1（2026-05-17）首版，在一个项目上跑通（129 R + 19 M + 5 A + 4 D / +1228 -779 lines）。
- `reform-protocol.md:50`、`arch-doc-guide.md:65` — 去掉 "(Codex 强调)"、"(踩过坑)" 等来源标注。

## 2026-09-18 — 按需决策记忆

扩展既有 record CLI：保存需求、理由、代码、来源及验证陈述；新增有界本地关键词检索，默认三条摘录。全局仅保留重要取舍的流程指针，取消按读文件数量强制写发现。缺验证/来源不推断成功或提交归属。机制参考 Atlas，未安装或复制其运行时。

## v4.6 — 计划控制面 CLI（2026-09-01）

**做了什么**：为 `_task_plan.md` 增加 Active Work/Current Coordinate schema、原子 CRUD、证据门、owner/record 查询和 `affected --task` 的 CodeGraph 联动；全局规则只保留 `plan show` 短入口。

**为什么**：动态进度不能写死在全局规则，也不能依赖 hook 或聊天记忆；Markdown 保持真源，CLI 提供可校验、可扩展且不丢历史的操作层。

## v4.2 — COL4 默认从函数账本改为代码域/入口账本（2026-06-06）

**做了什么**：`_meta/_registry.yml` 新项目默认登记代码域、入口、工具和跨域边界；函数级 `register.py/lint.py/sync_wiki.py` 模板改为 fail-loud placeholder；v4 模板补 `_wiki/`、`_tests/` 和 `_six_dim_contract.md`。

**为什么**：大型 wrapper / 多子仓项目不适合默认函数级注册；旧自动扫描会把 registry 写回函数账本,制造双真源和假自动化。

## v3.5 — contracts 收编到 COL 5 fs 子目录（2026-05-15）

**做了什么**：把 `contracts/` 从顶层 COL 6 改为 `fs/contracts/` 子目录。

**为什么**：接口契约本质是约定（跟 `fs/governance/`、`fs/naming-rules.md` 同性质），不是新独立维度。原 v3.4 单立 COL 6 是过度建模——"五合一"保持原 5 列不变。

## v3.4 — 接口契约 + L1 入口卡（2026-05-13）

**做了什么**：
- 加 `contracts/` 目录：API/Schema/Pipeline 契约**单一真源**，防"接口在 5 个文件各写一份漂移"（v3.5 已并入 `fs/contracts/`）
- 加 L1 入口卡 `00-OVERVIEW.md` / `00-API-MENU.md`：给非维护者（老板/客户/前端/接手 cc）5 min 速读

**为什么**：项目变复杂后接口契约在多个文件漂移，非维护者读 SKILL.md / wiki/ 看不懂"项目是什么"。

## v3.3 — Reform Protocol（2026-05-13）

**做了什么**：每次"更新五合一"主动跑 8 项 audit，根据通过数决定走 Tidy 还是 Reform。
- 7-8 过 → 健康
- 4-6 过 → 小修
- ≤3 过 → 启动 Reform 5 Phase

**为什么**：项目级 reform 经验沉淀——单个 tidy.sh 治标不治本，臃肿项目需要分 phase 重整。

## v3.2 — 阶段感汇报协议（2026-05-08 末）

**做了什么**：阶段命名约定 P0/P1/P2/P3 + P1.5/P2.3 + P1.6.a/b 分级；后续 phase 发现前面问题 → 新建 P<N>.<m> 推延记录，永不改原 P<N> 的 ✅ 标。

**为什么**：偷偷改回前面 phase 的状态会让用户失去对真实修复成本的掌控。

## v3.1 — 反硬塞铁律（2026-05-08 后期）

**做了什么**：给 LLM 加文档型内容（SOP / FAQ / 测试引导 / 能力总览 / 接入文档）时**必走 Skill，不糊 persona prompt**。

**为什么**：硬塞进 persona prompt 会让 prompt 越来越厚、检索失效；Skill 容器自带 description + 触发机制。

## v3 — SKP + claude-context MCP（2026-05-08）

**做了什么**：
1. **Skill-shaped Knowledge Pack (SKP)**：大型外部文档用标准 Skill 容器承载（`SKILL.md + INDEX.md + sources.lock + references/`），让 claude-context MCP 命中"高密度入口卡"
2. **claude-context MCP 主动使用**：陌生代码库查概念/架构必先 `search_code`，再 `rg/Read` 验证
3. **索引健康协议**：`.codex/semantic-index.lock` 记录 indexed_commit，落后 HEAD 时 search_code 结果只当线索不当事实

**为什么**：陌生代码库直接 `rg` 抓不到语义，需要 MCP 语义层索引介入。

## v2.3 — 工具集 + tidy.sh + 三件套画图特化（2026-05-03）

**做了什么**：v2.1 工具集（manifest.yml / fs-snapshot / resolve-path / lint-fs）+ tidy.sh + "更新五合一"标准动作 + 三件套画图特化。

## v2.1 — CLAUDE.md 规范（2026-04-29）

**做了什么**：CLAUDE.md 规范定型 — 项目身份 + 不变约束 + 五合一入口指针，总行数 ≤ 60；禁写状态/知识/反面教材展开。

**事故起源**：项目 CLAUDE.md 写"当前 V21"实际 V25，cc 抓错版本日志误判 LLM 评分。

---

## 写本文件的规矩

- 只记录**结构性变更**（新增 COL / 新协议 / 新铁律）
- 不记录 bug 修复、措辞调整等细节
- 每条 ≤ 5 行：做了什么 + 为什么
- 不用"血泪""吸收""审吸收"等日记词典
