# 审计门禁策略与失败归因

用途：录像 audit 出现红/黄字、有人想拿录像 audit 当 push 门槛、或要判断是产品 bug 还是录像 bug 时读。对应入口 §5.4（`scripts/audit-after-record.sh` 注释里的「§5.4 元承诺」即此处）。

## v2.4 元承诺:**测试金字塔 — 录像是演示 · 不验证**

**根因**:把"录像 audit 100% ✅"当 push 门槛,会陷入"改一处 → 再录"的死循环——它**违反 LLM 输出随机的本质**。

**真**真**金字塔正确分工**:
```
        ┌──────────┐
        │ 录像 e2e │ ← 演示 (showcase) · 接受 LLM 不稳 · 真 informative
        ├──────────┤
        │ branch   │ ← 集成验证 (mock LLM) · 真 deterministic
        ├──────────┤
        │ trunk    │ ← 单元验证 (mock event + 真数据) · 真 100% 真 deterministic
        └──────────┘
                      ↑ gate push 真**这层**
```

**真承诺**:
- 真**plugin tool 是否 work** → 真**真**真 trunk 单元测试真验证(如 `test_classify_lithology_smoke.py`)
- 真**SubAgent 链通不通** → branch 集成测试真(mock LLM)
- 真**用户视角真演示** → 真 e2e 录像真**informative · 不 gate**

**audit gate 策略 v3**(audit-after-record.sh):
- 真**STRICT tools** 未调 → 🔴 exit 1(真**真**真**真 gate** 真**因为**真 plugin 真没真接通 真**真这是真 plugin 问题**)
- 真**SHOULD tools / INTENT keys / METRICS** 未匹配 → 🟡 WARN(不 gate · 真因为真 LLM 真行为不稳 真**真**真**真**自由实现 真没真按 audit 真预期路径)

**反承诺**:
- 🔴 真不再追求 "录像 audit 100% ✅"
- 🔴 真不再"audit fail → 改一处 → 再录" 真死循环
- 🔴 真不再让 audit 信号真 gate 真 push(只 STRICT gate)

**触发**:任何"录像 audit fail · 真**真**真**真**真要 gate push" → 真**真**真**先问** 真"真**真**真**真**真是 plugin 真没接通(STRICT fail)真还是 LLM 真自由实现(SHOULD/INTENT 真 WARN)?"

## v2.2 关键洞察:audit 真区分录像 bug vs 产品 bug

audit 🟡 / 🔴 不一定是录像 SOP 问题 · **常常 catch 到真实的产品架构 bug**:

| 现象 | 真根因 |
|---|---|
| `tool X 未调` 真 SHOULD warning | tool 可能没注册 / persona whitelist 漏 / SubAgent 间 state 不传 / prompt 不够强 |
| `INTENT key 缺失` | LLM 真的没按 SOP 出 4 段结构 → prompt 或 persona system_prompt 缺 |
| `METRICS 数字不达标` | 模型真不行 · 不是 audit 问题 · 该开 finding |

**承诺**:audit 红/黄字真出 · 先**问"是产品 bug 还是录像 bug"**,不要直接改 SOP cheat audit · 先开 finding 记录架构层问题(示例:一次录像审计的 SHOULD 警告,最后查出是 SubAgent 间 cache_id 不传的产品 bug)。
