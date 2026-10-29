# Git、成果版本与实验生命周期

用于多分支、未提交工作、实验迭代或成果证据容易混淆的项目。普通单点文案修改不强制建版本快照。

## Git 是骨架，TOP 只记 Git 记不下的

Git 是版本管理器：提交、父子关系、trailer 和 tag 已经记下“改了什么、何时、属于哪个任务、依据哪条决策、到了哪个里程碑”。TOP 不再抄一遍这些，只记 Git 记不下的三样：**意图**（任务、验收 gate）、**当前坐标**（Active Work 里谁在进行、下一步、阻塞）、**决策理由**（`_decisions/`）。两边用 trailer 互相指：

| Trailer / 引用 | 含义 | 谁写 | 谁读 |
|---|---|---|---|
| `Task: <ID>` | 提交属于该任务 | `plan complete --commit`、`plan merge`、`plan handoff`；全局 `prepare-commit-msg` 钩子给普通提交自动补 | `plan show` 的 `activity`（任务相关提交 + note）、`unrecorded`（带 Task 的提交算已挂钩，计入 `task_commits`） |
| `Decision: <仓库相对路径>` | 该提交依据的决策记录 | `plan complete --commit --decision <路径>`（可多次；决策文件随同一提交） | `record for-file`（`git log -- <文件>` 里的 Decision 指回决策）、编辑提示 hook |
| `Handoff: <仓库相对路径>` | 交接快照 | `plan handoff <项目> <文档>` | `plan show` 的 `last_handoff` |
| tag `top/<phase>` | 阶段里程碑（annotated，消息=该阶段完成/取消任务摘要） | `plan milestone <项目> <phase>`（有未关闭任务拒绝，`--allow-open` 例外；已存在的 tag 从不移动） | `git show top/<phase>` |
| 日志行 `commit=<短SHA>` | 该完成/交接落在哪个提交 | `plan complete --commit` / `plan handoff` 提交后回写当天日志那一行（日志因此比提交多一处改动，随下一次计划提交入库；写进同一提交会自引用） | 人和 AI 从日志跳到提交 |
| 计划历史索引 `git show <SHA>:<计划路径>` | 瘦身前原文在 Git 里的位置 | `plan compact --apply`，仅当计划在 HEAD 干净时写（快照文件照旧保留） | 需要原文时 |

## 全局 git hooks（`git-hooks/`）

目录 `git-hooks/` 为 git 的常用 hook 名（pre-commit、prepare-commit-msg、commit-msg、post-commit、pre-push、post-merge、post-checkout、pre-rebase、post-rewrite、pre-merge-commit，以及 applypatch/receive/update/p4/pre-auto-gc/sendemail-validate 等其余标准名）各放一个指向 `_chain.sh` 的软链（hook 名取自 `$0`）：

1. **先原样执行仓库自己的 hook**：`$(git rev-parse --git-common-dir)/hooks/<名字>`（worktree 也指向主仓的 hooks），参数、stdin、退出码原样；本地 pre-commit 失败照样阻断提交。没有本地 hook 就什么都不做。
2. **再做 TOP 附加动作，全部 fail-open**（出错只在 stderr 打一行 `[top-hooks]`，不改退出码）：
   - `prepare-commit-msg`：仓库根有 TOP 计划、恰好一个 in_progress 任务、提交信息里还没有 `Task:` 时，用 `git interpret-trailers` 追加 `Task: <ID>`。在 `task/<ID>` 分支（任务 worktree）直接用分支名里的 ID；其它 linked worktree 不猜。merge/squash/amend/`-c`/`-C` 来源、rebase/cherry-pick/revert/merge 进行中都跳过。编辑器提交且信息为空时把 trailer 放在第 3 行，第 1 行留给标题。
   - `prepare-commit-msg` 另加 `Session: <claude|codex>:<会话号>`（Claude 取 `CLAUDE_CODE_SESSION_ID`，Codex 取 `CODEX_THREAD_ID`，否则读 tmux 窗口标记）：TOP 项目默认加，其它仓库需 `git config top.sessionTrailer true`；**公开仓库设 `top.sessionTrailer false`**（会话号不外发，新建公开仓库时一并设置）。由此可从一行代码 → blame → 提交 → 任务、决策与当时的对话。
   - `pre-commit`：仓库自己的 pre-commit 通过后，拦下超过 `top.maxFileMB`（默认 50 MB）的暂存文件和新增行里像真凭证的字符串（API key、GitHub/Slack token、AWS key、私钥）；确认无误单次放行 `TOP_ALLOW_LARGE=1` / `TOP_ALLOW_SECRETS=1`。检查器自身出错不拦提交。
   - `commit-msg`：编辑后只剩 `Task:` 行（用户清空信息想放弃）时去掉它，git 照常以“空信息”中止。`--no-verify` 会跳过这一步。
   - `post-commit`：工作树根有 `.codegraph/` 且有 `codegraph` 命令时，后台 `nohup nice flock -n … timeout 300 codegraph sync -q <根>`，清掉 `GIT_INDEX_FILE` 等变量；失败不影响提交。
3. `TOP_GIT_HOOKS=off` 关闭附加动作（本地 hook 仍执行）。仓库自己设了本地 `core.hooksPath`（如 husky）时全局设置不生效，这些仓库没有自动 Task trailer。`push-to-checkout`、`proc-receive` 不包装（存在即改变 git 默认行为）；高频的 `reference-transaction`、`post-index-change` 不包装（每次 ref/索引更新都会多起一个进程）——装了全局 hooksPath 后，仓库里这几个名字的本地 hook 不会再运行，`install.sh status --scan` 会把这种仓库标成警告。
4. 开销：非 TOP 仓库每次提交约多 50–60 ms（4 次 bash 调用，无 Python）；TOP 仓库有进行中任务时约多 140 ms（多一次 Python 读计划）。

安装/卸载只动 `git config --global core.hooksPath`，不改任何仓库：

```bash
bash ~/.claude/skills/share-top/git-hooks/install.sh status --scan ~/projects   # 当前设置；哪些仓库有本地 hook（会被链式执行）或本地 hooksPath（不生效）
bash ~/.claude/skills/share-top/git-hooks/install.sh install                    # 已有别的全局 hooksPath 时拒绝；--force 替换并记下原值
bash ~/.claude/skills/share-top/git-hooks/install.sh uninstall                  # 只在指向本目录时撤销，有原值则恢复
```

## 追踪边界与分拣（`track`）

原则见 [git-workflow.md](git-workflow.md) 的追踪分类表：按文件**怎么来的**判断，不按价值——写出来的（代码、绘图脚本、配置、论文源文件、TOP 记录、沙盒代码）一律追踪；能重新算出来的产物不追踪，只追踪配方（脚本、配置、参数、输入数据版本）并把位置与哈希登记到 data registry；环境、缓存、凭证永不追踪。进不进 Git 与"转正式"是两件事：转正式看是否推动计划（见下文「实验退出与归档」）。

实现分三处，入口 `scripts/sixone-cli.py track`，实现 `scripts/top_track.py`：

1. **`.gitignore` 基线**：`templates/gitignore/research.gitignore`、`dev.gitignore`，各段带注释说明为什么忽略、配方怎么追踪。`init-research.sh --kind research|dev`（默认 research）在没有 `.gitignore` 时复制模板，已有时把缺失行追加到 `# >>> top baseline (<kind>) >>>` 标记块（幂等，不动块外内容）；同时建该 kind 的常用目录（各带五问 `_readme.md`，已有的不覆盖）；已有计划的老项目给出 `--kind` 就只补缺的目录与基线。
2. **分拣**：`track <repo>` 读 `git status -z --untracked-files=all` 和 `git ls-files -z`，把每个路径分成三类：
   - `commit`：写出来的文本、TOP 记录与项目说明、论文目录里的图；已追踪的改动也在这里（表示待提交）。
   - `ignore`：凭证、环境与缓存目录、`_tmp/`、任意层 `_artifacts/`、构建产物、模型权重与二进制数据、超过阈值（`git config top.trackLargeMB`，默认 10MB）的非文本、生成区（`_outputs/`、`_data/`、`results/`、`runs/` 等）里成批的生成文件。
   - `review`：需要判断的中间地带——生成区里的少量文件（可能是该追踪的汇总层）、生成区里的代码（可能是真脚本也可能是快照副本）、普通目录里的图和表格、超过 1MB 的文本、fixtures 里的二进制、未知扩展名。
   另有 `structure`（只读，目录是否清晰）：`root_loose` 根目录散落的文件（常见项目根文件除外）；`dirs_without_readme` 缺 README 的顶层目录（`_` 目录也要说明，被 `.gitignore` 整体忽略的目录不算）；`unarchived` 未归档的未追踪文件（数量与样例）——已归档区 = `_` 开头或带 README 的顶层目录，根目录白名单外的文件和无 README 普通目录里的文件都算未归档。
   另有 `tracked_should_ignore`：已经被误提交的缓存/凭证/临时文件，只给 `git rm -r --cached` 建议。输出含每类按前两级目录的聚合、`gitignore_suggestions`（能整目录就整目录，同目录有已追踪或 commit 类文件时退回扩展名级或精确路径）和一句 `next_hint`；`--markdown` 给人读。
3. **plan complete 集成**：见上文「TOP × Git 联动」——计划提交带上整个 TOP 目录，scope 外剩余改动按类计数并提示。

AI 拿到分拣结果后：

- `commit` 类：自己写的补进任务 scope 或单独按路径提交；别的窗口正在改的代码不替它提交。
- `ignore` 类：确认后 `track <repo> --write-gitignore`，只写 `# >>> top track (auto) >>>` 标记块（只追加缺的行，不删块内已有行），文件留在磁盘上；大数据另登记到 data registry。工具建议不合适时，手工规则写在标记块**之后**并加注释：`!` 例外必须排在它要放行的规则之后才生效，且父目录不能已被整目录忽略。
- `review` 类：用"删掉它能不能一条命令重新生成"判断；汇总层（指标表、终稿图）追踪，其余加忽略；拿不准的列给用户。
- `tracked_should_ignore`：`git rm -r --cached <目录>` 加忽略规则后提交（文件不删）；要从历史里彻底清除属于改写历史，先问用户。

**一键归档**：用户说"归档 / 梳理一下 / 更新六合一"，本质是同一件事——文件放到约定位置、该进 Git 的提交、计划与笔记更新。完整的一键归档依赖归档技能 `share-archive`（可选，本包未包含）；未安装时按本节 `track` 分拣后手工提交。

边界：`track` 从不 `git add`/`commit`/`rm`；`--write-gitignore` 只动标记块。分类是按路径、扩展名、大小的近似，`review` 类和生成区判断要 AI 结合项目实际确认，不把分拣结果当成"已整理完"的证据——整理完的证据是 `git status` 与再次 `track` 的计数。

## 一条关系，四种职责

Git保存提交和父子关系；现有registry保存代码/资产位置；run/evidence绑定实际被验证的内容；现有选择入口记录采用决定。CodeGraph只是依赖导航缓存，不保存实验是否成功的权威状态。不要新增手写版本号账本替代Git，也不要删除仍有消费者的registry。

分支名会移动，不能作不可变版本号。一个工作区只有一套检出内容；并行隔离需已授权的独立工作区，且数据输出仍要独占。任务可以有多个提交，一个提交也可以产生多个实验。保留父内容身份、任务和归并目标；合并/rebase/cherry-pick后核验实际内容与依赖，不自动继承旧通过状态。

## 已实现CLI

入口 `scripts/sixone-cli.py version`，实现 `scripts/top_version.py`。

```bash
python3 sixone-cli.py version status <repo>
python3 sixone-cli.py version capture <repo> --file src/model.py --file config.json --artifact weights.pt --task T1 --output <全新目录>
python3 sixone-cli.py version verify <repo> <快照目录/manifest.json>
python3 sixone-cli.py version verify <repo> <快照目录/manifest.json> --staged
python3 sixone-cli.py version compare <快照A/manifest.json> <快照B/manifest.json>
```

- status返回实际worktree、branch/游离HEAD、完整commit、index指纹及脏状态。没有初始化提交也可检查。
- capture只收显式文件：源文件复制成内容寻址blob，删除源文件记录tombstone；大资产仅保存字节hash，原存储仍需保留。每个源文件至多16MiB，合计64MiB。符号链接、目录、Git元数据和跨根路径拒绝；输出不可覆盖。
- 内容ID按声明文件清单计算，与分支名/提交号分开；文件字节hash和规范化JSON内容hash明确标注种类。不要直接套用历史receipt中同名sha256字段。
- verify只证明声明内容匹配，返回非零表示失效；--staged核验暂存源文件和原位置资产，不能把工作树通过当暂存区通过。
- compare输出具体变更路径和两端Git背景，不判断哪个好、不自动采用。

## 明确边界

`version`是显式范围的内容快照/核验器，不是全依赖捕获、运行沙箱、测试执行器或备份服务；提交只发生在下文`plan complete --commit`这类显式命令里。范围不全时不能称可完整复现。依赖包括必要配置、环境标识、数据版本、预处理/解码或外部模型；按项目实际声明，未知写未知。

双读能发现部分并发改动，不能证明原子快照，不能排除变化后恢复。需要强绑定运行时，应在隔离目录从捕获内容构建并运行，另行记录执行环境与命令；当前CLI未实现该运行包装。只在运行前后扫描原目录不能证明进程实际用了这些字节。

snapshot一致不等于测试通过、来源可信或获准发布。manifest可被人工修改，因此不是防篡改签名。跨clone使用当前拒绝，须单独核验来源；同仓多worktree可核验内容并显式报告提交/分支变化。未声明文件变化不由内容ID覆盖。

## TOP × Git 联动（plan 命令已实现）

一条规则防止计划和 Git 变成两本账：**计划只在主 worktree 的主线上维护，从不分支；代码可以分支。** 任务与 Git 的关联全部由任务 ID 推导，计划里不另存分支字段：

| 对象 | 约定 | 由谁维护 |
|---|---|---|
| 任务提交 | 提交信息末尾 `Task: <ID>` trailer | `plan complete --commit` / `plan merge` 自动写；手工提交由全局 `prepare-commit-msg` 钩子补（已安装时），也可自行加 |
| 任务分支 | `task/<ID>` | `plan start --worktree` 创建，`plan merge` 或 `complete --merge` 合并后删除（`branch -d`） |
| 任务 worktree | `<主 worktree>/.worktrees/<ID>`（写入 `.git/info/exclude`） | 同上；合并后 `git worktree remove`（不加 --force） |
| 进度与日志 | 主 worktree 的 `_task_plan.md` 与 `_logs/<日期>-plan.md` | 在任务 worktree 里跑 CLI 也写主计划；worktree 里的计划副本只读、不更新 |

两种工作方式：

1. **主线直接做（默认，单窗口）**：改完、验证后 `plan complete <项目> <ID> --evidence … --commit`，任务 scope/gate/证据里的 `path:`/`test:` 路径中的改动 + 计划 + 整个 TOP 目录（`_top/` 下的 finding、决策、日志、阶段记录等；先过分类器，凭证、缓存、临时、大文件不带）合成一个本地提交。别人已暂存的文件保持暂存不动；scope 外的剩余改动在 `git.uncommitted_outside_scope` 里列出（`by_class` 分类计数、`authored_sample` 写出来却没进 Git 的样例，有这类文件时带 `track_hint`），由 AI 判断补 scope 还是另行提交。
2. **任务 worktree（长任务按 git-workflow 的持续授权，短任务按实际隔离需要）**：`plan start <项目> <ID> --worktree` → 在 `.worktrees/<ID>` 里改代码 → `plan complete <worktree 或项目> <ID> --evidence … --commit --merge`：代码提交在 `task/<ID>`，先 fast-forward，不行就 merge commit；冲突时 `merge --abort` 并列出冲突文件，什么都不改；合并后清理 worktree 与分支，最后在主线上提交计划和日志。只想合并用 `plan merge <项目> <ID>`。

`plan show` 的 `unrecorded` 按 Git 判定：以计划/日志最后一次提交为基线（计划有未提交改动时，早于这次改动的提交算已看过），之后**没有** `Task:`/`Handoff:` trailer 的提交计入 `commits`，有 trailer 的计入 `task_commits`；“计划更新后又改过的文件数”仍按文件修改时间（Git 不知道工作区改动发生在何时）。`activity` 是当前/下一任务的 `Task:` 提交与 note 合并后的最近动态，`last_handoff` 是最近一次 `Handoff:` 提交；`task_git` 给出当前任务分支是否存在、领先多少、是否已并入。这些只在显式 `plan show` / doctor 里供接续时参考；2026-10-16 起启动提示不再报“N 个提交没记进计划”（短碎改动本来就不进计划）。CLI 不 push、不 rebase、不 reset、不强删；pre-commit 钩子失败时计划已记完成，`git` 字段带 error，AI 按报错修后手动提交。

## 与提交和六合一连接

开工用version status辨认位置；需要保存实验/重要验证时capture，将manifest作为已有run或TOP记录的evidence链接。结果记录再链接测试命令、日志和所用内容ID。内容快照不写第二份任务状态，不重复维护分数。

提交前只暂存任务所属文件，查看diff；必要时verify --staged确认与验证对象一致。阶段性逻辑改动形成提交，避免长期累积（优先用`plan complete --commit`，它只收任务 scope/gate/证据里的路径——证据里引用的仓库内、未被忽略的文件一并入同一提交——以及计划、整个 TOP 目录和 `--decision` 文件）；不要盲目add -A。代码提交后，后续证据提交引用该代码提交，避免提交哈希自引用。trailer 约定见上文；全局 hooks 由用户决定是否安装，不重写历史。

CodeGraph已有affected入口检查pending/worktreeMismatch/reindex状态。索引过期仅作线索；不把代码图fresh标记当作测试或完整依赖证明。多worktree必须查询实际根目录。

## 实验退出与归档

新假设先在项目已有sandbox/experiments独立目录和独占新输出运行，声明父版本、假设、验收与停止条件；未验证模块不默认混入正式入口。试验需要复用主模块时使用明确依赖，正式代码反向导入实验目录属于待消除的边界债务。

分别记录两件事：研究结论（有效/无效/未判定）和依赖状态（仍被使用/仅供复现/可归档）。无效实验可能仍包含共享loader；不按日期或失败标签直接移动。

晋级：核对接口、来源和相关回归，再接正式入口及登记；采用决定独立记录。失败：先保留结论与来源，逻辑标记退役；只有真实引用、动态路径和冻结绑定已检查，才准备old→new映射与恢复说明并归档。冻结源码/历史回执不原地改。

## 验收

`tests/test_top_version.py`在临时仓库覆盖dirty/untracked、index错配、外部资产变化、多worktree、游离HEAD、删除、输出不可覆盖、并发可见变化、符号链接及Git路径表达式等。测试不能冒充AI可靠性统计。

AI行为另用真实任务检查：能否指出被测版本、拒绝错绑成绩、避免未经验证接正式入口、识别仍有消费者的失败实验。只回答情境题属于理解探针；要证明实际执行改善，还需观察真实工具操作，不报虚构成功率。

## 工作区卫生

`scripts/top-hygiene.py`只读列出worktree、分支、stash和未提交改动，按SAFE/REVIEW/KEEP分类（口径写在报告头部；基准分支按origin/HEAD→main/master→主worktree当前分支判定并写明依据）。

何时跑：任务收尾准备归并时；每周一次；启动提示或`git worktree list`显示单项目worktree超过3条时。

```bash
python3 scripts/top-hygiene.py <repo>                 # 单仓Markdown
python3 scripts/top-hygiene.py --all --summary        # ~/projects下每个主仓一行
python3 scripts/top-hygiene.py --all --json > report.json
```

### 任务分支

- `top-hygiene.py`把`task/<任务ID>`分支（worktree在`.worktrees/<ID>`）与主worktree的`_task_plan.md`关联，报告/JSON带task_id/task_title/task_state。
- 分类以计划状态为准：pending/in_progress/blocked=KEEP（即使已并入）；done+已并入+clean=SAFE；done未并入=REVIEW，建议`sixone-cli.py plan merge <项目> <ID>`；cancelled或计划里没有这个ID（孤儿）=REVIEW，人工决定是否丢弃。
- 任务分支若仍被worktree占用，先移除worktree，再次扫描后分支才成为SAFE；`--apply-safe --yes`一次执行内已自动重扫。
- 计划只从git仓库根读取；读不到时任务分支一律REVIEW，并在报告的错误行说明原因。

报告只是候选清单，REVIEW逐条人工判断。`--apply-safe --yes`只在逐项核实符合git-workflow清理条件后运行；SAFE分类不能替代窗口和进程占用检查。它仅对SAFE项执行`git worktree remove`（不加--force）和`git branch -d`（不用-D），脏worktree和未并入分支由git拒绝。执行后用`git worktree list`、`git branch`独立复核。
