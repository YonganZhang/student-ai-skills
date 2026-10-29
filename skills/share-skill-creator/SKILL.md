---
name: agent-skill-creator
description: "创建、修改、评估、吸收技能，把重复流程沉淀成 SOP：写 description、分层 references/scripts、正例与近误触负例验证、迭代评估。"
---

# Skill Creator

把 skill 当作按需加载的能力接口：入口负责路由，稳定知识进 references，重复且确定的动作进 scripts。用户给出的案例是证据和测试，不直接变成枚举式规则。

## 先选择工作流

| 任务 | 必读内容 |
|---|---|
| 新建或大改 skill | `references/conventions.md`（结构、description、拆分检查点、脚本自检），再按需读 `references/authoring-evaluation-guide.md` |
| 新建、改名或决定放在个人还是项目 | 下方“技能放在哪” |
| 用户要求记成做事规范、“以后都这样”、变成 SOP（只是记住事实/偏好时写进项目说明或宿主记忆即可） | `references/memory-to-sop.md` |
| 写或改 skill/rule/AGENTS.md 正文的措辞（指针、完成标准、删无效句） | `references/absorbed/mattpocock-writing-for-agents.md` |
| 拆分巨型 skill / router | `references/skill-structure-hierarchy.md` |
| 优化 description 触发 | `references/authoring-evaluation-guide.md` 的 Description Optimization |
| 吸收技能、仓库或外部能力的落位 | 先读 `references/placement-and-modules.md`；可选模块由 `share-project-provision` 安装 |
| 吸收外部 skill | `references/absorber/`；上游来源登记与跟踪见 `references/upstream-tracking.md` |
| 跑测试用例、和基线对比、打分与人工审阅 | `references/authoring-evaluation-guide.md` 的 Running and evaluating test cases；配套 `agents/`、`eval-viewer/`、`references/schemas.md` |
| 会话复盘 / retro：这次哪里能让下次更顺 | `references/absorbed/mattpocock-retro.md` |

## 技能放在哪

| 范围 | Claude Code | Codex |
|---|---|---|
| 个人、跨项目通用 | `~/.claude/skills/<技能目录>/` | `~/.agents/skills/<技能目录>/` |
| 属于某个项目、和队友共享（随代码进 Git） | `<项目>/.claude/skills/<技能目录>/` | `<项目>/.agents/skills/<技能目录>/`（可软链到同一份） |

入口文件必须是大写 `SKILL.md`；新建或改名后开新会话才会被发现。项目技能和代码一样走 PR。技能会被分享，不写本机路径、账号和凭证。

## 默认闭环

1. 从对话和现有文件提取目标、触发条件、边界和验收，不重复盘问已有答案。
2. 吸收外部能力或新增 skill 时先按 [落位选择](references/placement-and-modules.md) 判断个人全局、项目或可选模块；先搜已装技能和现有真源；更新已有规范，避免同义规则并存。
3. 把案例提升为“条件—不变量—边界—验证”，再决定放 rule、skill、reference、script 或项目级文件。
4. description 只在触发边界变化时修改，以约 140 字符为编辑目标、触发条件前置（必要语义优先，非平台技术限制，细则见 `references/conventions.md`）；主体写当前手册，历史放 changelog。
5. 用真实正例和相邻近误触负例验证；客观任务再进入详细 eval 循环。
6. 改完检查文件名、路由和引用；脚本新增、移动或调用变化时再检查孤儿候选。同时给 Claude Code 和 Codex 用时按各宿主语义适配，不复制本机路径、账号与凭证。

## 结构边界

- 篇幅：入口 `SKILL.md` 每次触发都整篇进上下文，以 150 行左右为目标（router 约 80 行）；超出不算错，但要能说明每次触发都需要这些内容，只在部分场景用到的下沉到 references。超过 500 行优先评估拆分或补目录；完整流程和约束优先于行数，这不是平台技术上限。多于两个独立子能力时优先采用 router，并验证父入口召回与子流程可达性。
- nested `SKILL.md` 只给真正需要独立触发的能力；其余用 `REFERENCE.md` 或主题文档，避免子流程被当成独立技能曝光。
- rule 保持常驻最小；命令、长流程和案例下沉 references。
- 不把日期、事故叙事、版本升级段和用户原话堆进主手册。
- 不创建没有入口的 script；重复逻辑才脚本化。

## 检查入口

文件名、路由与引用改后核验；孤儿扫描按上面的脚本变更范围运行。报告里的候选需人工核实，不直接当成错误或要求用户裁定。

在本技能目录（Claude Code `~/.claude/skills/share-skill-creator`，Codex `~/.agents/skills/share-skill-creator`）下运行：

```bash
python3 scripts/quick_validate.py <技能目录>             # frontmatter 与必填字段（需要 PyYAML）
SKILLS_DIR=~/.claude/skills bash scripts/check_skill_filenames.sh   # 入口必须是大写 SKILL.md；Codex 或项目技能换成对应 skills 目录
python3 scripts/audit_skill_routing.py ~/.claude/skills    # Codex: ~/.agents/skills；项目: <项目>/.claude/skills
python3 scripts/audit_skill_refs.py ~/.claude              # 参数是含 skills/ 的目录；Codex: ~/.agents；项目: <项目>/.claude
python3 scripts/scan_orphans.py <技能目录>               # scripts/ 里没人引用的脚本
python3 scripts/upstream_watch.py --lint --root <技能目录>  # 技能带 UPSTREAM.json 时检查格式
```

普通正文修改只检查本轮内容和受影响引用。新增、改名或迁移发现入口时，核对受影响宿主的目录；跨平台工具或 hooks 改动再验证对应能力。不因每次修改都启动多个模型做全面评测。

## 代表性路由验收

把真实说法（应触发）和相邻但不该触发的近误触说法写成触发评测集：`[{"query": "...", "should_trigger": true}, ...]`，格式示例见本技能的 `evals/memory-to-sop-trigger.json`。人工或模型回放时逐条核对选择与避免项，不把正则/静态断言当成模型选取准确率。在 Claude Code 里可在本技能目录下运行 `python -m scripts.run_eval --eval-set <评测集> --skill-path <技能目录>` 实测，`python -m scripts.run_loop` 自动迭代 description（需要 `claude` 命令，用法与测量边界见 `references/authoring-evaluation-guide.md` 的 Description Optimization）；Codex 等没有该命令的宿主在新会话里逐条人工回放。CLI 另跑实际只读命令，help 成功不能替代业务验证。
