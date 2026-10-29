---
name: share-skill-absorber
tags: [share, meta, skill-management, merge, absorb]
description: "从外部 skill 仓库筛选并合并可复用能力。"
---

# Skill Absorber

从外部 skill 仓库中智能筛选、对比、合并内容到现有 skill 体系。

## 开始前

先读 [落位选择](../placement-and-modules.md)，输出全局能力、项目专属或可选模块的推荐；仓库内容不默认转成全局 skill。可选模块把安装配方交给 `share-project-provision`，再按下方流程审查实际吸收内容。

## 工作流程（5 阶段，沿用已获授权）

| 阶段 | 名称 | 说明 | 详见 |
|------|------|------|------|
| 1 | 盘点 | 扫描外部仓库，生成分类清单 | `references/phase-1-inventory.md` |
| 2 | 分类 | 逐条标记：合并/新建/拆分/拒绝 | `references/phase-2-classify.md` |
| 3 | 合并计划 | 生成 pre-merge diff，Codex 审查 | `references/phase-3-merge-plan.md` |
| 4 | 执行 | 逐条合并，post-merge diff + Codex 审查 | `references/phase-4-apply.md` |
| 5 | 去重审计 | 全局扫描残留重叠 | `references/phase-5-audit.md` |

## 核心规则

1. **用户确认门控** — 执行前展示具体范围与内容；已有明确授权覆盖的阶段直接推进，实质范围变化或未决冲突才请求确认，禁止超范围静默合并
2. **索引-引用分离** — 吸收内容只进 `references/`，目标 SKILL.md 只加一行索引
3. **场景匹配优先** — 按使用场景/意图匹配，不按文件名匹配
4. **现有 skill 为主** — 外部内容是补充，永远不覆盖现有结构和风格
5. **冲突显式处理** — 同场景不同建议放 `references/conflicts/`，用户拍板后才合入
6. **溯源标注** — 每条吸收内容标注来源仓库、文件路径、吸收时间；并在目标 skill 根目录的 `UPSTREAM.json` 登记 repo、上游路径、吸收 commit、日期、vendored/semantic 与本地路径（格式见 `../upstream-tracking.md`）
7. **Codex 审查** — Phase 3/4 的 diff 必须提交 Codex 检查后再执行（没有 Codex 时交给不带当前对话的新上下文子智能体，或用本包 `share-code-review`）
8. **批量上限** — 单次最多处理 10 个 skill，超过排队下一轮
9. **锁定规范不动** — 目标技能中标为 locked 的文件（如某写作技能里标为 locked 的固定写作步骤文件）不得被吸收内容改动；看起来需要改时，先停下与作者讨论并取得明确批准

## 启动

读 `references/phase-1-inventory.md` 开始 Phase 1。

## 冲突处理规则

详见 `references/conflict-resolution.md`
