# 项目技能模组目录

按项目任务匹配最小组合；模块配方不自动注册为全局技能。判断需求与安装是两步：已有明确模式开关或项目安装授权就执行，否则先汇报具体组合与目标项目。项目装备入口负责执行和核验，不为所有项目批量安装。

| 模组/材料 | 何时匹配 | 当前状态与入口 |
|---|---|---|
| 软件骨架（pstack architect 本地适配） | 设计软件骨架、架构骨架、开启骨架/Potato模式，或任务需要先定模块和数据/接口结构 | [固定来源配方](software-skeleton.md)；已有使用授权，具体项目按需启用；不安装完整 pstack |
| 前端设计预设：frontend-design + design-taste-frontend | 新前端设计、组件视觉、落地页、作品集、整体改版；按页面类型选一个设计总控 | 离线模板在 `../../templates/skills/`，`SKILL.md.template` 安装时改为 `SKILL.md`；“开启前端设计模式”沿用现有授权语义 |
| Impeccable | 项目需要完整前端设计与评审流程，用户选择此包 | [固定版本配方](impeccable.md)；与现有设计总控互斥，不自动覆盖 |
| awesome-design-md | 选品牌/设计风格参考 | [材料库](../design-reference-library.md)，按需取材料，不另装技能总控 |
| 授权逆向研究 | 目标和用途已获授权，任务需要专门逆向工具 | 按[装备入口](../../SKILL.md)中的 reverse-skill-pack 配方选最小集合；不是预装包 |
| 深度学习数据工具、浏览器工具 | 任务确实需要 HuggingFace/Kaggle 或浏览器操作 | 优先已有 CLI/API 和全局研究/Playwright 技能，不复制一整组方法论 |
| Superpowers | 用户点名或需要其 TDD/调试/计划工作流 | 本技能包随附官方 7.0.0（`third_party/superpowers/`，MIT，obra/superpowers）。优先官方安装：Claude Code `claude plugin install superpowers@claude-plugins-official`；Codex `codex plugin add superpowers@openai-curated-remote`（或 `/plugins` 搜索）；离线时用技能包 `install.sh --only superpowers` 复制随附 skills。账号级安装，不按项目复制 |

项目安装回执记录实际来源、固定版本和文件指纹。全局模板更新不自动升级项目；文件存在与宿主发现分别核验。用户只问“有哪些模组”时列上述状态即可。
