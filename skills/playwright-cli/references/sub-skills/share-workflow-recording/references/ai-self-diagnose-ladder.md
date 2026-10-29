# AI 自诊断手段阶梯 · 录像/E2E 自动化通用

> 任何执行代理在 E2E / 录像卡死时按本阶梯走,**不冲动 retry**(retry = 不解释根因 = 反模式)。
> 触发:selector timeout / 录像挂 / SPA 渲染未完 / hydration race / DOM dump 找不到 / 协作卡死

## 哲学

执行代理**无可靠视觉判读能力**(无 vision)→ 必须靠**结构化文本**自诊断 → 阶梯穷尽时**走人工视觉判读协作**(human-in-the-loop)。

## 阶梯(按"代理可读性"递增 · framework-agnostic)

| 层 | 探针 | 用途 | 代理能读? |
|---|---|---|---|
| **L0** | 阶段日志(每步开头 stdout) | 定位"卡在哪步" | ✅ |
| **L1** | 截图(产物帧) | 给人看 | ❌ |
| **L2** | 原始 HTML 抓取(`page.content` 类) | server-render 页 / SSR | ✅(SPA 失效) |
| **L3** ⭐ | **渲染文本探针**(读 `document.body.innerText`) | **SPA**(React/Vue/Angular/SvelteKit/Solid) | ✅ 真渲染纯文字 |
| **L4** ⭐ | **交互元素清单探针**(枚举 input/button/a 的 type/id/name/aria/text) | 找真 selector / shadow DOM 边界探查 | ✅ JSON 列表 |
| **L5** | **人工视觉判读协作**(推视频 + 让人 F12 给 selector) | 阶梯穷尽 / 富文本编辑器 / canvas / iframe 跨域 | ❌ 代理 · ✅ 人 |

## 何时切下一层 · 决策表

| 症状 | 切到 |
|---|---|
| 不知卡哪步 | L0 |
| `page.content` 抓到 `<div id="app"></div>` shell | **L3**(SPA 信号) |
| L3 读到 "Submit" 字样但 `locator('text=Submit')` 仍超时 | **L4**(枚举 attrs 找真 selector) |
| L4 看到富文本/iframe/shadow DOM/canvas 类边界 | **L5**(代理穷尽) |
| 多次 timeout 加更大 timeout | **退回 L3/L4**(不是 timeout 问题) |

## 等待语义(代理常见误用)

- 🔴 **固定 sleep** = 反模式 · 用**可读状态**(`wait_for_function('window.__app_ready')`)
- 🔴 **network idle ≠ DOM ready** · idle 后 SPA 可能正 hydration
- 🔴 **hydration 期间 click** 会触发 race · 应 wait 框架可读信号
- ✅ **interaction-ready 探针**:存在性 + 可见性 + 可点击性三件套(`isEnabled` / `isVisible` / `isAttached`)

## 失败兜底铁律

1. **dump 不 crash** — L3/L4 探针失败用 try/except 包,**继续兜底**,不让脚本退出
2. **永不 silent retry** — retry 之前必跑 L3/L4 找根因 · 3 次仍挂 → L5
3. **沉淀踩坑** — 修复后立刻沉淀到项目的 demo 计划 / 踩坑记录(落点由项目定)

## 已知失效手段(避免踩坑)

- ❌ Playwright Python async `page.accessibility.snapshot()` 不支持(`Page` 无此属性) · JS sync 才有 · 用 L3/L4 代替

## 跨工具映射(L3/L4 是探针概念 · 工具是 instance)

| 工具 | L3 渲染文本探针 | L4 元素清单探针 |
|---|---|---|
| Playwright | `page.evaluate('document.body.innerText')` | `page.evaluate(() => [...].map(...))` |
| Cypress | `cy.get('body').then(b => b[0].innerText)` | `cy.get('input,button').then(...)` |
| Selenium | `driver.find_element('tag', 'body').text` | `driver.find_elements(...)` |
| Puppeteer | `page.evaluate(...)` 同 Playwright | 同 |

## 跟其他经验联动

- `share-top/references/test-trunk-branch-leaves.md §"AI self-debug 阶段定位机制"`:**阶段层定位**(卡在哪步)· 跟本文**手段层**(怎么自诊)正交互补
- 通用原则:诚实汇报 + 不 silent retry

## SOP 原则(不写 cookbook)

1. **失败先 L0 + L3 双 dump 落盘** · 不重跑
2. **L3 看清 UI · L4 找真 selector** · 改脚本不靠盲猜
3. **代理穷尽 → L5 协作** · 用户 5 分钟看视频 ≈ 代理 1 小时盲调 · 选前者
4. **沉淀** · 每次卡 + 修必沉淀到项目的踩坑记录
