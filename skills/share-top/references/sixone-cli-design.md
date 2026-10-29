# Sixone CLI — 完整命令与架构手册

当前运行时是本地 CLI：无常驻 MCP server、无项目 `.mcp.json`；hook 是 `scripts/top-session-hint.py`（启动主线提示 + 压缩后恢复卡 + 每轮一行当前任务 + 收尾提醒，只调 `plan show` 与只读 git 查询，不写项目文件）和 `scripts/top-edit-hint.py`（编辑前相关决策）。Markdown 仍是人和 AI 都能直接审阅的真源；CLI 负责有界读取、校验和受控写入，不创建第二套数据库。

## 1. 心智模型

```text
进入项目  plan show（“我在哪”唯一入口）
    ↓
选任务    plan next；新任务 plan add --gate "<验收>" [--depends-on A,B]
    ↓
开始任务  plan start [--worktree]
    ↓
定位影响  affected --task + owner resolve
    ↓
中途记录  plan note（进展 / 失败 / 心得）
    ↓
记录证据  record add / 测试产物
    ↓
关任务    plan complete --evidence <gate 结果> --commit [--merge]
    ↓
按需核验  doctor（死链、登记路径、plan validate、未记录改动）
```

唯一入口：

```bash
CLI=~/.claude/skills/share-top/scripts/sixone-cli.py
python3 "$CLI" --help
```

所有命令输出 JSON。正常或可用警告退出 0，可信度阻断退出 1，参数/运行错误退出 2。不要只看文本中出现 `ok`，自动化应同时检查退出码和 `verdict`。

## 2. 命令树

```text
sixone-cli.py
├── brief
├── doctor
├── plan show|next|list|validate|inspect|add|insert|replan|edit|start|note|complete|block|reopen|cancel|merge|archive|compact|handoff|milestone
├── affected
├── owner list|show|resolve
├── record add|list|show|search|for-file
├── deposit            （已退役：只输出提示，不盖章）
└── verify-pipeline
```

`scripts/sixone-cli.py` 是薄壳；通用读逻辑在 `core/sixone_core.py`，计划解析/CAS 在 `scripts/top_common.py`，各命令域分别由 `top_plan.py`、`top_owner.py`、`top_record.py` 实现。退役 FastMCP 代码未随本包发布。

## 3. 项目发现

`<项目>` 可以是项目绝对/相对路径；既有 registry id 继续兼容。计划命令优先读取：

1. `_wiki-methodology/_top/_task_plan.md`
2. legacy-compatible `wiki-methodology/top/task_plan.md`

不存在时只报告错误，不静默创建未知结构。新项目应先走 share-top 初始化模板。

## 4. 计划真源 schema

### 4.0 问答格式（默认，2026-10-16 起）

根文件第二行 `<!-- plan-format: qa · top-version=1 · focus=Q<n> · next=… -->`；每个问题一份工作本 `_questions/Q<n>.md`。格式、命令与迁移见 [qa-plan.md](qa-plan.md)；实现：`scripts/qa_format.py`（解析与渲染，零依赖）、`scripts/top_qa.py`（视图、校验、带锁写入）、`scripts/top_qa_cli.py`（`plan` 文本视图与写命令）、`scripts/top_qa_migrate.py`（`plan rewrite --to qa`）。`sixone-cli.py plan show/list/validate/note` 对问答计划委派给 top_qa；`plan upgrade` 检查/升级结构版本；`plan question <项目> Q<n> [--full]` 出一个问题的 JSON。旧写命令对问答计划一律拒绝（`top_common.atomic_replace_plan` 是唯一闸门）。`parse_plan()` 把尝试当只读的 PlanItem 交给 git hook、卡片等旧消费者。

### 4.1 目录格式（2026-09-26 起；2026-10-16 后为旧格式之一）

给人看的一份目录（planning-with-files 的 `task_plan.md` 套路），写法与改写 SOP 见 [plan-writing.md](plan-writing.md)。

```markdown
# <项目> — 计划

## 目标
一两句：整件事做完是什么样

## 现在
<!-- plan 命令自动生成，不要手改 -->
- 阶段：第 2/3 阶段 · P2 查行情
- 正在做：P2.1 查往返机票
- 下一步：P2.2 查酒店
- 卡点：P1.2 等放假通知

## 各阶段

### P1 问清需求 ⏸
先问清人数和预算，后面按这里来。

- [x] P1.1 问清目标和约束 <!-- ev=findings.md#需求 -->
- [ ] P1.2 确认放假日期 <!-- state=blocked · reason=等放假通知 -->

### P2 查行情 🔄
- [ ] P2.1 查往返机票 <!-- state=in_progress · gate=findings 有两家报价 -->
- [ ] P2.1a 顺便查高铁
- [ ] P2.2 查酒店

## 关键问题
## 决定
## 错误
```

- 解析：有 `## 各阶段` 即为目录格式。阶段 = `### P<n> <名称> [记号]`；步骤 = 阶段下的勾选行，ID 必须以所在阶段 ID + `.` 开头（否则 `PLAN_STEP_OUTSIDE_PHASE`），阶段标题写不成 `### P<n> …` 报 `PLAN_PHASE_MALFORMED`，阶段 ID 重复报 `PLAN_PHASE_DUPLICATE`。元数据（`state`/`dep`/`scope`/`gate`/`ev`/`reason`/`no_artifact_reason`，含义同旧格式）写在行尾 `<!-- … -->`，段之间仍用 ` · `；标题与元数据值都不许含 `<!--`/`-->`。只有 阶段 → 步骤 两层：步骤 ID 只能是 `P<n>.<k>`（插入的 `P<n>.<k>a` 同级），更深报 `PLAN_STEP_TOO_DEEP`，`plan add --parent <步骤>` / `--id P1.1.1` 被拒绝并提示用 `plan insert`。技术细节写在同目录的细节文章 `_plan_details.md`（AI 自由维护，按 `## P<n> …` 分节，不经 CLI；`plan show` 的 `details` 字段给出其路径，卡片"细节"标签页显示它）。
- 阶段状态由步骤推导：有进行中 → 🔄；全部关闭 → ✅（全是取消 → ✕）；未关闭的全阻塞 → ⏸；有完成的 → 🔄；否则 ⏳。文件里没有步骤的阶段（未开工，或步骤已被 `plan archive` 收起）以标题上的 ✅/✕ 为准，其余视为 ⏳。当前阶段 = 有进行中步骤的阶段，否则依次取第一个 🔄、⏸、⏳ 阶段。
- `## 现在` 与标题记号是镜像：每次写操作按步骤状态重写；手改只报 `PLAN_NOW_STALE` 警告，不阻断。旧格式的 stamp / Current Coordinate / phase 前缀约束不适用。
- 阶段号：`plan phase add` 取计划里已用最大号 + 1（`plan archive` 保留标题，所以不会复用）；步骤号：`plan add --parent` 取未用过的下一个，含 `_logs/plan-archive.md` 里的 ID。

### 4.2 旧格式（Active Work，兼容）

计划的机器可读区只有两个：`Current Coordinate` 是恢复镜像，`Active Work` 是任务状态真源。

```markdown
🧭 当前 [P3.9] task=[P3.9.E2] 接入受控计划 CLI
> Done Criteria: CLI case、文档和项目实迁移均通过

## Current Coordinate
- Goal: 六库研究主线可持续恢复
- Current task: P3.9.E2 接入受控计划 CLI
- Next task: P3.9.E3 运行验收 case
- Latest learning: current state 必须和历史叙述分离
- Blocker: none

## Active Work
- [x] P3.9.E1 冻结协议 · state=done · ev=test:plan-parser
- [ ] P3.9.E2 接入受控计划 CLI · state=in_progress · dep=P3.9.E1 · scope=path:_code · scope=symbol:Controller · gate=test:unit
- [ ] P3.9.E3 运行验收 case · state=pending · dep=P3.9.E2 · gate=test:integration
```

任务元数据用 ` · ` 分隔；可重复字段是 `dep`、`scope`、`gate`、`ev`。依赖也可写成一个可选的 `depends_on=P3.9.E1,P3.9.E2`（逗号分隔，与 `dep=` 等价；CLI 回写时保留作者用的写法，两种混用时统一回写为 `dep=`）。`gate=` 可以是 `test:<id>`、命令或一句可判定的验收标准，但不能含 ` · `。状态只有 `pending`、`in_progress`、`blocked`、`done`、`cancelled`。完成项必须有 `ev=`，或明确给出 `no_artifact_reason=`；阻断/取消项必须有 `reason=`。

任务 ID 必须属于当前 phase，例如 phase `P3.9` 下使用 `P3.9.E1`、`P3.9.E1.1`。一个计划最多一个 `in_progress`。CLI 从依赖闭合的 pending 项推导 next，不维护可漂移的第二份 next 状态。

## 5. 恢复和查询

AI 和人日常用短命令 `plan`（`scripts/top_plan_cli.py`）：同一套 top_plan 函数，默认输出几行文字。`plan` 看核心；`plan 当前|上一|下一|全部|P<n> [--细节]` 看阶段；`plan ls` 各项目一行。写操作回一两行，外加一行"现在：…"。下面的 JSON 接口给脚本、hook 和计划看板。

```bash
python3 "$CLI" plan show <项目>
python3 "$CLI" plan list <项目>
python3 "$CLI" plan list <项目> --state blocked
python3 "$CLI" plan inspect <项目> P3.9.E2
python3 "$CLI" plan validate <项目>
python3 "$CLI" plan upgrade <项目> [--apply]     # 问答计划版本；无版本先检查内容
python3 "$CLI" plan next <项目>
```

`next` 列出依赖全部关闭（done/cancelled）的 pending 任务（按计划顺序，带 gates），另给 `waiting`（还在等哪些依赖）、`blocked`、`current`；已有进行中任务时提示先收掉它。它只读，不替 AI 选任务。

`show` 返回 30 秒恢复卡。目录格式先给核心：`format="outline"`、`goal`、`phase`（`id`/`index`/`title`/`state`/`summary`/`done`/`total`）、`phase_count`、`phases_done`、`phases`（整份目录；步骤已被 `plan archive` 收起的阶段带 `archived_steps`）、`details`（细节文章路径或 null）、`blockers`（阻塞步骤与原因）、`questions`（关键问题最后 5 行）、`decisions`（决定最后 3 行）、`now_stale`；旧格式带 `format="legacy"`，有结构化任务时另给 `migrate_hint`。其余字段两种格式相同：goal、current、next、latest learning、blocker、状态计数，`recent_log`（当天与前一天 `_logs/<YYYY-MM-DD>-plan.md` 的最后 3 行留痕，只读，无文件时为空列表），`notes`（当前/下一步任务及整个计划最近 3 条 `plan note`，回看 14 天日志），`last_fail`（同一范围内最近一条 `note:fail`：`date`/`time`/`id`/`text`，没有为 null；每轮提示只在 24 小时内时显示），`unrecorded`（计划最后一次提交以来的提交数 + 计划更新后又改过的文件数），`task_git`（任务分支 `task/<ID>` 是否存在、worktree、领先数、是否已并入）。`--fast` 跳过后两项的 git 统计（每轮提示用）。`inspect` 暴露一个任务的 scope/gate/evidence，供 `affected --task` 使用。`validate` 检查：

- ID/phase/重复项；
- 至多一个 in-progress；
- stamp、Current Coordinate 与 Active Work 镜像一致；
- 依赖存在且状态合理；
- done/cancelled/blocked 的证据或理由；
- checkbox 与状态一致；
- 体积预算（只警告，`verdict=warn`，退出码仍为 0）：计划 >30KB → `PLAN_OVER_BUDGET`；任务行 >500B → `PLAN_TASK_LINE_LONG`；scope 合计 >300B → `PLAN_SCOPE_LONG`；最近 14 天 note 或 Latest learning >300 字 → `PLAN_NOTE_LONG`。每条带 `hint` 建议命令。轻量模式（无结构化任务）不做预算检查。

## 6. 受控 CRUD

目录格式特有（旧格式计划调用时报错并提示先改写）：

```bash
python3 "$CLI" plan goal <项目> "国庆去北京长城：机票、酒店、门票都订好"
python3 "$CLI" plan phase add <项目> --title "查行情" --summary "问清需求后查票，每查两处写进 findings。" [--after P1]
python3 "$CLI" plan phase edit <项目> P2 [--title "…"] [--summary "…"]      # 小结给空串 = 删掉
python3 "$CLI" plan phase cancel <项目> P3 --reason "改成自驾"              # 未关闭步骤全部取消：reason=阶段放弃：…
python3 "$CLI" plan add <项目> --parent P2 --title "查酒店"                 # 放在阶段末尾；--parent 步骤ID 则放在其子树末尾
python3 "$CLI" plan archive <项目> --keep 1                                 # 收起已关闭阶段的步骤，标题 + 小结留下
python3 "$CLI" plan migrate <项目> _tmp/plan-draft.md [--apply] [--accept-dropped]
```

`migrate`：草稿必须是目录格式且不变量全过，否则返回 errors；从旧格式改写时，草稿步骤若沿用旧计划或 `_logs/plan-archive.md` 里的编号，标题必须和原来一致（同一件事），否则 `PLAN_MIGRATE_ID_REUSED`（目录格式之间的重写允许改说法）；目标与阶段小结不能以 `#` 或勾选框开头；默认只预览（阶段数、步骤数、`dropped_open` = 旧计划里草稿没列出的未关闭任务、`warnings` = 可读性警告、`preview` = 核心字段）；`--apply` 时若有 `dropped_open` 须加 `--accept-dropped`，替换前原文写入 `_logs/plan-history/<时间>-before-migrate.md`（同一秒多次加序号；CAS 冲突时删掉），软链 `_task_plan.before-migrate.md` 只在从旧格式改写时指向它（之后的重写不再挪动，始终指向旧格式原文），CAS 替换计划并记一行日志。标题上的记号接受常见近形（U+FE0F 变体、❌/✖→✕、✔/☑→✅），标题中间的记号会被去掉；`plan phase cancel` 放弃的阶段即使有已完成步骤也显示 ✕。`migrate` 另要求标了 ✅ 的阶段列出步骤（或已有归档步骤），否则 `PLAN_PHASE_NO_STEPS` 错误。可读性警告（`validate` 的 `warnings`，不阻断）：标题里有路径、编号、小数/百分比或 ≥3 个英文术语 `PLAN_TITLE_TECHNICAL`、阶段下没有步骤也没有归档步骤 `PLAN_PHASE_NO_STEPS`、阶段 >7 `PLAN_PHASES_MANY`、未关闭步骤标题 >40 字或阶段名 >24 字 `PLAN_TITLE_LONG`、已完成/当前阶段没有小结 `PLAN_PHASE_NO_SUMMARY`、小结 >160 字 `PLAN_SUMMARY_LONG`、一个阶段 >10 步 `PLAN_STEPS_MANY`、`PLAN_NOW_STALE`。目录格式的 `note --kind learn` 只写日志，不写计划。

以下命令两种格式通用（示例是旧格式 ID）：

新增根任务或自动生成子任务：

```bash
python3 "$CLI" plan add <项目> --id P3.9.E4 --title "冻结验收门" \
  --dep P3.9.E3 --scope path:_code/eval.py --gate test:integration

python3 "$CLI" plan add <项目> --id P3.9.E7 --title "合并两路结果" \
  --depends-on P3.9.E4,P3.9.E5 --gate "pytest -q tests/test_merge.py 全绿" 

python3 "$CLI" plan add <项目> --parent P3.9.E4 --title "补负例" \
  --scope symbol:ControllerGate --gate test:negative-case

python3 "$CLI" plan edit <项目> P3.9.E4 \
  --add-scope registry:controller --remove-scope path:_code/old_controller.py \
  --add-gate test:controller-dev
```

状态变更：

```bash
python3 "$CLI" plan start <项目> P3.9.E4
python3 "$CLI" plan block <项目> P3.9.E4 --reason "缺少固定 development split"
python3 "$CLI" plan reopen <项目> P3.9.E4
python3 "$CLI" plan complete <项目> P3.9.E4 --evidence test:integration --evidence finding:P3.9-gate
python3 "$CLI" plan complete <项目> P3.9.E5 --no-artifact-reason "纯人工路线确认，无独立产物"
python3 "$CLI" plan cancel <项目> P3.9.E6 --reason "被 P3.9.E4 的统一 gate 取代"
```

任务中途与 Git 联动：

```bash
python3 "$CLI" plan note <项目> "解析器完成，写出端下一步"                 # 默认记到进行中任务
python3 "$CLI" plan note <项目> --kind fail "alpha=0.9 发散，回到 0.5"
python3 "$CLI" plan note <项目> --kind learn "A−映射必须两处同改" --id P3.9.E4   # 同时写 Latest learning
python3 "$CLI" plan start <项目> P3.9.E4 --worktree                           # 经用户同意后：task/P3.9.E4 于 .worktrees/P3.9.E4
python3 "$CLI" plan complete <项目> P3.9.E4 --evidence test:integration --commit [--merge]
python3 "$CLI" plan merge <项目> P3.9.E4                                      # 只合并
python3 "$CLI" plan archive <项目> --keep 5                                   # 已关闭任务移到 _logs/plan-archive.md
```

`complete` 时若任务声明了 gate 而证据里没有引用它，返回 `gate_reminder`（不拦截；证据要求本身不变），提示把 gate 的验证结果补进证据或 `plan note`。`--commit` 只收任务 scope/gate/evidence 里 `path:`/`test:` 或裸路径下的改动（含空白的 gate/命令不当路径），加计划和整个 TOP 目录（过滤凭证/缓存/临时/大文件），提交信息 `<ID> <标题>` + `Task: <ID>` trailer；在任务 worktree 里时代码提交在 `task/<ID>`，计划与日志提交在主线。`plan add` 对同 scope 或标题相近（相似度 ≥0.6）的开放任务返回 `warnings`。`archive` 保留最近 N 组已关闭任务、仍被开放任务依赖的任务，以及还有开放子任务的整组。设计与边界见 `git-version-lifecycle.md`「TOP × Git 联动」。

### 改计划：`plan insert` / `plan replan`

```bash
python3 "$CLI" plan insert <项目> P3.9.E4 --title "补负例探针" --gate "probe 通过" --reason "E4 暴露缺负例" [--rewire]
python3 "$CLI" plan replan <项目> P3.9.E5 --reason "旧 loader 太慢" \
  --replace-with "改用 arrow loader" --replace-with "基准测试" [--gate "<新验收>"]
```

- **新 ID 方案（定案）**：`<AFTER_ID>` 后缀第一个未占用的小写字母——`P3.9.E4` → `P3.9.E4a`、再插 `P3.9.E4b`；在已带字母的任务后插入保留词干（`P3.9.E4a` → `P3.9.E4b`）。理由：父前缀不变（`P3.9.E4a` 与 `P3.9.E4` 同级，计划看板按 `.` 前缀建树不受影响），不重编号任何已有 ID（`Task:` trailer 仍指向原任务），读起来就是 PWF 的"插在 4 后面的 4.5"。占用判定包括当前任务、其后代前缀和 `_logs/plan-archive.md` 里已归档的 ID；字母只表示"在 X 附近新增"，先后以 Active Work 的行顺序为准。a–z 用完时报错。备选"同父前缀下一个未用数字"会让 `1, 2, 6, 3` 这种顺序与编号打架，未采用。
- **位置**：新行放在 `AFTER_ID` 及其全部子任务的最后一行之后（replan 放在原任务子树之后）。
- **insert 依赖**：默认新任务无依赖、只占位置；`--rewire` 时新任务依赖 `AFTER_ID`，原来依赖 `AFTER_ID` 的 pending/blocked 任务改为依赖新任务。已在进行中的任务不改（它是在旧依赖上开工的）。`--reason` 只写日志和 `change_summary`，不写进计划行。
- **replan**：原任务必须未关闭、没有开放子任务；标为 `cancelled`，`reason=换路线：<原因>`。替代任务依次得到 `<ID>a`、`<ID>b`…并串联：第一个继承原任务的依赖，之后每个依赖前一个；验收 gate 挂在最后一个替代任务上（给了 `--gate` 用新的，否则沿用原任务的 gate——换的是路线，不是验收标准）。原来依赖该任务的 pending/blocked 任务改为依赖最后一个替代任务。随后自动 `plan note --id <ID> --kind fail "换路线：<原因>"`，计入 3 次失败协议。
- **输出**：`inserted`（新任务）、`rewired`（改了依赖的任务）、`change_summary`（三行中文：改了什么 / 为什么 / 影响哪些后续任务 + 当前下一步），供 AI 原样转告用户；日志行 `insert <新ID> <标题> · after=<ID> · ev=<原因> [· rewire=…]`、`replan <ID> <标题> · ev=换路线：… · to=<新ID,…>`。写入仍走 CAS + 不变量校验，失败零写入。

### 3 次失败协议：`plan note --kind fail`

`--kind fail` 且记在具体任务上（不是 `plan`）时，返回 `fail_count`（该任务在全部 `_logs/*-plan.md` 里的 `note:fail` 条数，含刚写的这条）和 `escalate`。达到 3 条时 `escalate: true`、`verdict=warn`（退出码仍为 0），`next_hint` 为"同一任务已失败 3 次：停下来找用户，列出试过的三种做法和各自结果"，并作为 `[→ AI 行动]` 尾注打到 stderr。`plan replan` 自动记的那条 fail 同样计数。

`edit` 可修改开放任务标题，并用 `--add/--remove-dep|scope|gate` 精确调整元数据；闭合任务必须先 reopen，依赖环会被拒绝。没有 `remove`：历史任务只能带理由取消。父任务存在开放子任务时不能 complete/cancel；依赖未闭合不能 start；已有 in-progress 时不能启动第二项；完成没有证据或无产物理由会被拒绝。

### 自动留痕（start / complete / block / cancel / reopen，另有 note / merge / archive / insert / replan）

insert / replan 也各写一行（见上）。这些命令写计划成功后，自动向 `_wiki-methodology/_top/_logs/<YYYY-MM-DD>-plan.md` 追加一行（文件不存在时创建，首行 `# <YYYY-MM-DD> log`）：

```text
- 14:05 complete P3.9.E4 冻结验收门 · ev=test:integration,finding:P3.9-gate · git=main@a1b2c3d(+2 dirty)
- 14:20 block P3.9.E5 补负例 · ev=缺少固定 development split · git=main@a1b2c3d(+3 dirty)
- 14:30 complete P3.9.E6 路线确认 · ev=no_artifact:纯人工路线确认 · git=none
```

- 文件名约定：用 `-plan` 后缀，不与现有 `_logs/` 三类文件冲突——手写日志 `<YYYY-MM-DD>.md`、`top-update.py log` 生成的 `_<YYYY-MM-DD>.md`、专题日志 `<YYYY-MM-DD>-<topic>.md`。仍以日期开头，`top-status` / `top-brief` 按日期排序能看到它。
- `ev=`：complete 写该任务全部 evidence（逗号分隔），无产物时写 `no_artifact:<理由>`；block/cancel 写原因；reopen 写 `-`。
- `git=`：只读 `git rev-parse` + `git status --porcelain`（每条 5 秒超时，`GIT_OPTIONAL_LOCKS=0`），格式 `<分支>@<短 HEAD>(+<未提交文件数> dirty)`；dirty 计数在计划写入之后取，因此通常包含 `_task_plan.md` 本身。项目不在 git 仓库内写 `git=none`；git 缺失/超时/报错写 `git=unknown(<原因>)`，不影响计划写入。
- 顺序：先完成计划 CAS 写入，再追加日志；日志追加失败只在 stderr 打 `[warn]`，JSON `log` 带 `error`，**不回滚计划**。
- JSON 输出新增 `log` 字段：`{"file": <日志路径>, "line": <追加的那一行>}`；`--no-log` 关闭留痕，此时 `log` 为 `null`。start/add/edit 不写日志。
- 这行只是时间线索引；结论、死路和可复用理由仍写 finding / decision，不写进日志。

### 计划瘦身：`plan compact`

```bash
python3 "$CLI" plan compact <项目>           # 预览：列出将移出的段落、字节数、原因
python3 "$CLI" plan compact <项目> --apply   # 写入
```

移出对象（原样搬到 `_logs/<YYYY-MM-DD>-journal-archive.md`，同日多次追加）：标题带日期或以“历史/旧/History/Archive/Legacy”开头的 `##` 段；其它 >2KB 的 `##` 段；Active Work 内不含任务行的带日期小节（`###` 及更深）；Active Work 内 >1KB 的非任务说明行；>1.5KB 的文件头说明（保留标题、stamp 行和 Done Criteria 段）。保留：Current Coordinate、Active Work 任务行、短的无日期段，以及末尾 `## 历史索引（plan compact 移出，原文在 _logs）`（每次追加一条：日期、段数、归档路径、至多 12 个标题）。

安全性：`--apply` 先追加归档，再对计划做 CAS 写入；计划被并发修改则回滚归档并报冲突。移动前后计划的解析结果（phase、stamp 任务、Current Coordinate、全部任务行、Done Criteria、错误码集合）必须完全一致，否则拒绝。没有 `## Active Work` 的轻量计划直接返回 ok、不做任何事。已关闭任务仍多时用 `plan archive`。

## 7. 并发与原子写

计划写入采用 compare-and-swap：读取时记录 SHA-256，写入时再次核对；文件变化则拒绝覆盖并要求重读。实际替换经同目录临时文件、`fsync`、`os.replace` 完成。它防止 AI/人类并发覆盖，但不是多人任务调度器；冲突后必须重新 `plan show/inspect`，不能盲重试旧命令。

## 8. 结构化记录

```bash
python3 "$CLI" record add finding <项目> --title "边界救援仅在低置信样本有效" \
  --summary "development split 上 intervention 受控，formal test 未读取" \
  --phase P3.9 --evidence test:controller-dev
python3 "$CLI" record add decision <项目> --title "关闭不合格动作" --summary "harm gate 超限"
python3 "$CLI" record list finding <项目>
python3 "$CLI" record show <项目> _wiki-methodology/_top/_findings/<文件>.md
python3 "$CLI" record search <项目> "融合 mask" --limit 3
```

`record add` 复用既有 `top-update.py`，支持 `finding|decision|review|log`。决策的需求、理由、备选方案、代码、来源和验证参数，以及无需模型的有界查询，见 [按需决策记忆](decision-memory.md)。`list/show` 是有界读取，并阻止路径逃逸。record 保存结论/决策/时间线；不要把历史正文重新塞回 Active Work。

## 9. 六列 owner 查询

```bash
python3 "$CLI" owner list <项目>
python3 "$CLI" owner show <项目> code
python3 "$CLI" owner resolve <项目> registry:controller
python3 "$CLI" owner resolve <项目> pipeline:train-m1
python3 "$CLI" owner resolve <项目> gate:controller-dev
python3 "$CLI" owner resolve <项目> path:_code/models/controller.py
python3 "$CLI" owner resolve <项目> symbol:ControllerGate
```

owner 列是 `wiki|top|tests|code|lifecycle|picture`。typed ref 只做定位，不复制 owner 正文。`symbol:` 明确交给 CodeGraph/语义扫描继续核验。

## 10. task-aware 影响分析

```bash
python3 "$CLI" affected <项目> --task P3.9.E4
python3 "$CLI" affected <项目> --since HEAD~1 --task P3.9.E4
```

`affected` 合并四类证据：git changed paths、任务 `scope/gate`、CodeGraph `affected/impact`、registry/pipeline/test 映射（命中的旧 CodeBook 节点只作只读参考，`codebook_retired=true`，不要求回写）。CodeGraph fresh 的条件是：已初始化、`pendingChanges=0`、无 `worktreeMismatch`、不建议 reindex。否则结果降级为导航线索，不能冒充完整影响面。

路径先分类：主流程 code/test 参与 gate；`_outputs/_figures` 是证据；`_legacy/_tmp/_sandbox` 和 vendored/external 默认不污染主流程命中。最终仍要打开源码和测试复核。

## 11. CodeGraph 与扫描模式边界

- 日常已知 symbol/caller/impact：直接用 CodeGraph；这是基础设施，不等于广泛扫描。
- CodeGraph 缺失或 stale：按 CodeGraph 官方文档重建或同步索引（配套的 semantic-scan 脚本本包未包含）。
- 用户明确说“扫描模式 / 语义扫描 / 全局扫描 / deep scan / 重建 codemap”时，加载代码语义扫描技能（可选，本包未包含），执行有边界的全局扫描；产物只是导航，事实仍由源码、live graph 和测试确认。
- `affected --task` 不会悄悄启动全仓语义扫描。

## 12. pipeline 防伪盖章（CodeBook 已退役）

```bash
python3 "$CLI" verify-pipeline <项目> train-m1
```

`verify-pipeline` 依据真实 step 接线写 `verified_steps_hash`。手改 hash 是伪造。step 漂移后 `doctor --full` 报告 stale。

CodeBook 于 2026-09-24 退役：代码结构交给 CodeGraph，入口写 `_codemap.md`，理由写决策记录的“涉及代码”并用 `record for-file` 找回。`deposit` 保留命令名兼容旧调用，只返回 `retired=true` 与迁移提示，不再写 `last_verified_hash`；已有 `_codebook/` 当普通文档只读。

## 13. 冷启动与收尾

```bash
python3 "$CLI" plan show <项目>
# ...工作...
git status --short
python3 "$CLI" plan complete <项目> <ID> --evidence <gate 结果> --commit [--decision <决策路径>]
python3 "$CLI" doctor <项目>          # 按需
```

`plan show` 回答“现在做哪件事”；`doctor` 回答“这些真源是否可信”，默认只查死链（入口文档相对链接 + typed ref）、登记路径存在、plan validate（含体积预算）、未记录的提交（不带 `Task:` trailer，warn）/改动（info）；pipeline 印记与旧 CodeBook 新鲜度只在 `doctor --full`（旧版全量体检，可选）。`brief` 保留兼容，不再是必跑。

## 14. 降级与回滚

- 没有结构化任务的计划（轻量模式）：`plan show/validate` 照常报告，`doctor` 只给 info、hook 不给收尾提醒、`compact` 不动它；不伪造任务，也不要求迁移。
- CodeGraph 不可用：仍返回 git/scope/owner 命中，并显式标记降级。
- Codanna 不可用：不影响日常 CodeGraph；只有明确扫描模式时报告该后端缺口。
- 计划写冲突：零写入，重读后重试。
- 需要回滚 CLI：Markdown 真源未被私有格式锁死；移除新命令后旧 reader 仍能读 phase/stamp。

CLI envelope 版本保持 `sixone-cli/v1`，计划子协议为 `sixone-plan/v1`。未来接 SDK、插件或 MCP 时应包裹当前 CLI/core 契约，不得另建一套状态数据库。
