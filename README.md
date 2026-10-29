# 学生 AI 技能包（Claude Code / Codex）

一组可直接安装到 Claude Code 和 Codex 的技能（Agent Skills），覆盖项目计划与交接、PPT 与方法图、需求澄清与代码审查、提 PR 前自检、CLI 设计、前端设计、项目模组安装、浏览器自动化和深度学习实验流程，并随附 Superpowers 工作流。技能是写给 AI 读的操作手册：装好后用平常的话提需求，AI 会按场景自动加载对应技能。

- 宿主：Claude Code（`~/.claude/skills/`）、Codex（`~/.agents/skills/`，Codex 当前的用户级技能目录）。
- 系统：Linux / macOS（安装脚本为 bash）。部分脚本需要 Python 3.10+；`plan` 命令调用 `/usr/bin/python3`，少数子命令需要 PyYAML。
- 版本：见 [CHANGELOG.md](CHANGELOG.md)。当前共 16 个技能（含 1 个必装）加 Superpowers。

## 技能清单

**必装：`dev-pr-self-check`（提 PR 前自检）。** `install.sh` 无论怎么用 `--only` 都会把它装上，`--list` 里标“必装”。

| 目录 | 技能名 | 用途 | 常用说法（触发） | 来源 / 许可证 |
|---|---|---|---|---|
| `dev-pr-self-check` | dev-pr-self-check | **必装**。提 PR 前作者侧自检：跑测试与构建、新上下文审 diff、按风险分级，写测试 / 风险 / 回滚说明，收敛审查轮次；附 `scripts/scope_check.py` | “提 PR”“准备合并”“PR 自检” | 自有，MIT |
| `share-top` | project-top | 项目目标、计划、进度、验收与交接（“六合一”项目记录法），附 `plan` 命令和 `sixone-cli.py` | “建个计划”“现在做到哪了”“交接一下”“梳理项目方法论” | 自有，MIT；吸收 planning-with-files、mattpocock/skills 部分思路（许可见 `references/absorbed/`） |
| `pptx-gen` | content-pptx-gen | AI 生图做整页图片型 PPT，默认白底，交付 PNG/PPTX 与备注 | “PPT 绘图”“生成 PPT 图片” | 自有，MIT |
| `real-ppt` | content-real-ppt | 原生可编辑 PPT：按原图复刻文字、形状、连接线，或制作/修改原生 PPT | “把这张图转成可编辑 PPT”“做个真实 PPT” | 自有，MIT |
| `share-technical-roadmap` | content-technical-roadmap | 方法思维导图、技术流程图、方法框架图，交付可编辑 draw.io 源图与预览 | “画个方法思维导图”“技术流程图” | 自有，MIT |
| `content-black-white-roadmap` | content-black-white-roadmap | 黑白科研技术路线图，先草图再出图，按需重建可编辑 PPT | “黑白技术路线图” | 自有，MIT |
| `grill-to-spec` | dev-grill-to-spec | 盘问需求、挑战方案、澄清决策，需要时整理成 spec | “盘问我”“grill me”“帮我把需求问清楚” | 自有，MIT；思路来自 mattpocock/skills（MIT） |
| `share-code-review` | dev-code-review | 代码 / PR / diff 审查，过度设计检查 | “审一下这个 PR”“看看这段代码有没有问题” | 自有，MIT；吸收 mattpocock/skills、github/spec-kit 部分思路 |
| `dev-find-wheels` | dev-find-wheels | 找轮子：复杂实现先找成熟包，比较候选后由你选型 | “有没有现成的库”“找轮子” | 自有，MIT |
| `share-agent-cli` | dev-agent-cli | 设计和规范 CLI：help、机器输出、退出码、非交互；附 Python 母模板 | “给这个脚本做个 CLI” | 自有，MIT；Click 母模板含 simonw/click-app 的 Apache-2.0 LICENSE/NOTICE |
| `frontend-design` | frontend-design | 后台、表单、多步业务界面的视觉设计 | “美化这个后台页面” | [anthropics/skills](https://github.com/anthropics/skills)，Apache-2.0（改过的副本，见 `UPSTREAM.json`） |
| `design-taste-frontend` | design-taste-frontend | 落地页、作品集、营销页与整体改版（与上一项二选一） | “做个落地页”“重新设计首页” | [Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill)，MIT（改过的副本，见 `UPSTREAM.json`） |
| `playwright-cli` | web-playwright | 用 Playwright CLI 操作真实浏览器：打开网页、填表点击、截图、E2E 验收与演示录像；附会话脚本和录像验收子流程 | “用浏览器打开这个网址把表填了”“跑一遍 E2E 验收”“录个操作演示” | 自有，MIT；`references/` 部分改编自 [microsoft/playwright-cli](https://github.com/microsoft/playwright-cli)，Apache-2.0（技能内 `LICENSE`、`NOTICE.md`）。**需另装命令**，见下文“Playwright CLI” |
| `share-autoresearch-engine` | research-dl-pipeline-base | 深度学习训练与研究闭环：过拟合/欠拟合诊断、loss 与超参、论文模块移植与对照实验、AI 检查点、实验回执与门禁；附 PyTorch Lightning 模板和检查脚本 | “模型过拟合了怎么办”“把这篇论文的模块接进我的网络”“帮我设计消融实验” | 自有，MIT；随附 ARIS（wanshuiyin/Auto-claude-code-research-in-sleep，MIT）技能正文、tuning_playbook（CC-BY-4.0）、AREX-Skill（Apache-2.0/MIT）、ms-swift 示例（Apache-2.0）等，来源、提交与许可见 `UPSTREAM.json` 与各 `vendor/` LICENSE |
| `mlgain-integrate-component` | research-mlgain-integrate-component | 组件接入参考库（research-dl-pipeline-base 的配套）：论文 / SOTA 模块接入模型时选接入点、接线与兼容检查、受控比较、效果下降排查；附探针脚本与报告模板。源文件为低频库格式 `REFERENCE.md`，本包改名为 `SKILL.md` | “把这个论文模块接进我的模型”“接入后效果变差了”“选哪个接入点” | 自有，MIT |
| `share-project-provision` | dev-project-provision | 模组安装器：按项目类型推荐并安装项目级技能模组（前端设计、软件骨架、Impeccable、授权逆向包等） | “这个项目要装什么”“开启前端设计模式”“开启骨架模式” | 自有，MIT；模板分别保留上游许可（见下文） |
| `third_party/superpowers` | superpowers（插件） | TDD、系统化调试、头脑风暴、写计划、子智能体开发等 15 个工作流技能 | 自动触发，如“帮我做个新功能” | [obra/superpowers](https://github.com/obra/superpowers) 7.0.0，MIT，作者 Jesse Vincent |

技能之间会互相引用。凡是写着“（可选，本包未包含）”的技能，本包没有收录，AI 读到时会跳过或改用通用做法。需要外部模型复核时，可另装公开的外援审查技能 <https://github.com/YonganZhang/external-review-skill>。

## 安装

```bash
git clone https://github.com/YonganZhang/student-ai-skills.git
cd student-ai-skills
bash install.sh --dry-run      # 先看会做什么
bash install.sh                # 默认：两端都装、复制方式、装 plan、装 Superpowers
```

常用选项（完整说明见 `bash install.sh --help`）：

- `--target claude|codex|both`：只装某一端。
- `--only share-top,grill-to-spec`：只装指定技能（`bash install.sh --list` 查看名字）。
- `--link`：用软链接代替复制，之后 `git pull` 即生效；仓库目录不能删除或移动。
- `--force`：覆盖已存在的同名目录。默认遇到同名目录会跳过并提示，不会覆盖你自己的技能。
- `--no-plan`、`--bin-dir DIR`：不装或换位置安装 `plan` 命令（默认 `~/.local/bin/plan`，指向已安装的 `share-top/scripts/plan`）。
- `--superpowers official|vendored|skip`：Superpowers 的安装方式，见下文。
- `--with-playwright`：缺 `playwright-cli` 命令时执行 `npm install -g @playwright/cli`；不加时只提示。

装完后开一个新会话，技能才会被发现。Claude Code 里输入 `/skills` 可查看；终端里运行 `plan help` 检查计划命令。

## Playwright CLI（playwright-cli 技能需要）

`playwright-cli` 技能驱动的是 Microsoft 官方 npm 包 [`@playwright/cli`](https://www.npmjs.com/package/@playwright/cli)（源码 [microsoft/playwright-cli](https://github.com/microsoft/playwright-cli)，Apache-2.0，提供 `playwright-cli` 命令；本包维护时用的是 0.1.22）。安装脚本默认只检查并提示，不会替你全局安装 npm 包：

```bash
node --version                      # 需要 Node.js 18+
npm install -g @playwright/cli      # 或：bash install.sh --only playwright-cli --with-playwright
playwright-cli --version
```

没有全局写权限时不要用 sudo，改用户级前缀：`npm config set prefix ~/.npm-global`，再把 `~/.npm-global/bin` 加入 PATH。首次打开会话时会按需下载 Chromium。远程服务器或无桌面的 Linux 只能跑无头浏览器；要让人看画面或接管，需要自行准备图形桌面、虚拟显示（如 Xvfb）加远程桌面，本包不提供这类服务。

## research-dl-pipeline-base 的说明

- 训练规则要求 CUDA GPU，默认用 PyTorch Lightning；`assets/lightning-template/` 需要 `pip install -r requirements.txt`（含 `lightning`），其 CPU 单测和 `tests/smoke.py` 不需要显卡。
- 原技能里约 32 MB 的时序/神经算子上游代码（`references/model-zoo/upstream/`，含数据与预编译库）没有随附；`references/model-zoo/SOURCES.md` 记录了仓库和 commit，需要时自行克隆。作者私有项目的实验记录也未随附，案例只保留可迁移的做法。
- 文中引用的组件接入参考库 `mlgain-integrate-component`（简称 mlgain）已随包提供，装在同级目录，相对链接直接可用。其探针脚本的测试 `tests/test_dl_probes.py` 需要 PyTorch，没有 torch 时会跳过。

## Superpowers

`third_party/superpowers/` 是官方 7.0.0 的原样副本（含 LICENSE、README 和 hooks），来源与版本记录在 [third_party/superpowers/VENDORED.md](third_party/superpowers/VENDORED.md)。安装脚本默认：

1. Claude Code：`claude plugin install superpowers@claude-plugins-official`（官方插件市场）；新装的 Claude Code 若没有这个市场，改试 `claude plugin install superpowers`（内置插件目录，版本可能比 7.0.0 旧，用 `claude plugin list` 查看）。
2. Codex：`codex plugin add superpowers@openai-curated-remote`（也可在 Codex 里输入 `/plugins` 搜索 Superpowers）。
3. 上述命令不存在或失败时，把随附的 `skills/*` 复制（或 `--link` 链接）到用户技能目录。这种退回方式没有插件自带的会话启动 hook，技能名也不带 `superpowers:` 前缀，功能以官方插件为准。

`--superpowers vendored` 跳过官方安装、直接用随附副本；`--superpowers skip` 不安装。Superpowers 上游 README 有一节 “Visual companion telemetry”，使用前请自行阅读。

## 模组（按需安装）

`share-project-provision` 不预装模组，只在你提出需要时按项目安装到 `<项目>/.claude/skills/` 和 `<项目>/.agents/skills/`。对 AI 说“这个项目要装什么”会先给建议清单，说“开启前端设计模式”等会直接安装对应预设。目录见 `skills/share-project-provision/references/modules/index.md`，主要有：

- 前端设计预设：`frontend-design` + `design-taste-frontend` 的项目级副本。
- 软件骨架（改编自 cursor/plugins 的 pstack architect，MIT）：说“设计软件骨架”“开启骨架模式”时启用。
- Impeccable（pbakaus/impeccable，Apache-2.0）：完整前端设计与评审流程，固定版本安装脚本 `scripts/install_impeccable.py`，先预览后安装。
- awesome-design-md（VoltAgent，MIT）：品牌风格参考，按需取材料。
- reverse-skill-pack：第三方逆向 / 安全研究技能（`P4nda0s/reverse-skills` 或 `zhaoxuya520/reverse-skill`）。**只用于你自己拥有或已获书面授权的目标**；未授权的软件、服务或设备一律不要用。
- Superpowers：账号级安装，见上节。

## 更新

- 复制安装：在仓库里 `git pull`，再运行 `bash install.sh --force`（会覆盖同名技能目录，你在已安装副本里的改动会丢失，先备份）。
- 软链安装：`git pull` 即可。
- Superpowers 官方插件按各宿主的插件更新方式更新；随附副本随本仓库版本更新。

卸载：删除 `~/.claude/skills/<目录>`、`~/.agents/skills/<目录>` 和 `~/.local/bin/plan`；官方插件用 `claude plugin uninstall superpowers` 或 `codex plugin remove superpowers`。

## 许可证

- 本仓库自有部分（安装脚本、文档及标注为“自有”的技能）使用 [MIT 许可证](LICENSE)。
- 第三方内容保留原许可证和署名，不受上述 MIT 覆盖：
  - `skills/frontend-design/`、`share-project-provision/templates/skills/frontend-design/`：Apache-2.0，anthropics/skills（`LICENSE.txt`）。
  - `skills/design-taste-frontend/`、`share-project-provision/templates/skills/design-taste-frontend/`：MIT，Leonxlnx/taste-skill（`LICENSE`）。
  - `share-project-provision/templates/skills/dev-software-skeleton/`：MIT，cursor/plugins pstack（`LICENSE`）。
  - `share-agent-cli/assets/python-click/template/`：Apache-2.0，simonw/click-app（`LICENSE`、`NOTICE`）。
  - `share-top/references/absorbed/`：planning-with-files 与 mattpocock/skills 的许可文本随附。
  - `skills/playwright-cli/references/`：部分改编自 microsoft/playwright-cli，Apache-2.0（`LICENSE`、`NOTICE.md`）。
  - `skills/share-autoresearch-engine/references/aris/vendor/`：MIT，wanshuiyin/Auto-claude-code-research-in-sleep（`LICENSE`）；`references/upstream/vendor/`：tuning_playbook（CC-BY-4.0）、AREX-Skill（Apache-2.0 / MIT）；`assets/llm-native/ms-swift/upstream/`：Apache-2.0；`references/timesfm/`、`references/zarr/`：K-Dense-AI/scientific-agent-skills（Apache-2.0 / MIT）。
  - `skills/mlgain-integrate-component/`、`skills/dev-pr-self-check/`：自有，MIT。
  - `third_party/superpowers/`：MIT，Jesse Vincent（`LICENSE`）。
- 各技能的上游仓库、固定提交与改动说明记在其 `UPSTREAM.json`。
