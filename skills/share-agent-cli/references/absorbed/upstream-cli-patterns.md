# CLI 上游吸收记录

2026-10-03 下载六个仓库的完整固定提交归档，解压普通文件；Copier 的四个符号链接未展开。原始包保留在任务目录 `~/tmp/cli-absorption-20261003/`，来源、SHA-256 和处理结果见 [下载清单](downloads-2026-10-03.json)。上游版本以本技能根 `UPSTREAM.json` 为唯一登记；下载不等于全部采用或通过安全审计。

## 采纳与舍弃

| 上游 | 实际接入 | 调整或不采纳 |
|---|---|---|
| [click-app](https://github.com/simonw/click-app) | 可分发包的 pyproject、console entry、项目 README、测试 CI 骨架 | 改为 src 布局、转义描述、限定依赖；不复制自动 PyPI 发布、作者 demo 更新、账号信息；保留 Apache-2.0 LICENSE 与 NOTICE |
| [Click](https://github.com/pallets/click) | group/version/错误 API，CliRunner 检查 stdout、stderr、退出码 | 真实业务示例和 JSON 契约由本机定义；库作为项目依赖使用，不复制实现。线程内不并行 CliRunner；各测试用独立临时目录 |
| [Copier](https://github.com/copier-org/copier) | 唯一生成器、答案和来源提交记录、保留本地改动的升级 | 输出限定到模板子目录；无任务/扩展/迁移，不开 trust；默认 inline 冲突用 git diff --check、业务测试和构建验收，不写自己的覆盖器 |
| [oclif](https://github.com/oclif/oclif) | 更新 TypeScript 选型与版本判断 | 生成器 package.json 要 Node >=22，但 README 写 18+；所附生成模板仍写 Node >=18 和旧 major 依赖。三者须分别核对实际版本，不能用 README 代替包元数据。不复制 TS 框架，不安装生成器 |
| [Typer](https://github.com/fastapi/typer) | 保留类型声明风格的备选 | 已有 Python 项目按原框架继续，新母模板已有 Click，无证据需要第二套发布模板；未安装运行 |
| [CLI Guidelines](https://github.com/cli-guidelines/cli-guidelines) | 对照既有设计合同 | 本机已有 help/README/机器输出/退出码/非交互合同，未复制长篇 CC-BY-SA 正文，也不加常驻规则 |

## 入口与维护成本

新能力接入既有 share-agent-cli 的场景表和母模板说明，仅按需加载。轻量 Python 标准库母模板保持默认；需要分发才读 `assets/python-click/README.md`。未新增全局 skill、hook、MCP 或服务。

共享 Git 根新增 `copier.yml` 引入技能内配置，只为成熟生成器提供仓库级入口；没有另存一份配置。生成项目的业务代码独立维护；母模板可升级，但不能承诺无损自动合并。

## 本次真实验证环境

- Python 3.12.13 与 3.10.12，任务 venv 中 Copier 9.18.2、Cookiecutter 2.6.0、Click 8.5.0、pytest 9.1.1、build 1.6.1；构建隔离环境 setuptools 84.0.0。
- 生成器五个隔离 Git 测试覆盖限定输出、来源/提交、引号和换行、非法目录名、保留本地文件与编辑的升级、版本冲突检查。
- 生成业务测试 14 项覆盖 help、版本、JSON 开关位置、只读结果、用法和运行错误、软链环与选项形路径。
- 14 项业务测试在 Python 3.10 和 3.12 实跑；3.10 补测发现嵌套双引号 f-string 语法问题，已改为独立版本变量。上游原 click-app 的生成、安装与版本测试也实跑，其 isolated_filesystem 触发 Click 弃用提醒，本地使用 tmp_path。
- sdist 和 wheel 实际构建；wheel 安装进独立消费环境，从无关目录运行短命令与模块入口，检查正常与失败状态。本机系统 Python 3.10 缺 ensurepip，隔离构建使用 build 的 `--installer uv`，未要求 sudo 或安装系统包；Python 3.12 的默认构建另已通过。

Click 当前源 HEAD 自述 8.6.0.dev；使用的是发布版 8.5.0，不声称直接运行开发 HEAD。oclif/Typer 只核对源码，未运行；本次实跑 Linux 上的 Python 3.10 与 3.12，没有实际执行 GitHub Actions。

## 复跑

模板生成与升级按 `assets/python-click/README.md`。测试具体命令、独立审查和最终结果另见本次吸收报告；旧的 CLI 创建审查报告保留当时状态，不改写历史。

下载可按清单 `download_url` 重新获取，再验证 `archive_sha256`。解压仅选 regular files 并验证成员路径在目标内，不执行上游工作流。模板许可证逐字保留，来源说明在生成物 NOTICE，不把 GitHub 页面当可自由复制的整段规则。
