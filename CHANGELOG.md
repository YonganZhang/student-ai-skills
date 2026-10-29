# 更新记录

## v1.3.1 (2026-10-29)

- 所有技能的 `UPSTREAM.json` 来源记录统一为 `skill-upstream/v1` 格式，`share-skill-creator/scripts/upstream_watch.py --lint --root skills` 全包 0 错误；快照清单类记录声明自己的格式并由所属技能测试校验。
- `frontend-design`、`design-taste-frontend`：说明设计参考库随 `share-project-provision` 安装，没装时跳过该步并沿用项目视觉。

## v1.3.0（2026-10-29）

- 新增入门教程 [docs/TUTORIAL.md](docs/TUTORIAL.md)：技能是什么、渐进式披露、技能与 MCP 的区别、安装、使用示例、自己创建技能；README 开头提示新同学先读。
- 新增 1 个技能（共 17 个）：agent-skill-creator（目录 `share-skill-creator`），技能创建器：创建与修改技能、写 description、结构分层、正例与近误触负例验证、测试用例评估与 description 迭代、吸收外部技能；附 `quick_validate`、`check_skill_filenames`、`audit_skill_routing`、`audit_skill_refs`、`scan_orphans`、`upstream_watch` 等脚本与测试。
- 公开前精选：只保留创建、评估、吸收相关内容；不随附维护者自用的技能清单与低频库、跨宿主同步、完整配置回放、案例泄漏审计、全局 harness 审计、路由契约测试与历史记录。个人写法约定改写为通用的 `references/conventions.md`；技能放置位置写成个人 `~/.claude/skills/`、`~/.agents/skills/` 与项目 `.claude/skills/`、`.agents/skills/`；脚本默认目录改为 `~/.claude/skills`（可用 `SKILLS_DIR` 覆盖），`check_skill_filenames.sh --fix` 改为就地改名。
- dev-project-provision、dev-grill-to-spec、project-top、research-dl-pipeline-base 里原先把技能创建器标成“本包未包含”的引用改为指向包内 `share-skill-creator`。

## v1.2.0（2026-10-29）

- 新增 2 个技能（共 16 个）：
  - dev-pr-self-check（**必装**）：提 PR 前作者侧自检（测试与构建、新上下文审 diff、风险分级、PR 说明模板、`scope_check.py`）。`install.sh` 的 `--only` 不含它时也会安装并提示“dev-pr-self-check 为必装，已一并安装”；`--list` 标“必装”。
  - research-mlgain-integrate-component（目录 `mlgain-integrate-component`）：组件接入参考库，research-dl-pipeline-base 的配套。源文件 `REFERENCE.md` 在包内改名为 `SKILL.md`。
- research-dl-pipeline-base 里指向 mlgain 的链接改为指向包内同级目录；探针夹具恢复使用包内 `probe_hooks.py`。
- 公开前处理：参考库一处本机环境路径泛化、油藏知识技能标“本包未包含”；dev-pr-self-check 测试里一处私有项目名改为通用名。
## v1.1.0（2026-10-29）

- 新增 2 个技能（共 14 个）：
  - web-playwright（目录 `playwright-cli`）：Playwright CLI 浏览器操作、E2E 验收与演示录像。依赖 npm 包 `@playwright/cli`，README 给出安装方法；`install.sh` 默认只检查并提示，新增 `--with-playwright` 才执行 `npm install -g @playwright/cli`。
  - research-dl-pipeline-base（目录 `share-autoresearch-engine`）：深度学习训练与研究闭环，含 Lightning 模板、实验门禁脚本和 ARIS 参考。
- 公开前处理：两技能去掉本机路径、代理与 systemd 等本机设定（`open_session.sh` 改为有代理才加代理配置、有 systemd 才进独立 scope）、私有看板与凭证工具、私有项目名与实验进展；录像后期、视频制作、外援审查等未收录引用标“本包未包含”（组件接入参考库自 v1.2.0 起随包提供）；不随附约 32 MB 的 model-zoo 上游代码（按 SOURCES.md 自行克隆）。
- v1.0.0 中把这两个技能标成“本包未包含”的引用（dev-find-wheels、dev-project-provision、project-top）改为指向包内技能。
- 修正：project-top 一处测试样例里的私有框架名；dev-agent-cli 一处指向未发布内部记录的说明。

## v1.0.0（2026-10-29）

首个公开版本。

- 收录 12 个技能：project-top（含 `plan` 与 `sixone-cli.py`）、content-pptx-gen、content-real-ppt、content-technical-roadmap、content-black-white-roadmap、dev-grill-to-spec、dev-code-review、dev-find-wheels、dev-agent-cli、frontend-design、design-taste-frontend、dev-project-provision（含模板与模块配方）。
- 随附 Superpowers 7.0.0（obra/superpowers，MIT）原样副本。
- 新增 `install.sh`：Claude Code / Codex 双端安装，复制或软链，按名选装，安装 `plan` 命令，Superpowers 官方插件优先、失败退回随附副本，支持 `--dry-run`、`--force`、`--help`。
- 公开前处理：本机路径改为 `~/.claude/skills/<技能>` 等可移植写法；删去私有项目、人员、内部看板与私有规则文件的引用；未收录技能统一标注“可选，本包未包含”。技能方法本身未改写。
