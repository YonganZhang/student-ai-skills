# 录后审计协议：锁信号、自动审计、场景 4 维锁

用途：首次在项目录像需要锁信号、编写或修改 `audit-signals.yml`、需要场景级 4 维锁时读。入口 §5 只保留门禁摘要。

## 元承诺(每次录像 不可绕)

> ****录像 **不靠"看起来 ok" · **都靠**后端 log 证据。**"假完成 / 假调用 / 假返"零容忍**。

## ** 4 阶段 协议**(任何项目录像 都套)

### 阶段 1 — **首次锁信号**(per-project · 1 次 confirm)

cc **首次**在某项目 录像时 **必须**和用户**确认 5 件事**:

| # | 要锁 | 示例(一个基于 AstrBot 的 AI 对话项目)|
|---|---|---|
| 1 | **用户消息**信号 | `grep core.event_bus.*<username>:` |
| 2 | **AI 返**信号 | `grep "使用工具：send_message_to_user，参数："` |
| 3 | **完成 cycle**信号 | `grep "result_decorate.stage:189"` |
| 4 | ** tool 链**信号 | `grep "使用工具：" → uniq` |
| 5 | **log 路径** | `/tmp/<app>.log`(项目级 自定) |

**存到** `<project>/.claude/audit-signals.yml`（Codex 项目为 `<project>/.codex/audit-signals.yml`；`audit-after-record.sh` 先找 `.codex/` 再找 `.claude/`）:

```yaml
project: <project-name>
audit_signals:
  log_path: <后端 log 路径>
  user_msg_grep: "<用户消息信号>"
  ai_reply_grep: "<AI 返回信号>"
  cycle_done_grep: "<完成 cycle 信号>"
  tool_trace_grep: "<tool 调用信号>"
confirmed_by_user: <YYYY-MM-DD>
```

******第一次录像 cc 先 dry-run  4 个 grep 贴证据给用户 确认"这就是你要的信号"** · 用户 OK 才落盘 audit-signals.yml。

### 阶段 2 — **每次录后自动 audit**(零额外成本)

 `audit-signals.yml` 存在 后 · **任何录像脚本完成时 都 自动跑**:

```bash
bash ~/.claude/skills/playwright-cli/references/sub-skills/share-workflow-recording/scripts/audit-after-record.sh \
  <project-root> <pre-log-line-baseline> <expected-rounds>
```

**自动核 5 件事**:
1. 用户消息 grep count == 期望轮数(R1/R2/R3 → 应该 3)
2.  AI 返 grep count ≥ 用户消息 count(每轮至少 1 返)
3. 完成 cycle  count == 用户消息 count(每轮 1 cycle)
4.  tool 链 grep count > 0(至少有 tool 调用)
5. **完整 dump**:用户原话 前 200 字 + AI 返前 500 字

### 阶段 3 — **不一致 即报红**(零藏匿)

 audit-after-record.sh 任何不符:
- 用户消息 count ≠ 期望 → **红字报** "发了 3 轮 ·  log 只见 N 轮"
-  AI 返 count == 0 → **红字报** " LLM 根本没返"
- 完成 cycle  count == 0 → **红字报** "假完成"

**红字出现 → 绝不**贴 mp4 假装成功** · ****先和用户说"录了 ****但 ****假" + 贴证据。

### 阶段 4 — **零 happy path 承诺**

**反模式**:
- 🔴 不 `tail mp4 → "已录"` 就贴 URL(必跑 audit)
- 🔴 不"信号没动 我以为 work"(必和 baseline 比)
- 🔴 不"我只看截图 截图 ok 就行"(截图是**最后一帧** · 不是 整段证据)
- ✅ **先 audit · 后报 URL** · **任何不一致 红字先报**

## **何时触发本节**

| 情况 | 行为 |
|---|---|
| **首次**在项目录像 | 必走阶段 1 锁信号 + 和用户 confirm |
| **已锁信号** 再录 | **自动**跑 audit-after-record.sh |
| **录后 audit 红字** | **先红字报用户** 后讨论修法 |
| **信号定义 过期** | 用户说"信号变了" → 重走阶段 1 |

## **元思维为啥这样**

**单 AI + 单用户 = 讨好型危险**。录像是"自己测自己" → **自然讨好倾向 · "假完成"不报**。

**把"看起来录的 ok" → 换成 "后端 log 证据 齐全"** — 客观信号取代主观判断。**这就是反讨好在录像层承诺**。

## v2.1 升级:scenario-level 4 维锁

基础信号(4 类)只验"流程有没动",**不验 LLM 是否真调了预定义 skill / 算法**。要验证的是:是否真调了预定义 skill / MCP / 算法,而不是 LLM 凭预训练知识编出来的。

加 `audit-signals.yml` 真 `scenarios.<id>` 节,每场景 4 维锁:

```yaml
scenarios:
  <scenario-id>:
    min_rounds: N
    expected_tools_strict:   # 必中 · 缺即 🔴
      - <plugin tool name>
    expected_tools_should:   # 应中 · 缺即 🟡 warning
      - <plugin tool name>
    expected_intent_keys:    # AI markdown 必含
      - <keyword>
    expected_metrics:        # 数字阈值
      - { name: "<regex>", op: gte, value: <number>, desc: "<desc>" }
```

`audit-after-record.sh <project> <baseline> <rounds> --scenario <id>` 真按 yaml 分级审计。
