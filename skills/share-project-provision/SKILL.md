---
name: dev-project-provision
description: "项目技能模组/装备。设计软件骨架、架构骨架或开启骨架/Potato模式，以及任务需要先定软件结构时，启用骨架模块；智慧大屏与三维运营看板按源码复用流程准备；按授权准备前端设计等项目能力。"
---

# Project Provision — 项目级装备推荐器

你说「这项目要装什么」或描述在做什么 → 我**查档案匹配项目类型 → 列出建议清单(从下面的目录) → 你勾选 → 我才往该项目 `.claude/` + `.agents/` 装**。

你明确说「开启前端设计模式」→ 这句话本身就是对设计 bundle 的确认：我直接安装并验证。

🔴 **核心纪律:问「装什么」才只建议；说「开启 X 模式」就安装 X 的预设 bundle。** 如果用户只是泛泛聊概念或不在项目目录里，先解释/定位项目，不静默安装。
触发于用户询问模组/装备、开启某模式，或任务持续需要前端设计等专门能力而项目尚未具备。自动识别并提出最小建议；已有模式开关或项目授权就执行。普通小改、已有装备足够、单纯进入目录时不安装或重复推荐。
🔴 **项目级 MCP 不再作为默认装备。** 能用 CLI / API / 全局 skill 做的,不要建议写项目 `.mcp.json`;只有用户明确授权「装 MCP / 用 MCP」才把 MCP 当例外候选；同一任务已有授权继续有效。

## 模组是什么、为何列表里看不到

模组是一组按项目启用的技能、参考和工具配方。全局只展示本入口；离线模板使用 `SKILL.md.template`，获授权安装到具体项目后才成为项目技能。模块不按全局手册读取排名判断价值。

当前模块和历史状态见 [模块目录](references/modules/index.md)。点名 Superpowers 时按该目录的 Superpowers 行处理：本技能包在 `third_party/superpowers/` 随附固定版本，优先用官方插件安装。

## 软件骨架入口

用户要求设计软件骨架、架构骨架、开启骨架/Potato模式，或任务需要确定软件模块边界、数据模型和接口结构时，按[软件骨架模块](references/modules/software-skeleton.md)启用并使用。此为已授权的可选架构模块；普通“后端/开发模式”仍沿用现有能力。论文提纲、方法绘图和局部修复不触发。

## 智慧大屏与三维运营看板

用户要制作智慧大屏、智慧园区/社区运营看板，或基于现有 Base 做同类网页时，读[大屏源码复用流程](references/smart-dashboard.md)（原配套的大屏总入口属运维技能，本包未包含）。先核对项目与 Memory 的已选骨架，沿用可用版本，再适配数据、视觉和交互；这是开发配方，不执行下方装备安装流程、不自动安装技能或换栈。已有大屏的局部修复直接进入源码。通用 BI 数据分析另用数据分析工具；数字孪生的机理建模先交接领域对象、输入/输出、参数与单位、时间步、校准数据和验收指标，再由对应领域流程实现。

## 可选模块

用户要吸收技能、仓库或外部能力时，先确定落位（全局技能、项目技能或按需模块；专门的技能创建流程（可选，本包未包含））。本入口负责执行已选的项目装备；模块配方存在按需 reference 中，不进入全局技能清单。项目固定安装版本，更新不自动传播。

- 用户明确选择 Impeccable → 读 [项目设计模块配方](references/modules/impeccable.md)，用 `scripts/install_impeccable.py` 预览、安装和核验。安装器拒绝覆盖同职责技能；替换范围已批准时先归档旧入口，再安装。
- 只说开启前端设计模式 → 沿用下方现有预设；Impeccable 尚是可选候选，不因进入软件项目自动安装。
- 模块升级 / 卸载 → 按配方核对安装回执、本地改动、宿主发现及退出范围；已有授权不逐阶段重复确认。

## 品牌风格参考

用户指定品牌风格、要选设计参考，或明确使用 awesome-design-md → 读 [设计参考库](references/design-reference-library.md)。它提供按需读取的设计材料：核对页面类型与来源后，把选中的规则适配进项目设计真源；不安装额外设计总控。仅评估时只给建议，已授权做页面时直接沿用该授权执行。

## 工作流(每次)

1. **判类型**:看项目结构判 dev / frontend / 深度学习 / …(用户一句话可覆盖)。
2. **查档案 + 目录**:按下方「档案」拿该类型的建议 bundle,在 [安装目录](references/install-catalog.md) 查本轮所选项。
3. **决定动作**:
   - 用户问「装什么 / 推荐装备」→ 给清单,每项标 `type`、为什么、装到哪,等用户勾选。
   - 用户说「开启前端设计模式」→ 直接按下方“模式开关”安装设计 bundle。
   - 用户说「开启后端/开发模式」→ 不默认安装项目级方法论；已授权的软件骨架模块按上方入口执行，其余按任务需要检查现有代码、测试和工具。
4. **按 type 装**(用户勾选或模式开关确认的):
   - `skill` → **我 copy** 模板到 `<项目>/.claude/skills/<name>/` 和 `<项目>/.agents/skills/<name>/`(模板已在 `templates/skills/` 离线备好；若模板入口叫 `SKILL.md.template`，安装时改名为 `SKILL.md`)。
   - `cli` → **我检查/安装命令行工具**到用户 prefix 或复用全局 skill;项目内只放测试、配置和证据。
   - `plugin` → 默认不使用。用户询问是否安装时，说明 CLI/API/skill 替代方案供选择；已明确授权安装指定 Claude plugin 时，按该范围执行，不重复确认。
5. **验证 + 汇报**:skill 核验文件并在目标宿主实际检查发现（必要时 reload/restart）；只落盘不算可调用;cli 跑 `--version`/smoke test;plugin 例外才看 `claude plugin list`。报实际结果。

## 档案:项目类型 → 建议 bundle

识别 React/Next.js 或处理复杂前端组件时，读 [React 组件技能选用](references/react-composition-routing.md)：从项目依赖和源码确认后，按实际需要评估项目专属组件规范；该包已从通用技能集合退役；不要求用户先知道是否用了 React，不默认迁移技术栈。

| 项目类型 | 建议装(按需勾选) |
|---|---|
| **开发类(software)** | 不默认安装通用方法论 skill；软件骨架按明确设计任务启用，其余按需准备框架、CLI 或测试工具 |
| **+ 前端开发** | **frontend-design** + **design-taste-frontend(taste)** |
| 深度学习 / 模型 / 数据 | HuggingFace / Kaggle CLI 或 API 工作流（按需） |
| 需要控制浏览器 / E2E | Playwright CLI（本包 `playwright-cli` 技能；命令需另装 `npm i -g @playwright/cli`） |
| 逆向工程 / 安全研究（授权内） | **reverse-skill-pack**(按需装项目级;默认轻量,综合需求才装完整路由包) |

> 一类需求 = 档案/目录里一行。要支持新类型,照「扩展」加行即可。

## 模式开关:用户说法 → 直接安装的项目级 bundle

| 用户说 | 语义 | 直接安装/准备 |
|---|---|---|
| `开启后端模式` / `开启开发模式` / `进入开发模式` | 开始开发工作 | 不安装项目级方法论；使用模型内置能力 + 项目现有规则/测试 |
| `开启前端设计模式` / `开启设计模式` / `做前端设计模式` | 项目进入前端视觉/交互设计模式 | 项目级 `frontend-design` + `design-taste-frontend` |
| `开启扫描模式` / `语义扫描` / `重建 codemap` | 代码导航与按需索引 | 有代码语义扫描技能（`dev-semantic-scan`（可选，本包未包含））时转它，否则优先复用现有索引或直接查源码；按其许可与必要性规则维护索引，重建 codemap 时回写项目导航 |
| `开启逆向模式` / `开启安全研究模式` / `做逆向` | 项目进入授权逆向/安全分析 | 按「目录」`reverse-skill-pack` 行装到项目级（默认先问轻量还是完整）；仅用于用户自有或已授权目标 |

具体后端库、ORM、队列、观测工具只在项目确有需要时另行建议或安装。

## 目录与安装

安装、升级、卸载或查询特定装备时，读 [装备与安装目录](references/install-catalog.md)，只执行匹配项。该目录保留前端模板、逆向包、CLI、插件与 MCP 例外的完整边界；普通装备建议不先加载全部安装命令。模板和脚本路径不变。

## 扩展:加新类型 / 新项(只加行,不改流程)

匹配不到 → **先 `WebSearch` 核实真实包名/仓库**(别编) → 在「目录」加一行,需要时在「档案」加该类型的 bundle 行,大件 skill 把模板预先 `curl`/`npx skills add` 落到 `templates/skills/`。优先找 CLI / SDK / 官方 API。

## 边界

- 本 skill = **按项目类型建议 + 装现成第三方 skill/CLI 到项目级或复用全局能力**。
- 新项目的进度骨架不在本 skill 生成：用 share-top 的 `~/.claude/skills/share-top/scripts/init-research.sh <项目>`，默认只建必需部分（`AGENTS.md` + `_task_plan.md` + `_logs/`），codemap/registry/wiki/tests 等可选模块用 `--with` 按需启用；不生成 roadmap、phases、six_dim_contract、external_reviews、capabilities、naming 骨架。
- 把自己代码封装成 CLI → `share-agent-cli`；API 服务封装属 `share-dev-toolkit`（可选，本包未包含）。
- 新建/优化/吸收 skill 本体、跑 eval → 专门的技能创建流程（可选，本包未包含）。
- 改 settings.json / enabledPlugins / hooks 细节 → 先读当前本地 schema与对应官方文档；Claude 侧可用内置 `update-config` skill 改 settings.json；Codex 侧改 `~/.codex/config.toml`。
- 配置只安装在当前机器的当前项目；不向其他机器传播。
