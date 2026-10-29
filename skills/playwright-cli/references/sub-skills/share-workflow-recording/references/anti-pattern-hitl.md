# anti-pattern catalog · HITL 协议

用途：录像 / 用户使用 / audit fail 中发现 LLM 行为偏离预期、准备把踩坑写进场景 `anti_patterns` 时读。对应入口 §5.5（`audit-after-record.sh` 的 HITL 建议指向此处）。

## v2.5 anti-pattern catalog · HITL 协议

**为什么**:LLM 行为天生不稳 · 但**踩过的坑可以写进 SOP** · 让 LLM 下次 prompt 就看到"上次错在哪" — 避免重复犯。

**HITL 关键**:
- 🟢 cc 自动:scenarios.yml 真 anti_patterns 字段 维护 + script append
- 🔴 用户决策:**根因判断** / **要不要 append** — 防 cc 局部最优死循环

**流程**（项目内可选 `append_anti_pattern.py` 脚本）:
```
1. cc 发现 LLM 踩坑 → 自己分析根因 → 生成 draft
2. cc 跑 dry-run(无 --confirm)→ 打印根因 + draft + 已存 anti_patterns
3. cc 汇报给用户:"我觉得是 X 问题 · 想加 Y · 你看?"
4. 用户文字 confirm yes/no/改
5. cc 加 --confirm 真**真**真再跑 → 自动 append yaml + commit
```

**注入自动化**(`ScenariosRoute.list_scenarios`):
- yaml 真 anti_patterns 字段自动 append 到 welcome_prompt 末尾
- 前端 LLM 真选场景就看到"⚠ 历史踩坑 · 必避免"段
- LLM **下次会看到** 上次错 · 不重复犯

**反承诺**:
- 🔴 cc 不自动 append(必 dry-run + 用户 confirm)
- 🔴 不写无根因 anti_pattern(--reason 真必填)
- 🔴 不重复 append 已存 anti_pattern(先看已存条目避重)

**真触发场景**:任何录像 / 用户使用 / audit fail · cc 发现 LLM 行为偏离预期 → 立刻 dry-run draft → 真汇报 + 真等用户。
