# 组件可视化覆盖层(演示录像的观感层)

> 触发:给演示加个炫酷效果 / 组件可视化 / show 一下前端结构 / 让观众看出这是真组件 / component inspector overlay
> 不触发:AI 自己要定位元素、要写断言、要做回归录像 — 那些跟本层无关(见 §2)

## 1 · 这是什么

演示录像里的前端很容易被当成"黑箱截图或套壳 UI"。叠一层**组件级 overlay**(hover 时高亮组件边框 + 浮出组件名和源码路径),观众一眼看出**这是真实组件树在渲染**。

纯观感层,不改产品行为,可随时开关。

## 2 · 🔴 只对人类观众有用 · 对 AI 自己零帮助

AI 操作浏览器靠 **DOM / accessibility tree / snapshot ref**,不看像素。打开这层**不会**让 AI 更会点按钮、更会找 selector、更会验收。

- ❌ 不要为"让我自己更好操作页面"打开它
- ❌ 不要把 overlay 当断言依据(断言仍走父技能的后端 log 信号 + DOM 真信号)
- ✅ 它唯一的收益方是屏幕另一头的人

## 3 · 默认关闭

| 场景 | 开关 |
|---|---|
| 正式产品演示录像(给老师 / 老板 / 客户) | **关** — 画面干净,overlay 会遮真实 UI |
| 用户明确说"展示技术细节 / 炫酷效果 / 证明是真组件" | 开 |
| AI 自跑 e2e、回归录像、验收证据 | **关** |

不确定就先关,再问用户。

## 4 · 怎么做 — Vite 项目(lobehub 实证)

包:`code-inspector-plugin`。挂在 `plugins/vite/sharedRendererConfig.ts` 的 plugin 数组:

```ts
isDev && process.env.DISABLE_CODE_INSPECTOR !== '1' &&
  codeInspectorPlugin({ bundler: 'vite', exclude: [/\.(css|json|html)$/], hotKeys: ['altKey', 'ctrlKey'] })
```

三要素:① **dev-only**(`isDev` 短路,不进生产);② **单一 env 开关**(`DISABLE_CODE_INSPECTOR=1 pnpm dev` 即关);③ **`hotKeys` 决定观众按什么键才出 overlay**。

录像时若要画面"自动出效果",必须让脚本按住修饰键(Playwright `keyboard.down('Alt')` + `keyboard.down('Control')`)或临时把 `hotKeys` 配空 — 否则录出来什么都没有,别误判成开关坏了。

## 5 · 非 Vite 栈 — 方向性判断(不展开教程)

- `code-inspector-plugin` 自己就多 bundler(vite / webpack / rspack / turbopack),**先查它的 `bundler` 选项,不要另造轮子**。lobehub 的 Next 侧就是同一个包,以 `bundler: 'turbopack'` 挂在 `src/libs/next/config/define-config.ts` 的 `turbopack.rules` 里。
- ⚠️ **同一 repo 两条构建链的开关可能不同步**:lobehub Vite 侧有 `DISABLE_CODE_INSPECTOR`,Next/turbopack 侧当时只按 `isTest` 判,没接同一个 env。**改开关前先确认这次录像走哪条构建链**,否则改到没生效的那条。
- 纯 React 无构建插件 / 只能碰线上站点:退化方案是用 Playwright `add_init_script` 注入一段 hover outline 脚本,靠 React fiber(`__reactFiber$` 前缀属性)取组件名。能力弱且脆,只在真的需要时做。
- 搜索方向关键词:`<bundler> component inspector plugin`、`click-to-component`、`react-dev-inspector`。

## 6 · 🔴 验证开关是否真生效 · 必须拆帧肉眼看

**本次踩的坑**:只查 DOM 属性(`data-insp-path` 一类)的数量来判断开关生效 —— 这是**无效验证**。

为什么无效:
- 属性注入和 overlay 渲染是**两件事**,属性还在但 overlay 不出、或反过来,都可能发生
- overlay 常挂在插件注入的独立节点或 shadow root,普通 DOM 查询根本看不到
- overlay 只在**按住 hotKeys 且 hover** 时出现,静态快照必然是空

正确做法:
1. 开 / 关各录一段**动作相同**的短视频
2. 拆帧:`ffmpeg -i demo.mp4 -vf fps=2 frames/%03d.png`
3. **人眼**比对同一时刻的两组帧
4. 只有肉眼看到差异,才能说"开关生效"

**通用化**:任何**视觉效果开关**的验收都套这条 —— 视觉产物只能用视觉证据验收。这跟父技能的定位("断言过但人眼不对")同源。

---

关联:录像本体流程见 `../SKILL.md`;录像卡死自诊断见 `ai-self-diagnose-ladder.md`。
