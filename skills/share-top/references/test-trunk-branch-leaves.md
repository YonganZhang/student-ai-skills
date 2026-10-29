# 测试三层 · 主干 / 分支 / 枝叶 + SSDO(通用 software 项目)

> 任何 software 项目 v4 COL 3 tests 都该按这三层组织。
> 对有 pipeline / 服务 / trace / status / report 的 software 项目,COL3 还必须有 SSDO/audit-first 入口:测试失败和 debug 第一动作是读真实过程,不是凭印象猜。

---

## 修复与回归

修复会复发的行为错误时，把最小复现放在能覆盖真实输入、边界和用户可见结果的测试层：修前失败，修后通过。缺少可测边界时先处理这个缺口；不为可逆的低影响修改或实现细节逐条增加测试。测试入口与证据沿用项目现有目录。

## 三层定义

| 层 | 是什么 | 工具 | 真源位置 |
|---|---|---|---|
| 🌳 **主干** | 端到端**用户行为**录像 · 真浏览器 · 真服务器 | Playwright / Cypress | `_wiki-methodology/_tests/trunk-recording/` |
| 🌿 **分支** | **跨多组件**集成测试 · 真 DB 真 SSE | pytest + test client | `_wiki-methodology/_tests/branch-modules/` ↔ `<lang>/tests/integration/` |
| 🍃 **枝叶** | **单函数 / 单类**纯逻辑 unit | pytest / jest | `_wiki-methodology/_tests/leaves-unit/` ↔ `<lang>/tests/contract/` |

---

## 关键约定(三条铁律)

### 🔴 1. 枝叶绿 ≠ 主干绿

```
单元测试 100% 过  ≠  用户看到的功能能用
枝叶绿是必要不充分条件 · 主干必须真用户视角验
```

只补 unit test "通过了" → 上线挂 = 自欺。

### 🔴 2. 主干红 → 修主干 + 沉淀经验

```
WRONG:主干挂 → 临时改脚本 → 跑通 → 不记录
RIGHT:主干挂 → 改对应 wfN-demo-plan.md(加"踩坑历史" 段)→ 改脚本 → 重录 verify
       下次别人再走 = 看 demo-plan 就知道历史坑 = 不重蹈
```

### 🔴 3. demo plan 只放 `tests/trunk-recording/`

不允许散落:
- ❌ `tests/integration/` 内放 .md plan(代码 vs 文档混)
- ❌ `docs/` 放 demo(脱离 v4)
- ✅ `_wiki-methodology/_tests/trunk-recording/wfN-demo-plan.md`(单一真源)

### 🔴 4. 测试失败先 audit,再解释

```
WRONG:测试红了 → 看最后一行 stderr → 猜一个原因
RIGHT:测试红了 → 跑项目 COL3 audit/SSDO 入口 → 读 timeline/report/log/status → 再判断
```

如果项目还没有 audit 入口,这本身就是 COL3 缺口。应补一个最小 reader,至少能读最近一次 run 的 report、timeline 和 stdout/stderr。

---

## 新功能录像 SOP(用户说"录像 X"必走 8 步)

模板:`_wiki-methodology/_tests/trunk-recording/_new-feature-template.md`(每项目自己有)。

简版 8 步:
1. 复读 X 是啥(1 句话)
2. 起草 `wfN-demo-plan.md`(5-9 必演产物 + linger + verify + 反例)
3. ⭐ **跟用户讨论 plan**(不直接录)
4. 用户拍板 → 写脚本(plan → 1:1 步骤)
5. 录第一遍(必挂)
6. 分类修:后端 / 前端 / 录像 plan 漏(★ 改 plan 不是临时拼)
7. 重录 + verify + 按项目约定交付(外发渠道只在用户明确要求时用)
8. ⭐ **沉淀到 wfN-demo-plan.md 末尾 "踩坑历史" 段**

---

## 接入新 software 项目(三层骨架建立)

新建 `_wiki-methodology/_tests/` 目录后:

```bash
mkdir -p _wiki-methodology/_tests/{trunk-recording,branch-modules,leaves-unit}
```

写 4 份 README:
1. `tests/README.md`:三层定义 + 关键约定
2. `tests/trunk-recording/README.md`:wfN 列表 + 跑法 + 新功能 SOP 链接
3. `tests/trunk-recording/_new-feature-template.md`:8 步 SOP
4. `tests/branch-modules/README.md` · `tests/leaves-unit/README.md`:指向 `<lang>/tests/` 真源
5. software pipeline 项目加 `_wiki-methodology/_tests/_ssdo_protocol.md` 或等价文档:登记 audit 命令、trace 真源、失败时必读流程。

参考蓝本：优先看当前项目的 `_wiki-methodology/_tests/`；旧项目范例仅用于迁移参考。

---

## 项目级说明配套

在项目 `AGENTS.md`(或项目已有的规则文件)里加一段录像协议:
- 引用本文档
- 列项目级 wf 列表
- 用户说 "录像 X" 时 cc 自动走 8 步 SOP

---

## 反例

| 反例 | 后果 |
|---|---|
| 录像第 1 遍挂 → 改脚本不沉淀到 plan | 下次别人又踩 · 失忆螺旋 |
| 主干挂 → 只补 unit test 骗自己 | 上线用户视角真挂 · 客户骂 |
| 交付说明 / 字幕按某一个 wf 硬编码 | 其他 wf 的产物都贴错说明 |
| 相机视角、布局参数凭直觉填 | 画面与真实状态不符 · 反复重录 |
| 没 demo plan 临时拼脚本 | 漏演关键产物 · 用户验收时挑刺 |

---

## AI self-debug 阶段定位机制

**AI 不监控录像 → AI 监控阶段进度**:不需要定位到视频哪一帧,只要知道卡在 workflow 的哪个阶段,就能去查对应文档与日志。失败时 AI 自己定位 = "录到[X/N]步时挂"+ 查对应文档 + log + db → 自主修。

### 阶段进度的三个信源(AI 必读)

| 信源 | 看什么 | 答的问题 |
|---|---|---|
| **wfN-demo-plan.md 步骤段** | `[1] <步骤> / [2] <步骤> / … / [N] <步骤>`(每步写明必演产物) | "本来该跑哪步?对应必演产物是啥?" |
| **stdout 日志** | `print("[N/M] ...", flush=True)` 真实进度 | "录到哪步挂?有没 stderr?" |
| **backend log + db** | 任务状态字段 / 错误字段 · 事件表 · access log | "底层 service 这步是 done 还是 failed?根因?" |

### 失败时 AI 自主三步

```
1. 读 stdout · 定位到 "录到 [X/N] 步" 卡住
2. 对照 wfN-demo-plan.md "[X]" 段 · 看预期产物/动作
3. 查 backend log + db · 看后端是否真出此产物 · error 啥
   → 是后端 bug:修后端 + 加 leaves-unit 防回归 + 沉淀 wfN-demo-plan 踩坑历史
   → 是前端 bug:修前端 + 沉淀
   → 是 plan 漏(没演关键产物):改 plan 不是临时拼脚本
4. 重录 · verify · 按项目约定交付
```

### 录像脚本必带的可观测三件套

- `print(f"[{i}/{N}] step name", flush=True)` 每阶段开头
- API/click 失败时 `requests.post` 兜底 + 打印 status_code + body[:200]
- 关键产物前 `page.screenshot(path="step_N_*.png")` 截图

**禁**:silently 重试 / 隐藏 stderr / 一坨大 try-except 吞错。

---

## 反模式速查

### 🔴 "赌运气"反模式 — 失败就 retry 不查根因

**症状**:测试挂 → 加 `for attempt in range(3): retry` → 撞通了就发布 → 用户嫌"挂的原因没解释"。

**真因**:retry 是"症状缓解"不是"根因修复" · 会把超时、字段名错位、判空条件过严这类真问题藏起来。

**RIGHT**:任何非确定性失败,都先查具体失败那次的 sandbox / db / log · 找到逻辑上的根因 · 不允许"概率高就推 retry"。

### 🔴 字段名错位 — API 字段 vs DB 字段不一致

**症状**:测试代码读不到值 · 死等超时 · 但 db 里数据是好的。

**真因**:DB 列名/类型(如某个 `*_json` 字符串列)和 API 序列化后的字段名/类型(如对应的 dict 字段)不一致 · 测试代码用 DB 列名查 API 拿不到。

**RIGHT**:写轮询代码前先 `requests.get(...).json()` 跑一次 print keys · 用真 API 字段名。

### 🔴 浏览器 race condition — reload 触发 fetch 立即 abort

**症状**:浏览器只 1 次 GET 资源 200 但 ERR_CONTENT_LENGTH_MISMATCH · 之后不再重试。

**真因**:reload 进行中触发的 fetch 被 chromium 自己 cancel · model-viewer 等 web component 不会 retry。

**RIGHT**:reload 完成后**显式 reset** 资源 src(`removeAttribute + setAttribute + ?ts=now`)强制 fresh fetch。

### 🔴 假"主干通过" — 视频录到了但产物没演

**症状**:webm 文件存在 + 大小正常 → AI 报告 "录像 OK" → 用户截图看到弹窗错误才发现。

**真因**:AI 只验"视频文件落盘" · 没验"产物真在帧里"。

**RIGHT**:每个必演产物对应**前端可读 state**(进度 attr / class / 数据 dom)· 录完跑 `verify_video.py` 或在脚本内 assert dom state · 不靠 AI vision 看视频。

---

## 科研项目(research mode)适配

研究项目没浏览器录像,但**三层思想同样套用**:

| 层 | software | research |
|---|---|---|
| 🌳 主干 | Playwright 录用户行为 | 端到端 pipeline 真跑(数据 → 特征 → 模型 → 评估 → submit / paper figure)· 出真数字 |
| 🌿 分支 | API + DB 集成 | 多 step pipeline 切片(eg. step N 的输入依赖 step N-1 的输出 · 跨 module) |
| 🍃 枝叶 | 单函数 unit | 单公式 / 单 sklearn estimator · pure logic |

研究项目"录像"形式 = **可复现 notebook + 真数字 + plot**。fail-state 信号:

- 主干红 = Kaggle CV 没提升 / paper figure 出不来
- 分支红 = step N 输出 schema 不对(下游 step N+1 KeyError)
- 枝叶红 = 公式算错 / σ² 传递断

研究项目 demo-plan 等价 = **`_wiki-methodology/_top/_findings/<slug>.md`**(假设 + 数据 + 结果 + verdict)· 不是 wfN-demo-plan 而是 finding 卡片。

---

## 链接

- 项目级范例 → 当前项目 `_wiki-methodology/_tests/`
