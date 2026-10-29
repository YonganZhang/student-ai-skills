# share-top Runbook

`SKILL.md` 只放最小流程；这里放命令全集和细则。CLI：`CLI=~/.claude/skills/share-top/scripts/sixone-cli.py`。

## 1. 我在哪（冷启动 / 接手）

- 唯一入口：`python3 "$CLI" plan show <项目>`。目录格式计划先给核心：`goal`、`phase`（第几阶段、名称、一句小结）、`phases`（整份目录）、`current`/`next`（带 gate）、`blockers`；此外还有最新认识、阻塞、最近任务笔记、`activity`（来自 Git 的任务提交 + note）、`last_handoff`（最近一次 `Handoff:` 提交）、计划更新后未记录的提交/改动、任务分支状态；计划超预算时带 `compact_hint`。
- `brief`、`top-status.py`、`topic-brief.py`、`top-brief.py` 保留兼容，但不再是必读；需要六列上下文或旧项目摘要时再用。
- 轻量模式：计划没有结构化任务（无 `## Active Work` 或没有任务行）时，直接读计划头部即可；工具不会要求迁移或维护。
- 交接或跨会话接手时，先按 [交接与恢复](absorbed/mattpocock-handoff.md) 核对真源和现场漂移；交接快照不替代计划。

## 2. 任务控制

**日常用短命令 `plan`**（`scripts/plan` → `top_plan_cli.py`，软链到 `~/bin/plan`）：查看输出几行人话，修改回一两行，`--json` 出原始 JSON；`plan help` 一屏速查。
- 项目选择：不写就用当前目录所在的项目；看别的项目写名字里的几个字、tmux 窗口号或路径；git worktree 归到主项目。改别的项目只接受 `-p <路径|窗口号>`。
- 老子命令（`show/list/validate/next/compact/inspect/handoff/milestone/merge/edit`），以及动词后面直接跟项目路径的老写法，都原样转给 `sixone-cli.py plan`（输出 JSON）。下面的长命令主要给脚本和计划看板用。

计划默认是**问答格式**（`## 目标` / `## 现在` / `## 问答`；每个问题一份工作本），问答计划的版本见 `plan check` 的 `top_version`；目录格式（`## 各阶段` 下的 `### P<n>` 阶段与步骤）继续可用，改写方法见 [qa-plan.md](qa-plan.md)「迁移」。语法与参数见 [sixone-cli-design.md](sixone-cli-design.md)。

```bash
python3 "$CLI" plan show <项目> [--fast]
python3 "$CLI" plan next <项目>                                   # 依赖已完成、未阻塞的待办（计划顺序）
python3 "$CLI" plan list <项目> [--state pending|in_progress|blocked|done|cancelled]
python3 "$CLI" plan inspect <项目> <ID>
python3 "$CLI" plan validate <项目>                               # 不变量 + 体积预算警告
python3 "$CLI" plan upgrade <项目> [--apply]                      # 检查/升级问答计划版本；无版本先检查内容
python3 "$CLI" plan goal <项目> "<一两句：做完是什么样>"                       # 目录格式
python3 "$CLI" plan phase add <项目> --title "<阶段名>" [--summary "<为什么做>"] [--after <P>]
python3 "$CLI" plan phase edit <项目> <P> [--title "..."] [--summary "<得到了什么，对下一阶段意味着什么>"]
python3 "$CLI" plan phase cancel <项目> <P> --reason "..."                       # 整段放弃：未关闭步骤全取消
python3 "$CLI" plan migrate <项目> <草稿> [--apply] [--accept-dropped]           # 整份换成目录格式（默认预览）
python3 "$CLI" plan add <项目> --id <ID> --title "<任务>" [--gate "<验收标准或命令>"] [--depends-on A,B] [--dep <ID>] [--scope <ref>]
python3 "$CLI" plan add <项目> --parent <阶段或步骤ID> --title "<子任务>"
python3 "$CLI" plan edit <项目> <ID> [--title "..."] [--add-gate ...] [--add-dep ...] [--add-scope ...] [--remove-*]
python3 "$CLI" plan insert <项目> <AFTER_ID> --title "<任务>" [--gate ...] [--reason "..."] [--rewire]   # 插一步：<AFTER_ID>a
python3 "$CLI" plan replan <项目> <ID> --reason "..." --replace-with "<替代1>" [--replace-with "<替代2>"] [--gate ...]  # 换路线
python3 "$CLI" plan start|reopen <项目> <ID>
python3 "$CLI" plan note <项目> "<一句话>" [--kind progress|fail|learn] [--id <ID>]
python3 "$CLI" plan complete <项目> <ID> --evidence <ref> --commit [--merge] [--decision <决策路径>]
python3 "$CLI" plan handoff <项目> <交接文档> [--no-commit]         # 文档+日志一起提交，带 Handoff: trailer
python3 "$CLI" plan milestone <项目> <phase> [--allow-open]        # annotated tag top/<phase>，消息为阶段任务摘要
python3 "$CLI" plan block|cancel <项目> <ID> --reason "<原因>"
python3 "$CLI" plan archive <项目> [--keep 5]                     # 已关闭任务移到 _logs/plan-archive.md
python3 "$CLI" plan compact <项目> [--apply]                      # 流水段移到 _logs/<日期>-journal-archive.md
```

- 开工写清验收：`--gate` 可以是 `test:<id>`、命令（`pytest -q tests/x.py`）或一句可判定的标准；`plan show`/`plan start` 的 `next_hint` 会带出它。
- 完成附一次证据：`plan complete` 必须有 `--evidence` 或 `--no-artifact-reason`；任务有 gate 而证据里没引用它时，返回 `gate_reminder`（不拦截），把 gate 的验证结果补进证据或 `plan note`。
- 一个计划最多一个 `in_progress`；依赖未关闭不能 start；没有 remove，路线淘汰用 cancel 留理由。
- `plan add` 发现同 scope 或标题相近的开放任务会给 warnings，先确认是否重复。
- 改计划：`plan insert` 把同级新任务放在 `AFTER_ID`（含子任务）之后，ID 为 `<AFTER_ID>a/b…`（不改任何已有 ID）；`--rewire` 让新任务依赖 `AFTER_ID`，原来依赖它的待办/阻塞任务改依赖新任务。`plan replan` 把任务标为取消（`换路线：<原因>`），在原位置插入串联的替代任务，依赖它的待办/阻塞任务改依赖最后一个替代任务，并记一条 `--kind fail` 笔记。两者都返回三行 `change_summary`（改了什么 / 为什么 / 影响哪些后续任务），原样转告用户。
- 3 次失败协议：同一任务第 3 条 `note --kind fail`（含 replan 自动记的那条，跨全部日志计数）时返回 `escalate: true`：停下找用户，列出试过的三种做法和各自结果。
- 写入是 compare-and-swap + atomic replace；并发变化时拒绝覆盖，重读后再做。
- 记录与接手正文先写对象、结果、原因与下一步（[可读性规则](decision-memory.md#记录和汇报要让接手者读懂)）。

## 3. 收尾（最多 4 步）

本轮推进了长周期任务时，在最终回复前：

1. `git status --short`（需要时 `git diff --name-status`）看实际改动。
2. 只在改了入口或数据时更新项目**已启用**的登记：代码入口 → `_codemap.md` + `_meta/_registry.yml`；数据资产 → `_meta/_data_registry.yml`；可复用的理由/教训 → `record add decision --file <路径::符号>`。代码结构不手写（CodeGraph 实时给出）。其余不动。
3. 完成尝试：核对实际结果、验证证据和对应改动，`plan done <ID> "结果" --ev … --commit`（旧接口为 `plan complete <项目> <ID> --evidence … --commit [--decision <决策路径>]`）。问题答清后再 `plan answer <QID> "结论" --ev …`；没完成就 `plan note` 记进展、卡点和下一步。
4. 回复里写清更新了哪些真源；预期该更新却没更新的，说明原因。

需要额外确认时再跑 `python3 "$CLI" doctor <项目>`：只查死链（AGENTS.md/CLAUDE.md/_codemap.md 相对链接 + typed ref）、登记路径是否存在、plan validate、未记录的提交/改动（不带 `Task:` trailer 的提交才算未记录）；pipeline 印记默认不查，需要时加 `--full`（旧 CodeBook 新鲜度也只在 `--full` 里，仅供参考）。没有结构化任务的项目不会被提维护要求。

## 4. 计划瘦身

计划是恢复卡，不是日记。`plan validate` / `doctor` 对以下超预算给**警告**（不阻断），并附建议命令：

| 预算 | 超出时 |
|---|---|
| 计划 >30KB | `plan compact` 预览 → `--apply`；已关闭任务多时再 `plan archive` |
| 单任务行 >500B | 任务行只放标题 + dep/scope/gate/ev 引用，细节写 `_logs/` 或证据文件 |
| scope 合计 >300B | scope 写 `path:`/`symbol:`/`registry:` 引用，不写说明文字 |
| note / Latest learning >300 字 | 一句话结论 + 证据路径；长复盘写 `_logs/<日期>-<主题>.md` |

超重计划的推荐顺序：① `plan compact <项目>` 预览，确认移出的都是流水/历史段后 `--apply`；② 已关闭任务多时 `plan archive <项目> --keep 3`；③ 还超就按 `validate` 的 `PLAN_TASK_LINE_LONG` / `PLAN_SCOPE_LONG` 提示用 `plan edit` 收短任务行。新项目用问答格式（`templates/minimal` 已是问答格式空计划），计划自然保持短；旧格式按 SKILL.md「升级旧计划」迁移。

`plan compact` 规则：保留标题、stamp、Done Criteria、Current Coordinate、Active Work 的任务行；把标题带日期或以“历史/旧/History”开头的段落、>2KB 的其它段落、Active Work 内不含任务行的带日期小节、>1KB 的说明长行、>1.5KB 的文件头长说明，**原样**移到 `_logs/<日期>-journal-archive.md`，计划末尾留一段 `## 历史索引`。默认只预览；`--apply` 先写归档再 CAS 写计划，冲突时回滚归档；如果移动会改变计划解析结果（stamp/坐标/任务/Done Criteria），直接拒绝。不要在别人正在使用的计划上未经确认 `--apply`。目录格式计划的 `目标`/`现在`/`各阶段` 从不被移动；做完的阶段用 `plan archive` 收起（步骤移到 `_logs/plan-archive.md`，标题和小结留下）。

## 5. Hooks

Claude 与 Codex 共用 `scripts/top-session-hint.py`（注册：Claude `~/.claude/settings.json` 的 SessionStart / Stop / UserPromptSubmit；Codex `~/.codex/hooks.json` 同三事件，按 Codex 文档完成 hooks 信任）和 `scripts/top-edit-hint.py`（PreToolUse：Claude matcher `Edit|Write|MultiEdit|NotebookEdit`，Codex matcher `apply_patch`）。全部只读、出错不阻断，会话状态存 `~/.cache/top-hooks/`，不写项目：

1. 启动/恢复时放一条 `【TOP 主线】`：问答格式给目标、已答清几个问题、正在弄清的问题与当前判断、正在做、下一步、需要你、24 小时内的失败；目录格式计划给目标、第几阶段 + 阶段小结、正在做、下一步、卡点、24 小时内的失败；旧格式给阶段、当前或下一步、最近笔记或心得、卡点；都带任务分支和版本状态（2026-10-16 起不再报“计划更新后未记录的提交/改动”）；计划超 30KB 时加一句“计划过大，可运行 plan compact”；轻量模式只说“轻量模式”。
2. 上下文压缩后（SessionStart `source=compact`）改放 `【TOP 恢复卡】`（≤800 字：目标、当前任务 + 验收、下一步、上次失败、心得、卡点、计划路径）。PreCompact 事件也输出同一张卡，但 Claude 只把 PreCompact 的 stdout 写调试日志、Codex 忽略其纯文本，所以模型看到的是 SessionStart(compact) 那份；不需要额外注册。
3. 每轮用户消息前一行 `【TOP 当前】`（问答格式：正在弄清的问题 → 当前判断 → 正在做/下一步 → 需要你 → 24 小时内的失败，按优先级整段取舍；目录格式：第几阶段、正在做、下一步、卡点、24 小时内的上次失败，不带零碎笔记；旧格式：当前任务、下一步、24 小时内的上次失败、最近笔记；≤200 字，超出截断但保留尾注；只含稳定字段，便于缓存；刚放过主线提示的那轮跳过；`TOP_INJECT=off` 关闭）。
4. 每轮结束时，只有**有一步正在进行**、本会话又改了项目文件或提交了代码、而计划（含问答工作本）和当日日志都没动时，才给一条 `【TOP 收尾提醒】`，点名那一步（不拦截，下一轮转给 AI 一次；同一批改动只提醒一次）。没有进行中的一步就不提醒：短的、碎的、跟长期目标无关的改动本来就不进计划（2026-10-16）。轻量模式项目不提醒。可选完成门：`git config top.stopGate true`（仓库或全局）后，若进行中任务声明了 gate，提醒改为 `【TOP 收尾提醒·完成门】`，点名该任务与验收、给出 complete/note 两条路——仍只提醒、不阻止结束；默认关闭。
5. 编辑 TOP 项目里的文件前（TOP 自己的 `_wiki-methodology/` 除外），`top-edit-hint.py` 调 `record for-file`：有相关决策/经验才以 `hookSpecificOutput.additionalContext` 给出 `【TOP 相关决策】`（最多 3 条：标题、日期、路径、命中原因、是否已被取代），不拦截；每个文件每个会话只查一次；纯本地（有界扫描记录 + 一次 `git log`，约 0.1 秒）。`TOP_EDIT_HINT=off` 关闭。

边界：hook 不改计划、不标完成、不替 AI 选任务、不自动提交；用户当前请求优先。收到收尾提醒时，推进/完成了那一步就用 plan 命令记录；改动跟它无关就不用管，也不用解释。历史上的整份 brief 注入、每轮整段 stamp、PostToolUse、Stop 拦截闸已下线，不要恢复。

Git 侧另有全局 git hooks（`git-hooks/`，由用户通过 `install.sh install` 设置 `core.hooksPath`）：先原样执行仓库自己的 hook，再 fail-open 地给任务期间的提交补 `Task:` trailer、提交后后台 `codegraph sync`。细节见 [git-version-lifecycle.md](git-version-lifecycle.md)。

## 6. TOP × Git

- Git 是骨架，TOP 只记意图、当前坐标、决策理由；trailer 与 tag 约定见 [git-version-lifecycle.md](git-version-lifecycle.md)。
- 任务完成且验证过：`plan complete <项目> <ID> --evidence … --commit`，把该任务 scope/gate/证据里 `path:`/`test:` 或裸路径下的改动（证据引用的仓库内、未被忽略的文件，含不带斜杠的文件名与仓库内绝对路径）与计划、整个 TOP 目录（finding、决策、日志等；凭证/缓存/临时/大文件除外）一起本地提交（`Task: <ID>` trailer；`--decision <路径>` 另加 `Decision:` trailer 并把决策文件放进同一提交；不 push；不碰别人暂存的文件）；提交后短 SHA 回写到当天日志那一行（`commit=<sha>`）。scope 外剩余改动会列出并按 `track` 分类计数（写出来却没进 Git 的给样例和 `track_hint`）。含空格的 gate（命令/标准）不当路径。
- 交接：`plan handoff <项目> <交接文档>` 提交文档 + 日志（`Handoff:` trailer）；接手时 `plan show` 的 `last_handoff` 指出它。
- 阶段收尾：`plan milestone <项目> <phase>` 打 annotated tag `top/<phase>`（有未关闭任务拒绝；已有 tag 不移动）。
- 需要隔离时（经用户同意）`plan start <项目> <ID> --worktree` 建 `task/<ID>` 于 `.worktrees/<ID>`；计划永远只在主 worktree 更新；完成用 `complete --commit --merge` 合回并清理，冲突则中止并报告。
- `start|complete|block|cancel|reopen|note|insert|replan|archive|compact` 成功后自动在 `_logs/<YYYY-MM-DD>-plan.md` 留一行（含 `git=<分支>@<短HEAD>(+N dirty)`），`--no-log` 关闭。
- 版本快照、实验晋级与归档：[git-version-lifecycle.md](git-version-lifecycle.md) 的 `version status/capture/verify/compare`。

## 7. 认知保护

- 改重要接口、方法或架构取舍前，按 [decision-memory](decision-memory.md) 查相关决策；只记录可复用的理由。
- 改公式、参数、主要步骤或策略前，重读 `plan show`（不要整份读 `_task_plan.md`）。
- 工具调用超过 80 次或目标变模糊时，自问：任务、阶段、下一步、错误、决策。
- 卡住时按 SKILL.md「中途」的 3 次失败协议升级（修 → 换方法 → 重新想/`plan replan` → 找用户），不重复已失败的同一动作；每次失败 `plan note --id <ID> --kind fail "<做法 → 结果>"`，可复用教训用 `--kind learn`。
- 每看两次资料（网页、PDF、图片、长输出）就把发现写盘：`record add finding` 或 `plan note --kind learn`。
- 阶段标签保持诚实：`P0/P1/P2` 主阶段，`P1.5` 修补，`P1.6.a` 批次；后面发现前面的问题就开新的修补子阶段，不静默改旧状态。

## 8. 代码导航（CodeGraph + `_codemap.md` + 决策记忆）

CodeBook 已退役（2026-09-24）：结构交给 CodeGraph（实时、零维护），`_codemap.md` 只写一页纸用途与入口（≤5KB，入口变了才更新），理由写决策记录的“涉及代码”（`路径::符号`），改文件前 `record for-file <项目> <文件> [--symbol X]` 找回。已有 `_codebook/` 当普通文档只读；`deposit` 只输出退役提示，不再写 `last_verified_hash`。


- 健康：`codegraph status -j <项目>`；缺索引时按 CodeGraph 官方文档初始化（配套的 semantic-scan 脚本本包未包含）。
- 任务联动：Active Work 写 `scope=path:...` / `scope=symbol:...` / `gate=test:...`，再 `python3 "$CLI" affected <项目> --task <ID>`；它不是全仓扫描。
- 只有用户明确说“扫描模式 / 语义扫描 / 全局扫描 / 重建 codemap”才加载代码语义扫描技能（可选，本包未包含）；扫描结论仍需源码和测试核验。
- 图谱发现的可复用轮子，接受后记进已启用的 `_codemap.md` 或 `_meta/_registry.yml`。

## 9. 可选与旧工具（不在必须流程里）

这些脚本保留兼容，只在用户要求或确有需要时跑；输出是线索，不是报完成的前置条件。

| 工具 | 用途 | 状态 |
|---|---|---|
| `sixone-cli.py doctor --full` / `topic-doctor.py` | 旧版全量体检：state drift、wiki/tests 缺层、SSDO、根目录杂物、sandbox 索引 | 可选 |
| `doctree.py` | 知识树：跨列主题导航的 build / check / place / show / summaries stamp（[knowledge-tree.md](knowledge-tree.md)） | 可选；项目有 `_meta/_doc_tree.yml` 才生效 |
| `topic-closeout.py` | 按 git 改动猜该更新哪些 owner | 可选 |
| `top-lint.py` | phase 文件、finding 形状等旧式 lint | 可选/旧 |
| `finding-doctor.py` | findings / external reviews 生命周期 | 可选/旧 |
| `top-gate.py` | 聚合上面几项 | 可选/旧 |
| `tidy.sh`、`lint-fs.py` | 散落文件/三件套 LEDGER 体检（用户说“整理/tidy/文件乱了”时） | 可选/旧 |
| `v4-cleanup.sh` | 顶层 `_` 前缀命名扫描（规则见 [v4-naming-architecture.md](v4-naming-architecture.md)） | 可选/旧 |
| `audit-rot.sh`、`purge-to-legacy.sh` | 死代码候选与归档（见 [col4-lifecycle.md](col4-lifecycle.md)） | 可选 |
| `brief`、`top-status.py`、`topic-brief.py`、`top-brief.py` | 其它“我在哪”摘要 | 兼容保留；以 `plan show` 为准 |
| `top-hygiene.py` | worktree/分支/stash 清单（hook 在超限时指向它） | 可选 |
| `top-update.py` / `record add` | 结构化 finding/decision/log | 可选 |

结构性重整（“项目臃肿 / AI 看不清 / 一团乱”）走 [reform-protocol.md](reform-protocol.md)，先给方案、等用户批准。profile 选择见 [profiles.md](profiles.md)。旧/自定义 TOP 升级走 [share-top-upgrade-old](sub-skills/share-top-upgrade-old/REFERENCE.md)，不混进日常流程。

## 10. 新项目

```bash
bash ~/.claude/skills/share-top/scripts/init-research.sh <项目目录>                     # 必需部分 + research 常用目录
bash ~/.claude/skills/share-top/scripts/init-research.sh <项目目录> --kind dev          # 必需部分 + _meta _sandbox _tmp _legacy
bash ~/.claude/skills/share-top/scripts/init-research.sh <项目目录> --with codemap,registry # 补可选模块
```

常用目录各带一份五问 `_readme.md`（放什么/不放什么/入口/文件角色/改动原因去哪查）；dev 项目的模块目录按需自建，README 用 `templates/dir-readme.md`。已有计划的项目给 `--kind` 只补缺的目录与 `.gitignore` 基线，只给 `--with` 不补目录。可选模块：`codemap registry data-registry decisions wiki tests pipelines dirs`（`codebook` 已退役：仍接受该参数，只提示不创建）；`full` 仅为兼容旧的整套 v4 骨架。不覆盖已有文件。启用模块后在 AGENTS.md「真源入口」加一行指针。

## 11. 边界

| 系统 | 负责 | 位置 |
|---|---|---|
| share-top | 计划、日志、可选的登记与知识模块 | `_wiki-methodology/_top/`（必需）及启用的可选模块 |
| codegraph | 符号导航、调用图、影响面 | `codegraph` CLI |
| `AGENTS.md`（Claude/Codex 共读） | 项目身份、不变量、真源指针 | 项目根；规范见 [claude-md-spec.md](claude-md-spec.md) |
