# 等待完成的陷阱：streaming 信号与 SPA wait

用途：写或调试 Playwright 录像脚本的等待逻辑（等 LLM 回复完成、等 SPA 页面就绪）时读。

## v2.3 陷阱 4:**stage 触发 ≠ streaming 完成 ≠ 前端渲染完成**

**症状**:截图里 LLM 响应**才刚开始 streaming**(图件说明 + 表头 + 第 1 节标题),完整 markdown、图片和后续解读还没渲染完,录制就停了。

**根因 3 段递进**:
1. 后端 stage 信号(如 `result_decorate.stage:189`)真触发时机 = LLM **开始 streaming**(不是结束)
2. 之后真 LLM 真持续 push token 30-60s + tool 链可能继续(transfer 触发新 SubAgent)
3. 即使后端真停了 · 前端真 fetch image / 渲染 markdown 真还需 5-15s

**反模式**:
- 🔴 `SILENCE_S` 只看真同名 stage 真无新出现(可能 cycle 真新 stage 都在结尾 burst → 立刻 true)
- 🔴 wait 完成立即截图(0-2s buffer)

**治本(双信号 + 前端 buffer)**:
```python
def wait_llm_done(label, pre_lines, max_wait):
    stage_seen = False
    last_lines, last_change_at = log_lines(), time.time()
    SILENCE_S = 10.0   # log 真整体真停才算完
    while elapsed < max_wait:
        # 信号 1: cycle 已启动
        if not stage_seen and grep_stage(pre_lines) > 0:
            stage_seen = True; last_change_at = now
        # 信号 2: log 整体真无新行 SILENCE_S 秒
        if stage_seen:
            cur = log_lines()
            if cur > last_lines: last_lines = cur; last_change_at = now
            elif (now - last_change_at) > SILENCE_S: return True
        sleep(1)
# 真录像 wait 完成后 真额外 8s 前端渲染 buffer
page.wait_for_timeout(8000)
```

**通用承诺**:任何后端 streaming 真信号都不是"完成"信号 · 真**必须叠加** log 真整体静默 + 前端真渲染 buffer。

## v2.6 Playwright SPA wait 陷阱

🔴 **永远不用 `wait_until="networkidle"` / `wait_for_load_state("networkidle")`** 在 SPA 项目(任何含 WebSocket / SSE / 长连接的前端)。

**根因**:SPA 持续 WebSocket(dingtalk_stream / 即时通讯)+ SSE keep-alive + service worker keepalive → **networkidle 永远不达到** → timeout 20s exit。

**卡住时**:不要擅自改走 REST 绕开 UI(那就不再是用户视角的验收),停手汇报;写新脚本前先找项目里已经跑通的录像脚本。

✅ **正确模式**（优先参考项目现有 proven 录像脚本）:
```python
page.goto(url, wait_until="domcontentloaded", timeout=20000)  # 改 domcontentloaded
page.wait_for_timeout(2000)  # 固定等 SPA hydrate(关键!)
page.wait_for_selector(".specific-element", timeout=10000)  # 等具体元素 · 不等 networkidle
```

**适用范围**:所有走 playwright-cli 子技能 share-workflow-recording 的 Playwright 录像 · 跨项目。

**自检 checklist**(cc 写 Playwright 脚本前必走):
- [ ] `grep "networkidle"` 自己脚本 → 0 hit
- [ ] 参考项目现有 proven 录像脚本（若有）
- [ ] SPA hydrate buffer 用 `wait_for_timeout` 显式等(不是等"网络静默")
- [ ] 关键元素 `wait_for_selector` 不等 load_state
