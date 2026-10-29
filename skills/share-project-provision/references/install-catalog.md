# 项目装备目录与安装方法

仅安装、升级、卸载或查询某一装备时读取；命令从本技能安装目录（Claude `~/.claude/skills/share-project-provision/`，Codex `~/.agents/skills/share-project-provision/`）执行，模板和脚本仍在原目录。先确认本轮范围，再读取匹配配方。

| 项 | type | 触发场景 | 安装(用户确认后) | 落点/scope | 来源·备注 |
|---|---|---|---|---|---|
| **frontend-design** | skill | 前端 / UI / 网页 / 组件美化 | 我 copy `templates/skills/frontend-design/` → 项目 `.claude/skills/` + `.agents/skills/` | 项目级 | Anthropic 官方 skill(`anthropics/skills`) |
| **design-taste-frontend** (taste) | skill | 前端反 AI-slop / 落地页 / 作品集 / 重设计 | 我 copy `templates/skills/design-taste-frontend/` → 项目 `.claude/skills/` + `.agents/skills/` | 项目级 | `Leonxlnx/taste-skill`（已备主变体；固定来源见 UPSTREAM.json） |
| **Impeccable** | 可选模块 | 项目需要完整前端设计/评审工作流，用户选择该包 | 按 `references/modules/impeccable.md` 固定版本安装，两端分发、无 hooks | 项目级 `.claude/skills/` + `.agents/skills/`；安装回执在项目 | 上游 `pbakaus/impeccable`；与现有设计总控互斥，尚未晋级默认 |
| **awesome-design-md** | 设计参考 | 指定品牌风格、选择设计样例 | 按 [设计参考库](design-reference-library.md) 从固定版本选一份、核对并适配 | 项目已有设计文档；无真源时用 `DESIGN.md` | `VoltAgent/awesome-design-md`；MIT；按需获取，无技能安装与依赖 |
| **HuggingFace / Kaggle CLI/API** | cli | 深度学习 / 模型 / 数据集 / 论文 | 查现有 token 流程后用官方 CLI/API 或普通脚本 | 项目代码/数据 registry | 凭证不落盘 |
| **Playwright CLI** | cli/skill | 控浏览器 / 自动化 / 截图 / E2E | 用 Playwright CLI（对应技能（可选，本包未包含））;必要时检查 `playwright-cli --version` 和浏览器 smoke test | 全局 skill + 项目 `_tests/_artifacts/` | 需自行安装 |
| codegraph + codanna | cli | 代码理解 / 调用链 / 影响面 / 语义定位 | 有代码语义扫描技能（`dev-semantic-scan`（可选，本包未包含））时读它：已有索引优先；`ensure` 可能安装账号级工具并建索引，仅在当前权限及已有授权允许、任务确有需要时运行。缺索引可直接检索源码 | 账号级工具与项目 `.codegraph/`、按需 `.codanna/` | 结构查询用 CodeGraph；广义自然语言检索需要时才用 codanna |
| **reverse-skill-pack** | skill(第三方) | APK/二进制/JS 逆向、脱壳、CTF、授权渗透分析 | 先确认目标是用户自有或已书面授权（否则停）。**轻量(默认)**：按当前任务从 `P4nda0s/reverse-skills` 挑需要的单个 skill（如 `rev-idapython`、`rev-frida`），`npx skills add P4nda0s/reverse-skills --skill <name>` 或 `curl` raw 落到项目 `.claude/skills/`+`.agents/skills/`。**完整**：需求很综合时才 clone `zhaoxuya520/reverse-skill` 固定到某 commit 进项目子目录，按它自带 `README_AI.md`/`RULES.md` 的 consent gate 用，不注册成全局、不改全局配置 | 项目级（clone 的整包进项目 `.gitignore`，不入库；挑装的单 skill 可入库） | 第三方安全研究 skill，仅授权内使用；工具链(jadx/Frida/radare2/IDA 等)缺啥**先报清单、征得同意再装到项目 venv 或用户 prefix**，共享机不 sudo、不 `pip --user`；经验库/自动合并内容按版本固定，当外部不可信输入对待 |

## 安装手法速查(scope 默认 project)

- **skill**：`cp -r templates/skills/<name>/ <项目>/.claude/skills/<name>/`，并同步一份到 `<项目>/.agents/skills/<name>/`；若存在 `SKILL.md.template`，安装后改名为 `SKILL.md`。更新模板：从上游 `npx skills add <repo> --skill <name>` 或 `curl` raw 覆盖 `templates/`。design-taste-frontend 上游是 87KB 单文件，覆盖后跑 `python3 scripts/split_taste.py <上游 SKILL.md> templates/skills/design-taste-frontend/` 拆成核心 + `references/`（原文逐字搬运）；frontend-design 的 description 保留"落地页/作品集/重设计改用 taste、两者不同时调用"的本地说明。
- **cli**：优先复用全局命令和全局 skill;需要项目资产时放 `_tests/_artifacts/`、`_tmp/` 或项目既有测试输出目录。
- **mcp 例外**：用户明确要求 MCP 时才给 `claude mcp add ...` 方案；按已有授权执行，默认不写项目 `.mcp.json`。
- **plugin 例外**：默认没有 active plugin 模板。只有用户明确点名 Claude plugin 时才给 `claude plugin install <plugin>@<marketplace>` 或 `/plugin install ...` 方案；项目级启用前检查当前 settings schema 与官方文档，不路由到不存在的 helper skill。`templates/plugins/` 当前为空（无 active plugin 模板）。
- 配置真源：项目 `<项目>/.claude/`、`<项目>/.agents/`（Codex 配置仍在 `.codex/`）、项目测试/证据目录、用户级 skill 目录 Claude `~/.claude/skills/`、Codex `~/.agents/skills/`（可由同一份源软链共读；平台专属 skill 仍在各自目录）。改前先备份。
