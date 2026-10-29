# 场景 E2E 用户旅程 SOP(跨项目通用元思维)

> **元思维抽象** · 任何项目"用户进入页 → 选某模板/场景 → 模拟用户操作 → 验证后端返"都套这套。
> **本文档不含项目级细节**(emoji 否决 / 具体动画风格 / scenario 数 / chip 名 等都是项目级)· 项目级具体落到 `<project>/wiki-methodology/top/decisions/<date>-e2e-test-sop.md`。

## 元思维:为啥要固化(从 4 个坑抽)

任何项目做 e2e 录像测试 · 都会撞这 4 个坑:

| # | 坑 | 元根因 |
|---|---|---|
| 1 | 视频看不到鼠标 | Playwright headless 默认不渲染光标 · 无视觉反馈 |
| 2 | 点击没动效反馈 | force=True click 直接砸 · 视觉像"瞬移"不像用户 |
| 3 | 选中态没体现 | 选完场景 · 用户不知道"选了"· 只 textarea 文字 = 信息不可见 |
| 4 | 没 SOP 锁 LLM 行为 | 单句 prompt · LLM 自由发挥 · 测试结果不可复现 |

**元修法**:固化 7 阶段 SOP + 4 决策点 + 4 UI 硬要求 + 5 段标准录像脚本结构。

## 7 阶段 SOP(每场景必走)

```
S1 选场景  → hover 列表/卡片 → 停 → 点击    →【截图: 选中态有反馈】
S2 备数据  → 上传指定测试文件(场景预定义)    →【截图: attachment 出 + filename 显示】
S3 编辑    → welcome_prompt 自动塞 + 用户追加→【截图: input 含完整 prompt】
S4 发送    → click send · 后端 启动            →【network 有调】
S5 返    → 等 + 截 +  grep log           →【log 找到预期 tool/endpoint】
S6 多轮    → 用户追问 2-3 轮(模拟对话)     →【每轮验】
S7 报告    → 聚合 7 阶段证据 → PASS/FAIL         →【markdown 报告】
```

## 4 关键决策(项目首次启用 SOP 时拍板)

### Q1. welcome_prompt 升级方式?

| 选 | 含义 |
|---|---|
| A | 单句 prompt → step-by-step SOP("1. parse · 2. classify · 3. shap · 4. 报告"明确锁) |
| B | 不改 prompt · LLM 自由发挥 |
| C | yaml 加 `expected_tool_calls: [tool1, tool2, ...]` 锁 |
| **D 推荐** | A + C(prompt 引导 + yaml 锁锚) |

### Q2. "测过" 标准?

| 选 | 含义 |
|---|---|
| A | LLM 返非空就过 |
| B | 必须 grep 后端 log 找到 ≥ N  tool 调 |
| C | 必须 LLM 返字段含 specific keys |
| **D 推荐** | A + B + C 全要(全自动 PASS/FAIL) |

### Q3. 录像策略?

| 选 | 含义 |
|---|---|
| A | 每场景独立 mp4(N 场景 = N mp4) |
| B | 1 个 long mp4 串联(难看) |
| **C 推荐** | 每场景 5 截图 + 30-60s mp4 highlight + 1 markdown 报告 |

### Q4. 自动化 vs 手动?

| 选 | 含义 |
|---|---|
| **A 推荐** | 完全自动(Playwright 跑 N 场景 · auto 截图 + auto grep + auto PASS/FAIL) |
| B | 半自动(自动跑 + 人复审关键场景) |
| C | 手动(1 个 1 个做) |

## 4 UI 硬要求(防 4 坑 · 项目级具体样式自定)

### 改 1 · 鼠标可视化(Playwright headless 补 · **跨项目通用 JS**)

```python
CURSOR_JS = """
() => {
  const dot = document.createElement('div');
  dot.style.cssText = 'position:fixed;width:16px;height:16px;border-radius:50%;'
    + 'background:rgba(255,0,0,.85);border:2px solid white;pointer-events:none;'
    + 'z-index:99999;transform:translate(-50%,-50%);transition:transform .08s';
  document.body.appendChild(dot);
  document.addEventListener('mousemove', e => {
    dot.style.left = e.clientX + 'px';
    dot.style.top = e.clientY + 'px';
  });
  document.addEventListener('mousedown', () => dot.style.transform = 'translate(-50%,-50%) scale(.6)');
  document.addEventListener('mouseup', () => dot.style.transform = 'translate(-50%,-50%) scale(1)');
}
"""
page.evaluate(CURSOR_JS)
```

### 改 2 · 点击反馈动效(**抽象要求 · 项目级 CSS 自选**)

任何"卡片/选项"点击 · CSS 必须有视觉反馈。最低标准:`transform: scale()` + 颜色 / 阴影 变化 · 200-600ms 动画。

**项目级选风格**(本 SOP 不指定):
- 弹动效(scale 1.2 + glow)
- shadow flash
- 颜色 reverse
- 圆环波纹(ripple)
- 其他

### 改 3 · 选中态视觉显示(**抽象要求 · 项目级具体落地自定**)

选完场景 · **必须有 UI 元素显示"已选 X"** · 不能只是后台 state · 也不能只是 textarea 文字。

**项目级落地选项**(SOP 不指定具体):
- 上方 banner(滑入动画 · 含图标 + 标题 + step 提示 + ✕ 取消)
- 浮 chip
- 全屏 modal 确认
- 卡片飞到 input 上方
- 其他

**硬要求**:必须**可取消**(✕ 按钮 / 点空白处 / ESC 等)· 用户有出路。

### 改 4 · 弹幕/列表 用户旅程(Playwright 用法)

```python
# 用户旅程(非 force=True 砸)
cards = page.locator(".scen-card").all()
target = cards[0]
target.hover()                #  hover · CSS 暂停滚动
page.wait_for_timeout(1500)  # 停让看清
target.click(force=False)    # 让 Playwright 等 stable
```

## 5 段标准录像脚本结构(任何项目套)

```python
def record_scenario_journey(scenario_id, test_data_path, expected_tools, expected_keys):
    """通用 e2e 录像入口 · 任何项目套同结构"""
    # === Setup ===
    inject_cursor(page)         # 改 1
    login_user(page)
    goto_chat_entry(page)

    # === S1-S2 选场景 + 备数据 ===
    hover_then_click_scenario(page, scenario_id)
    page.locator('input[type="file"]').set_input_files(test_data_path)

    # === S3-S4 编辑 + 发送 ===
    page.locator('textarea').type(extra_user_prompt, delay=80)
    page.locator('.send-btn').click()

    # === S5 等返 ===
    page.wait_for_timeout(40000)

    # === S6 多轮追问(2-3 轮)===
    for round_prompt in rounds_2_3:
        page.locator('textarea').type(round_prompt, delay=80)
        page.locator('.send-btn').click()
        page.wait_for_timeout(30000)

    # === S7 报告 ===
    log = read_backend_log()
    tools_hit = grep_tools(log, expected_tools)
    keys_hit = check_llm_response_keys(page, expected_keys)
    write_markdown_report(scenario_id, tools_hit, keys_hit, screenshots, mp4)
    return all(tools_hit) and all(keys_hit)
```

## 跨项目复用承诺

1. **任何 web 项目** 加场景模板系统都套本 7 阶段 + 4 决策 + 4 UI 硬要求
2. 项目级 SOP 文档链回本全局 skill(单一源)
3. UI 硬要求**只定抽象规则** · 项目自选具体落地风格(动画 / 配色 / 文案 / 输入习惯)
4. 录像脚本 5 段结构不变 · 项目级只填 scenario_id / test_data_path / expected_tools / expected_keys

## 使用触发(任何项目说)

- "录场景测试视频"
- "e2e 用户旅程录像"
- "测我的模板/场景系统"
- "鼠标看不到 · 点击没动效"(单条改 1-3)
- "固化测试 SOP"(全套)

→ cc 立刻 load 本文档 · 按 7 阶段 + 4 决策 + 4 UI 要求走 · 不重新设计。

## 案例引用(单一参考 · 不复制具体)

- 项目级 SOP 放项目自己的决策记录(如 `<project>/_wiki-methodology/_top/decisions/<日期>-e2e-test-sop.md`)
  - 项目级具体:视觉反馈方案取舍 / 场景测试列表 / 测试数据路径

本全局 skill**只锁 SOP 元结构** · 项目级具体细节不进。

## 陷阱 1 · Playwright `.click(force=True)` 不能触发 Vue/React @click

**症状**:
- 用 `target.click(force=True)` · Playwright 报 success
- 但 Vue/React 组件的 `@click` 没跑(state 没 set · 事件没 emit)

**根因**:
- `force=True`  bypass element stable 检查 · 但 click 位置可能漂移到动画中其他位置
- 打到的 DOM element 跟用户预期不一致 · Vue listener 没触发

**修法 · 必用 native JS click**:
```python
page.evaluate("""() => {
  const cards = document.querySelectorAll('.scen-card');
  for (const c of cards) {
    if (c.textContent.includes('一键测井岩相')) { c.click(); break; }
  }
}""")
```

** verify 用 page.evaluate 查 DOM**:
```python
info = page.evaluate("""() => ({
  banner_in_dom: !!document.querySelector('.your-target-class'),
  draft_value: document.querySelector('textarea')?.value,
})""")
```

**触发**:任何"clicked 但 state 没变 / event 没 emit / banner 没出现" → 立刻怀疑此陷阱 · 改 native JS click。

## 陷阱 2 · `wait_for_function('.loading-class > 0', timeout=8000)` 假完成

**症状**:
- 录像 每轮 "4-5s 完成" · 不可能(LLM  30-60s)
- 接着发下一轮 · 上轮还在跑 →  LLM 上下文错乱

**根因**:
- `wait_for_function` 等 `.loading-message length > 0`  8s timeout(LLM 思考 10-20s 才出 streaming)
-  except 走 `=== 0` 初始就 true →  immediately pass → 假完成

**修法 · 用后端 log polling 稳信号**:

```python
def wait_llm_done(label, pre_lines, max_wait=240):
    """信号:后端 log 新 send_message_to_user 后 5s 静默 = 完成"""
    import subprocess, time
    t0 = time.time()
    last_count = 0
    last_seen_at = None
    SILENCE_S = 5.0
    while time.time() - t0 < max_wait:
        result = subprocess.run(
            ["awk", f"NR>{pre_lines}", "/tmp/backend.log"],
            capture_output=True, text=True
        )
        count = result.stdout.count("send_message_to_user")  # 项目级 完成 signal
        now = time.time()
        if count > last_count:
            last_count = count; last_seen_at = now
        if last_seen_at and (now - last_seen_at) > SILENCE_S:
            return True, now - t0
        time.sleep(1.0)
    return False, time.time() - t0
```

**项目级 信号 自定**(本 SOP 不锁具体 grep 词):
- 基于 AstrBot 的项目:`result_decorate.stage:189]: 流式输出已启用`(单次消息处理 cycle 完成 · 每轮 1 次)
- 其他项目:`stream done` / `response complete` / `generation finished`

**坑**:**不要**用 LLM 的最终回复 tool(如 `send_message_to_user`)当完成信号——长 tool 链下 LLM 很久才调到它,timeout 会先到,造成假完成。
**用消息处理 cycle 的 stage 信号**(如上面 AstrBot 的 `result_decorate.stage`)——处理完一轮就触发、每轮 1 次,稳定。

**触发**:任何"假完成 / 多轮上下文错乱 / wait_for_function  except 落空" → 改 后端 log polling。

## 陷阱 3 · 服务端口假定

**症状**:
- 脚本 hardcoded port → 服务 listen 别 port → 录像"看似跑通"但根本没连进后端
- 后端 log 有活动 → 误以为脚本在工作 · 其实是用户在网页用

**修法 · 脚本启动前探**:
```python
def detect_port(candidates):  # 候选端口从项目 config 读,不写死
    import subprocess
    for p in candidates:
        try:
            r = subprocess.run(
                ["ss", "-tlnp"], capture_output=True, text=True, timeout=2
            )
            if f":{p} " in r.stdout:
                return p
        except Exception: pass
    raise RuntimeError(f"无 listen 端口  candidates={candidates}")

PORT = detect_port(project_config_ports)
page.goto(f"http://localhost:{PORT}/")
```

**触发**:每次 录像 / e2e 前 不假定 port · 从 `ss -tlnp` / 项目 config 读当前。
