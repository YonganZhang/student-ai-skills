# Absorption Checklist — 吸收新 skill 不踩坑

> 2026-05-23 立 · paperspine 吸收踩坑后沉淀
> 适用: **任何外部 skill / subagent 吸收到本地**
> 调用时机: 完成"文件搬运 + UPSTREAM.json（格式见 `../../upstream-tracking.md`）"后, **强制**走本 checklist 再算吸收完成

---

## 真根因 (2026-05-23 paperspine 案例)

之前吸收 paperspine 时:
1. ✅ snapshot vendor 6 ref + 1 script + sources.lock + SKILL.md 子技能 — 做了
2. ❌ **但没接入 baselines 主流程任何一个 step / round** — 用户原话: "你的主流程里面 Baseline 里面又没有去用它"
3. ❌ **没主动问用户接入点** — 用户原话: "你不问我这个东西是放在骨架里面还是精修里面"
4. ❌ **结果**: "到时候它放了不就跟没放一样吗? 就是有, 但是没有用"

= 典型 **死代码 / phantom registration** 问题 (注册了但没人调).

---

## 用户铁律 (吸收 skill / 创建 subagent 都遵守)

> "吸收新的技能和子智能体的创建, 都需要明确规定, 在这个子智能体它在什么时候触发. 如果你自己不知道什么时候触发, 你就应该来问我."
>
> "如果它的主技能是一个大目标 (例如写论文是一个大目标), 这个子技能只是一个工具, 那么就应该来主动问用户, 怎么把这个工具变成大目标里面, 或者说大流程里面的一个零件, 规定好什么时候去用, 怎么用."
>
> "如果这个问题很简单, 你也可以自己去规定好、设置好."

提炼成 4 条:

1. **每个吸收都必须明确触发时机** — 不留模糊
2. **不确定触发时机 → 主动问用户**
3. **主技能是大目标 + 新技能是工具 → 必须问"怎么变成大流程零件"** (不许只挂 sub-skill 文件不接流程)
4. **简单问题 AI 自己规定** (不浪费用户时间)

---

## 6 项强制 Checklist

吸收新 skill 完成 "文件搬运 + UPSTREAM.json + SKILL.md" 后, **必须**走以下 6 项 audit, 跟用户对齐才算吸收完成.

### 1. 概念重叠扫描 (AI 自己做, 不问用户)

grep 现有主流程 / baseline / pipeline 产物名 vs 新 skill 概念名, 列出重叠.

工具:
```bash
# 假设要吸收 X 进 <目标技能> 主技能（项目技能换成 .claude/skills/<目标技能>/）
grep -rn -E '<新概念关键词>' ~/.claude/skills/<目标技能>/
git grep -E '<新概念关键词1>|<新概念关键词2>'
```

输出: 列出 N 处重叠点, 标 "需要决定关系" (合并 / 替换 / 并存 / 嫁接).

**例子 (paperspine 案例)**: `main_argument_chain` (现有 6 段) ↔ `confirmed_motivation` (新一句话) — 重叠, 需决定关系.

### 2. 接入点 mapping (AI 起草 + 必须问用户拍板)

打开主技能 (大目标) 的主入口 SKILL.md / pipeline 文件, **逐个列出新 skill 的每个工具应该镶嵌在哪个 Step / Round / Phase**.

不是"挂到 sub-skills/ 就完事". 必须找具体接入点.

输出: 表格

| 新工具 / 新概念 | 推荐接入点 (主技能哪个 Step) | 接入方式 | 备注 |
|---|---|---|---|

⚠️ **强制问用户拍板**: 即使 AI 有推荐, 也要列给用户看 + 用户确认.

**例外** (条件 4 "简单问题 AI 自己规定"): 如果接入点显然 (例: 新工具是"语法检查器" 显然进 polish 阶段) → AI 自己规定但**显式告诉用户**, 给用户 1 次反对机会.

### 3. 触发词冲突扫描 (AI 自己做, 不问用户)

grep 现有 skill description 看新 skill 触发词跟谁冲突.

```bash
grep -rn -E '<新触发词>' ~/.claude/skills/*/SKILL.md ~/.agents/skills/*/SKILL.md
```

输出: 列冲突的现有 skill + 推荐怎么改 (改新触发词更精确 / 改现有 skill 加排除规则 / 路由表加优先级).

### 4. 替换 / 叠加 / 分流决策 (必须问用户拍板)

对每个有重叠的工具, 问用户:
- **替换**: 新工具替掉老工具 (老工具归档)
- **叠加**: 新老都跑 (新工具先, 老工具补; 或反过来)
- **分流**: 触发条件分 (默认走老, 用户喊 X 才走新)

输出: 决策表

| 工具 | 老的 | 新的 | 决策 | 触发条件 |
|---|---|---|---|---|

### 5. 强制 vs 可选门控 (必须问用户拍板)

新工具是 "schema 卡死必须用" 还是 "用户喊才触发"?

- **强制**: 进入下游必须先用 (例: paperspine confirmed_motivation 前置门 — 没拍板不准进 skeleton)
- **可选**: 用户喊"严格 / 深度" 才触发 (例: paperspine rewrite-matrix — 普通 polish 不用, 深度改才用)
- **默认走**: AI 自动跑 + 输出报告, 不阻塞用户

### 6. 必问用户清单 (列给用户秒回)

把 1-5 项中**所有需要用户拍板的决策**整理成一个 clean 清单, 用人话问 (不用编号 A1/B1 让人迷糊).

**问题格式**:
- 一件事一段
- 每段先讲背景 (现状 + 新工具加了什么)
- 再给 trade-off 选项 (甲/乙/丙路线, 用真实场景叙事不用编号)
- 最后明确"等用户拍板"

---

## 反例 (paperspine 吸收时踩的坑)

🔴 反例 1: 文件搬完就汇报"完成", 没走接入点 mapping
🔴 反例 2: 用 A1/B1/C1 编号问用户 6 个决策点 — 用户原话: "你说的非常混乱"
🔴 反例 3: AI 没主动列接入点, 等用户提才说 — 用户原话: "你不问我这个东西是放在骨架里面还是精修里面"
🔴 反例 4: "挂到 sub-skills/ 当独立子技能"以为完事, 没接 baseline 主流程

---

## 正例 (paperspine 修复后)

✅ 走完 6 项 checklist:
1. 重叠扫: `main_argument_chain` ↔ `confirmed_motivation` (合并嫁接, 不引入新文件)
2. 接入点 mapping: 列了 baseline 1 Step 1.5 / baseline 2 Step 0.3 / baseline 3 Round 0-alt + 3.5 + 6
3. 触发词扫: 加"反 shallow / 深度改稿 / 闭卷重写 / motivation thread / 七锚审计"
4. 替换/叠加/分流: 第 3 件 Adversarial vs rewrite-matrix 分流决策
5. 强制 vs 可选: primary_motivation 强制门, rewrite-matrix 用户喊才触发
6. 必问清单: 5 件事场景叙事问, 不用编号

---

## subagent 创建场景的延伸应用

吸收 skill 经常顺手会**创建新 subagent** (例: paperspine closed-book rewrite 需要派 general-purpose subagent 做物理隔离).

subagent 同样走以下 audit:

1. **触发时机明确?** — 写到主技能 SKILL.md 的哪个 Step / Round
2. **subagent 跟主智能体的边界**? — input/output/禁止访问的文件
3. **守护机制?** — subagent 误操作 (例 closed-book 误读原稿) 怎么 detect + 怎么 recovery (重新派 / 加更死硬黑名单 / 降级到主智能体)
4. **降级路径?** — subagent 不可用时怎么办

---

## SKILL.md 接入点提示 (主入口 share-skill-creator)

吸收任何外部 skill 时, AI 主动告诉用户:
> "我把文件搬好了, 但按 absorption-checklist.md 还要跟你对齐 6 项决策才算吸收完成. 我列给你看..."

不要默认 "搬完文件 = 吸收完成". 这是用户铁律.
