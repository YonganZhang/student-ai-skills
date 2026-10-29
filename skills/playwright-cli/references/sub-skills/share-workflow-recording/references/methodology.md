# 用户旅程录像方法论

## 核心定位

**不是测试金字塔 Layer 4** · 是**断言之上的 Acceptance Evidence + 移动端验收 Notification**。

| 层 | 工具 | 失败 = |
|---|---|---|
| 1 · unit / 合约 | pytest | 代码 bug |
| 2 · e2e backend | requests + db | 业务逻辑 bug |
| 3 · e2e UI 断言 | Playwright + assert | UI 不可见 |
| **★ Journey Recording** | Playwright + 视频 + GIF + Trace | **assert 过但人眼不对** + **移动端无法验收** |

**铁律**:Journey 必须含 deterministic assert · 视频只给人看 · AI 不报"录像看起来 OK"(它是文盲对视频)。

## 何时用

- web / 桌面客户端 / mobile webview
- 工作流明确(起点 + 终点 + 关键节点)
- 远程移动端验收 / 给老板/老师/客户看 demo

## 何时不用

- 纯后端 API(pytest 够)
- 一次性脚本(<200 LOC)
- prototype 早期 UI 每天大改(维护成本 > 价值)

## 共享 helper 用法

### wait_until_status(替代 magic timeout)

❌ 不要这样写:
```python
t0 = time.time()
while time.time() - t0 < 240:  # ← 写死 240 是地雷
    time.sleep(7)
    ...
```

✅ 应该这样:
```python
from share_workflow_recording.recording_helpers.wait import wait_until_status

result = wait_until_status(
    poll_url=f"{SITE}/v1/projects/{slug}/ai-renders",
    extract_status=lambda d: (d.get("renders") or [{}])[0].get("status"),
    terminal=("done", "failed"),
    max_seconds=600,  # 给充足余量(fal.ai retexture 极端 400s)
    cookies=api_cookies,
    on_progress=lambda t, st, d: print(f"  [{t}s] status={st}"),
)
# 此处 result 保证是 terminal status · 没到 terminal raise WaitTimeout
```

### abort 时产证据

❌ 不要静默退出:
```python
if not done:
    ctx.close(); browser.close()
    return None
```

✅ 应该:
```python
import json

if not done:
    screenshot = OUT_DIR / "abort_last_frame.png"
    page.screenshot(path=str(screenshot))
    record_path = OUT_DIR / "abort_backend_record.json"
    record_path.write_text(
        json.dumps(fetch_backend_record(slug), ensure_ascii=False, indent=2)
    )
    print(f"ai-render {max_seconds}s 未完成；状态={last_status}")
    print(f"失败证据：{screenshot}、{record_path}")
    raise SystemExit(2)
```

## 反例

| 坑 | 教训 |
|---|---|
| polling 240s 写死 → fal 抽风 250s · 静默退出录空白 | 用 `wait_until_status` · 留 2x 余量 |
| SSE `INCOMPLETE_CHUNKED_ENCODING` 导致 frontend tab 渲染失败 | step 间 reload retry · 加 selector wait + count check |
| backend Blender `replay-5-tier.sh exit 1` · 静默被脚本当 transient | 显式查 `job.error_json` · 写 db record 到 abort 证据 |
| 失败后静默退出 · 用户无感 | 保存截图 + JSON record，并在当前对话报告 |
