# CLI 成熟项目吸收与验证

日期：2026-10-03。任务：下载上次选型中的成熟项目，把有实际用途的部分吸收到既有全局 CLI skill 和母模板，做行为测试，再请 Claude 独立检查。

## 实际结果

六个仓库的固定提交源码归档均已下载、检查 SHA-256 并保留。新增按需的可分发 Python CLI 母模板：借鉴 click-app 包结构，使用 Click 的公开命令和测试 API，由 Copier 生成及版本升级。小型内部命令继续用原标准库母模板。

没有新造 CLI 框架或覆盖器；没有新增全局技能、常驻规则、hook、MCP 或服务。share-agent-cli 描述保持原文，入口仍 46 行，详细模板与来源按需读取。Claude/Codex 经现有相对软链读取同一份共享真源。

## 来源与取舍

| 来源 | 已吸收的实际能力 | 未采用部分 |
|---|---|---|
| [simonw/click-app](https://github.com/simonw/click-app) | pyproject、安装短入口、项目 README、测试 CI 骨架 | 自动 PyPI 发布、作者 demo 更新、账户信息 |
| [pallets/click](https://github.com/pallets/click) | 命令组、版本与错误 API、CliRunner 的通道和退出码测试 | 不复制库实现；不使用已弃用的 isolated_filesystem |
| [copier-org/copier](https://github.com/copier-org/copier) | 限定子目录生成，记录来源/提交/答案，升级重放本地业务修改 | 不写自己的生成器，不启用任务/迁移/扩展或 trust |
| [oclif/oclif](https://github.com/oclif/oclif) | 修正 TypeScript 选型的版本判断 | 未安装或引入其 Node 框架；生成器 Node >=22，与 README 和生成模板要求分开核对 |
| [fastapi/typer](https://github.com/fastapi/typer) | 保留备选，已有项目沿原框架 | 未新增第二套 Python 发布模板，未运行 Typer |
| [CLI Guidelines](https://github.com/cli-guidelines/cli-guidelines) | 对照已有 CLI 合同 | 未复制 CC-BY-SA 长正文或追加常驻说明 |

来源提交、吸收路径、许可证登记在 skill 根 UPSTREAM.json；六个归档的下载 URL、SHA-256、缓存路径和处置记录在 references/absorbed/downloads-2026-10-03.json。Apache-2.0 LICENSE 与 click-app 上游逐字一致，生成包含 LICENSE 与来源/本地适配 NOTICE。

## 母模板以后怎么使用

稳定 CLI 都要有可运行 help、README、明确退出码和非交互路径；机器输出按真实消费者需要实现。轻量脚本用 python-minimal；需要安装与分发的 Python 多命令包才用 python-click。已有 CLI 沿原框架和兼容契约，不强制迁移。

Copier 入口位于共享仓库根 copier.yml，仅引入技能内配置，输出受 _subdirectory 限定。它使用 Copier 专用 !include 标签，不能用通用 YAML safe_load 代替。生成项目源码独立维护，不运行时软链回母模板。

生成前选择新目录、干净的源提交；安装项目环境后改成真实业务。生成答案随项目提交，不手改。升级前提交项目改动；升级后审 diff、用 git diff --check 检查 inline 冲突、重跑业务测试与构建。Copier 退出 0 仍可能留冲突，实测证实此边界。具体命令见 assets/python-click/README.md 和生成项目 README。

## 测试证据

| 验证 | 结果 |
|---|---|
| 原轻量母模板 | 10 项通过 |
| 配置/技能创建/路由回归 | 42 项通过 |
| 既有独立 mdcount 前向演练 | 12 项通过 |
| Copier 隔离 Git 生成与升级 | 5 项通过，含非法命令名和越界防护、特殊字符、业务保留、冲突 |
| 新模板真实命令行为 | 14 项在 Python 3.10.12、3.12.13 各通过 |
| 原 click-app 生成/安装/版本测试 | 1 项通过，出现 Click 弃用提醒，本地模板已避免此 API |
| sdist 与 wheel | 实际构建成功，wheel 包含许可证与 NOTICE |
| 只安装 wheel 的独立消费环境 | 从无关目录运行 6 项子进程检查通过，含模块入口与失败通道 |
| 来源与引用 | 六个归档指纹、逐字 LICENSE、登记的上游路径、UPSTREAM 格式、技能入口引用均通过 |
| 双端配置 doctor | 0 warning，0 broken link，79/79 Codex home 就绪；Claude 固定上下文仍显示 20.3k |

84 个不同测试 = 10 + 42 + 12 + 5 + 14 + 1。不同 Python 版本、重复回归和 Claude 重跑不重复计数；6 项消费环境检查单独列出。

最低版本补测发现版本测试的嵌套双引号 f-string 在 Python 3.10 无法解析，已改为先取版本变量；3.10 和 3.12 复跑均通过。本机系统 Python 3.10 缺 ensurepip，使用 build --installer uv 成功隔离构建，无 sudo 或系统包更改；3.12 默认构建也已通过。Click 运行版为 8.5.0，源码核对 HEAD 为 8.6.0.dev，二者没有混称。

## Claude 独立检查

首轮 job 20261003T172601__claude__1513677 严格完成。Claude 在独立隔离 Git 仓库生成项目，逐条验证 README、安装、命令通道/状态、测试与打包，另做保留业务和冲突的两条升级实验；无 P0/P1。

三条建议的处置：模块名重复 cli 后缀已修正，默认 example-cli → example_cli，class → class_cli；Copier 专用 include 在入口注明，保留单一配置真源；软链环 RuntimeError 分支保留，主控在 Python 3.10/3.12 均实际复现该异常，原“死代码”判断有误。

最终窄复核 job 20261003T173300__claude__1617838 严格完成。Claude 独立复现 Python 3.10/3.12 的 RuntimeError，撤回“死代码”判断；查明没有消费仓库根文件的通用 YAML 校验器，!include 属正常 Copier 配置而非缺陷；修正后的命名、安装、版本、模块入口、软链失败与 14 项 Python 3.10 业务测试通过。最终无未解决的 P0/P1/P2。

## 验证范围

本次验证 Linux 上的模板生成、安装、构建、命令行为和升级；没有实际执行 GitHub Actions，也未运行 oclif/Typer。双端共享读取一致与静态路由回归通过，未另做双方自然语言自动触发的全量对照。没有证据证明“所有场景最优”，但新增能力有可复跑的收益与明确边界。

规则约束没有删减；这次没有修改全局规则。新增能力放在按需材料里，选型与生成物维护成本按任务承担。
