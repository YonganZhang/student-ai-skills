# planning-with-files 吸收对照表

来源：OthmanAdi/planning-with-files（作者 Ahmad Adi，MIT，许可证副本 [planning-with-files-LICENSE.txt](planning-with-files-LICENSE.txt)），吸收于 commit `3b7690eafd887547f0cf4f111c0d62b77c46f797`（2026-09-24）；2026-09-26 复核到 `4d24d9a`（v3.20.8：之后 12 个提交都是 Cursor/Gemini/PowerShell 适配与"无计划时 check-complete 静默"，无须吸收），并补吸收"计划即目录"的格式与 smart injection 的核心字段。登记见 `../../UPSTREAM.json`。

吸收方式是**语义吸收**：PWF 的脚本多为 sh/ps1，且面向"每个任务一套计划文件"；我们是"项目级单计划 + CLI 受控写入"，所以按我们的接口重写，没有原样照搬的代码文件。

## 以后对照上游再升级

```bash
cd <PWF 克隆> && git fetch && git diff 4d24d9a..origin/master --stat -- \
  skills/planning-with-files/SKILL.md skills/planning-with-files/templates/task_plan.md \
  skills/planning-with-files/scripts/check-complete.sh skills/planning-with-files/scripts/gate-stop.sh \
  skills/planning-with-files/scripts/inject-plan.py hooks/hooks.json hooks/codex-hooks.json docs/workflow.md \
  skills/i18n/planning-with-files-zh/templates/task_plan.md
```

逐行看下表的"PWF 机制"列有没有变化；有变化再决定改哪个"我们的位置"，改完更新 `UPSTREAM.json` 的 `absorbed_commit` 与本表。

## 对照表

> 2026-10-16：计划默认改成问答格式（[qa-plan.md](../qa-plan.md)）。上游 task_plan.md 最后一节 Key Questions 提到最前面当骨架；Goal → 目录的目标，Phases → 一串问题，Decisions → 答案修订，Errors → 日志与作废的尝试；findings.md / progress.md 收进每个问题的工作本。下表记录的目录格式吸收仍适用于旧格式计划。

| PWF 机制（上游位置） | 我们的实现位置 | 状态 |
|---|---|---|
| 计划就是一份目录：Goal / Next Step / Current Phase / `### Phase N` + 勾选步骤 + Status / Key Questions / Decisions / Errors（`templates/task_plan.md`，中文版 `skills/i18n/planning-with-files-zh`） | 目录格式（2026-09-26）：`## 目标` / `## 现在`（阶段、正在做、下一步、卡点，CLI 推导的镜像）/ `## 各阶段` 的 `### P<n> <名称> <记号>` + 一句承上启下的小结 + 步骤 / 关键问题 / 决定 / 错误；机器元数据藏进行尾 `<!-- -->`；写法见 `references/plan-writing.md`；`plan phase add/edit/cancel`、`plan goal`、`plan migrate` | 已吸收（改造：Status 与 Next Step 由步骤状态推导，不手写；多一句阶段小结，因为我们的计划要活几个月） |
| smart injection（`PWF_INJECT=smart`：计划变长时只注入标题、Goal、Next Step、Current Phase、阶段数、当前阶段全文、最近 3 条决定） | 同一组"核心"：`plan show` 的 `goal`/`phase`/`phases`/`current`/`next`/`blockers`/`decisions`；【TOP 当前】只给阶段、正在做、下一步、卡点、24 小时内失败；计划看板计划面板默认也只显示这些 | 已吸收（人和 AI 看同一份核心） |
| 插入阶段（手改成 Phase 2.5）、换路线（手改计划） | `plan insert`（`<AFTER_ID>a/b…`，`--rewire`）、`plan replan`（取消 + 串联替代 + 改依赖 + fail 笔记），都返回三行 `change_summary`；`scripts/top_plan.py` | 已吸收（新增命令；PWF 只靠手改） |
| Errors Encountered 表（错误 / 第几次 / 处理） | `plan note --id <ID> --kind fail` 写 `_logs/<日期>-plan.md`，`fail_count` 按任务累计 | 已吸收（改造：不写进计划正文） |
| 3-Strike Error Protocol（诊断修复 → 换方法 → 重新想 → 找用户） | 同一任务第 3 条 fail 笔记时 `plan note`/`plan replan` 返回 `escalate: true` + 提示；SKILL.md「中途」 | 已吸收 |
| Never Repeat Failures | SKILL.md「中途」 | 已吸收（纪律） |
| 2-Action Rule（每看两次资料就写盘） | SKILL.md「中途」：`record add finding` 或 `plan note --kind learn` | 已吸收（纪律，无自动化） |
| Read Before Decide | SKILL.md（改公式/参数/策略前重读 `plan show`） | 已有 |
| 5-Question Reboot Test | `plan show` + 恢复卡（目标、当前 + 验收、下一步、上次失败、心得、计划路径） | 部分（"做过什么"看 `plan show` 的 activity） |
| UserPromptSubmit 注入计划头 50 行 | `top-session-hint.py`【TOP 当前】一行：当前、下一步、24 小时内的失败、最近笔记，≤200 字 | 已吸收（改造：一行而非全文） |
| cache-safe（注入内容保持稳定） | 【TOP 当前】只含稳定字段（ID、标题、笔记的分钟级时间），无秒级时钟 | 部分（不用恒定字符串，因为要带当前任务） |
| PreCompact hook | `top-session-hint.py` 的 PreCompact 与 SessionStart(`source=compact`) 输出恢复卡（≤800 字） | 已吸收（见下方"宿主差异"） |
| Stop 完成门（`gate-stop.sh` → `check-complete.sh --gate`，可 block） | Stop 提醒 + `git config top.stopGate true` 时对声明了 gate 的进行中任务改用更强措辞 | 已吸收（改造：只提醒不拦截） |
| 完成门的防失控（阻断计数上限、停滞检测、`stop_hook_active`） | 不需要：我们从不拦截 | 不吸收 |
| findings.md / progress.md | `record add finding`、`_logs/` | 已有 |
| 自主模式 ledger（`ledger-append.sh` / `ledger-summary.sh`） | `_logs/<日期>-plan.md` 自动留痕 | 已有 |
| phase-status / check-complete 状态统计 | `plan show` 的 counts、`plan next` | 已有 |
| plan-doctor | `sixone-cli.py doctor` | 已有 |
| 并行写保护（完成数下降报警） | 计划写入 compare-and-swap，冲突直接拒绝 | 已有更强的 |
| 每次工具调用前注入计划（PreToolUse，约 90 token/次） | 不做；PreToolUse 只在编辑文件时给相关决策 | 刻意不吸收 |
| 计划文件默认不进 Git（工作记忆，任务完了就丢） | 计划与 `_logs/` 随 `plan complete --commit` 入库 | 刻意不吸收 |
| `.planning/<id>/` 多计划、`PLAN_ID` / `PWF_PLAN_ROOT` / `.active_plan` 选择 | 项目级单计划，多窗口靠 CAS | 刻意不吸收 |
| Attestation（SHA-256 锁定计划，偏离就不注入） | Git 提交 + CAS 已能追溯改动；锁定需人工重锁，负担大于收益 | 刻意不吸收 |
| session-catchup.py（读宿主会话记录） | 不读会话记录；跨会话漏记由 `plan show` 的 `unrecorded`（Git）发现 | 刻意不吸收 |
| `/plan-goal`、`/plan-loop`、`loop.md` | 需要时直接用宿主的 `/goal`、`/loop` 并在提示里写 `plan show` | 暂不吸收 |
| 多语言模板、各宿主适配（Cursor、Gemini…） | 只服务 Claude 与 Codex | 不吸收 |

## 宿主差异（2026-09-24 查官方文档）

- Claude Code：PreCompact 的 stdout 只写调试日志，模型看不到；`systemMessage` 被丢弃。模型能看到的是 SessionStart（`source` = `compact`）的 stdout。<https://code.claude.com/docs/en/hooks>
- Codex：有 PreCompact / PostCompact，但 PreCompact 的纯文本 stdout 被忽略；SessionStart 的 matcher 可匹配 `compact`，压缩后在下一次模型请求前运行，输出作为开发者上下文。<https://developers.openai.com/codex/hooks>
- 所以恢复卡真正送达靠 SessionStart(compact)；现有注册已覆盖（Claude SessionStart 不设 matcher；Codex matcher 含 `compact`）。PreCompact 那份只是诊断副本。
