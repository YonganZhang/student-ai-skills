# share-workflow-recording · playwright-cli 子技能(V2)

## 定位

**不是测试金字塔 Layer 4** · 是**断言之上的 Acceptance Evidence + 移动端验收 Notification**。

跟现有层关系:
- Layer 1-3(unit / e2e backend / e2e UI 断言)= 断言 = 防 bug
- 本层 = **证据 + 通知** = 防"断言过但人眼不对"+ 远程验收

## 按需读取

| 任务 | Reference |
|---|---|
| 本层方法论定位 | `references/methodology.md` |
| 单场景 e2e 录像 SOP | `references/scenario-e2e-sop.md` |
| 录像卡死 / selector 找不到 | `references/ai-self-diagnose-ladder.md` |
| 给演示加炫酷效果 / 组件可视化 / show 前端结构 | `references/component-inspector-showcase.md` |
| 首次锁审计信号、写 `audit-signals.yml`、场景 4 维锁 | `references/audit-signals-protocol.md` |
| audit 红/黄字怎么定性、录像能不能当 push 门槛 | `references/audit-gate-and-triage.md` |
| 把 LLM 踩坑写进场景 `anti_patterns` | `references/anti-pattern-hitl.md` |
| 写/调录像脚本的等待逻辑（LLM streaming、SPA 就绪） | `references/wait-completion-traps.md` |
| 搭配置化 journey pipeline 的观测层与易踩点 | `references/journey-runner-architecture.md` |

## 模块

```
modules/
└── recording-helpers/   # cursor / slow-type / wait_page_ready / wait_until_status
```

journey runner（setup / action / assert / export / cleanup 五段）与 `workflow-recording.yaml` 清单按项目实现，架构见 `references/journey-runner-architecture.md`；本 skill 不带这两个模块。

## 何时用

- 项目说"录视频 / 录工作流 / 跑 e2e demo / 给老师 / 老板看"
- 加新 web 项目需要"AI 模拟用户验收"基建
- 当前 workflow 脚本里有 magic number(timeout=240)/ 静默 abort / 没 status guard → **迁移到本 skill 的 helper**

## V1 已实现(Phase 1)

| Helper | 用途 |
|---|---|
| `wait_until_status` | 等 backend 显式 terminal status(done/failed/cancelled),不靠固定 timeout |

失败时保存截图和 backend record，在当前对话说明原因及证据路径；不静默退出。

## 5 · 已采用 AI 对话审计协议的项目：四类信号

本节只用于已采用该协议、且录像目标包含 AI 消息/回复/工具执行的项目。普通静态页面或非 AI 网站按真实 DOM、请求与目标行为验收，不创建不存在的 AI 信号。协议适用时保留项目已有的信号确认与审计约定。

### 5.1 四阶段协议(完整细节、示例与 yaml 模板见 `references/audit-signals-protocol.md`)

1. **首次锁信号**(per-project,1 次 confirm):首次在某项目录像必须和用户确认 5 件事(用户消息 / AI 返 / 完成 cycle / tool 链 四类 grep 信号 + log 路径);先 dry-run 4 个 grep 贴证据,用户确认"这就是你要的信号"才落盘 `<project>/.claude/audit-signals.yml`(Codex 项目为 `<project>/.codex/audit-signals.yml`;脚本先找 `.codex/` 再找 `.claude/`)。
2. **每次录后自动 audit**:`audit-signals.yml` 存在后,任何录像脚本完成都跑
   ```bash
   bash ~/.claude/skills/playwright-cli/references/sub-skills/share-workflow-recording/scripts/audit-after-record.sh \
     <project-root> <pre-log-line-baseline> <expected-rounds> [--scenario <id>]
   ```
3. **不一致即报红**:轮数不符、AI 返为 0、完成 cycle 为 0 → 红字报;绝不贴 mp4 假装成功,先和用户说"录了但假"并贴证据。
4. **零 happy path**:先 audit、后报 URL;必须和 baseline 比;截图只是最后一帧,不是整段证据。

### 5.2 何时触发本节

| 情况 | 行为 |
|---|---|
| **首次**在项目录像 | 必走阶段 1 锁信号 + 和用户 confirm |
| **已锁信号** 再录 | **自动**跑 audit-after-record.sh |
| **录后 audit 红字** | **先红字报用户** 后讨论修法 |
| **信号定义 过期** | 用户说"信号变了" → 重走阶段 1 |

### 5.3 场景级 4 维锁(v2.1)

基础 4 类信号只验"流程有没动";要验是否真调了预定义 skill / MCP / 算法,在 `audit-signals.yml` 加 `scenarios.<id>`(strict / should tools、intent keys、metrics),用 `--scenario <id>` 分级审计。yaml 结构见 `references/audit-signals-protocol.md`。

### 5.4 元承诺:录像是演示,不验证(v2.4)

- 只有 **STRICT tools 未调** → 🔴 exit 1(plugin 没接通);SHOULD tools / INTENT keys / METRICS 未匹配 → 🟡 WARN,不 gate。
- 不追求"录像 audit 100% ✅",不陷入"audit fail → 改一处 → 再录"死循环;plugin 是否 work 由 trunk 单元测试验证,SubAgent 链由 branch 集成测试(mock LLM)验证。
- audit 红/黄字先问"是 plugin 没接通还是 LLM 自由实现""是产品 bug 还是录像 bug",不改 SOP 去 cheat audit,先开 finding。金字塔与归因表见 `references/audit-gate-and-triage.md`。

### 5.5 anti-pattern HITL(v2.5)

发现 LLM 踩坑时 cc 先分析根因、dry-run draft 并汇报,**用户 confirm 后才 append**;不写无根因条目,不重复 append。流程与注入机制见 `references/anti-pattern-hitl.md`。

### 5.6 等待完成陷阱(v2.3 / v2.6)

- SPA(含 WebSocket / SSE / 长连接)**永远不用** `networkidle`;用 `domcontentloaded` + 显式 hydrate 等待 + `wait_for_selector`。
- 后端 stage / streaming 信号不是"完成"信号,必须叠加 log 整体静默 + 前端渲染 buffer。
- 卡住时不要擅自改走 REST 绕开 UI,停手汇报;写新脚本前先找项目里已跑通的录像脚本。代码模板与自检清单见 `references/wait-completion-traps.md`。

## 6 · journey-runner + 铁律:每个 pipeline 必带自驱检测架构

配置化 journey pipeline(runner / observer / steps / journeys yaml)把"AI 操作/测试浏览器"固化成可增删流程的 pipeline;参考实现、观测层与已知易踩点见 `references/journey-runner-architecture.md`。

### 6.1 铁律 — 每个 pipeline 都必须有自驱检测架构

- **逐步断言**:每一步 = action + assertion 绑定(`ctx.assert_(name, ok, detail)`),不是跑完整段再回看。
- **真信号优先**:断言基于后端状态 / DOM / 网络 in-out,**绝不靠截图**(截图太慢、看不到弹窗、会被假完成骗)。
- **anti-fake-completion 结构化**:honesty gate 必须让"手动 API / 外部 curl 触发的产物"物理上无法点亮断言 —— 因为观测层只挂 page 网络钩子,浏览器没发的请求不进事件流。
- **可插拔 = 改 manifest**:增删流程只改 yaml 的 steps 清单,不动执行器。新步 = 加一个 `steps/<name>.py` 的 `run(ctx)`。

## GUI 变更证据

涉及用户可见 GUI 行为时，记录真实服务/传输、对应源码 commit 或树状态和实际动态证据；除非项目明确允许，不用 fixture 冒充验收。录屏是行为证据，不替代针对性测试；只有用户、PR 或项目门禁明确要求时才发布 GIF。
