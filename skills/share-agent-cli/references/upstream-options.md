# CLI 框架与模板选型

核验日期：2026-10-03。六个上游已下载固定提交的源码。标准库母模板仍为本机示例；新增 Click 母模板吸收 click-app 包结构、Click 测试接口和 Copier 版本追踪，保留相应许可证。实际运行版本与采纳范围见 [吸收说明](absorbed/upstream-cli-patterns.md)；Typer、oclif 未安装运行，选型不等于供应链审计。

| 场景 | 候选与依据 | 取舍 |
|---|---|---|
| 小型内部 Python 脚本 | [argparse 官方文档](https://docs.python.org/3/library/argparse.html)；本技能轻量母模板 | 现有 Python 环境即可；业务代码独立，不再造通用 CLI 框架 |
| Python 命令组、可分发包 | [Click](https://github.com/pallets/click)（BSD-3-Clause）；[Typer](https://github.com/fastapi/typer)（MIT） | Click 接口显式，Typer 基于类型声明；按仓库既有框架与团队习惯选择。二者是框架，不等于已满足本机 JSON/写入契约 |
| Python 包、测试与发布母模板 | [simonw/click-app](https://github.com/simonw/click-app)（Apache-2.0） | 作者登记真实使用者 shot-scraper、s3-credentials、git-history；提供测试与 PyPI 发布配置。对内部几十行脚本偏重，发布和自动化上传配置须按项目需求保留 |
| TypeScript 命令树、插件、构建发布 | [oclif](https://github.com/oclif/oclif)（MIT）、[模板说明](https://oclif.io/docs/templates/) | Salesforce 项目；`oclif` 是生成/构建/发布工具，运行框架是 `@oclif/core`。不为小型 Python 工具引入 Node 体系 |
| 多项目的母模板持续升级 | [Copier](https://github.com/copier-org/copier)（MIT）、[更新文档](https://copier.readthedocs.io/en/stable/updating/) | 记录生成答案和模板版本，升级时尝试保留项目修改；仍可能冲突，要审 diff，不能承诺自动无损更新 |
| 人类命令行体验核对 | [Command Line Interface Guidelines](https://github.com/cli-guidelines/cli-guidelines)（CC-BY-SA-4.0） | 指南，非代码框架或生成器；参考其设计原则，不整篇复制进常驻规则 |

不依星数选型。成熟度看真实消费者、维护状态、契约与维护成本；活跃框架也不会自动解决业务真源、并发、授权或部分失败。若已选框架，具体版本以项目环境与当次官方文档为准。

## 可复核的上游快照

API 核验：仓库 archived 状态、默认分支 HEAD 和最新 release。六个仓库当时均未归档；以下是选型证据，**不是本机锁定的依赖版本**。click-app 最近提交比框架少，实际消费者比提交频次更有解释力。

| 仓库 | HEAD（默认分支） | 提交日期 UTC | 最新 release（发布日期 UTC） |
|---|---|---|---|
| pallets/click | [06b2a6787411](https://github.com/pallets/click/commit/06b2a678741131fd577ce170e23e5ca0aeba0309) | 2026-09-23 | 8.5.0（2026-08-27） |
| fastapi/typer | [a80f6e5ecd74](https://github.com/fastapi/typer/commit/a80f6e5ecd74f32b983cca336a2f3cba98d9853a) | 2026-09-08 | 0.27.2（2026-08-28） |
| simonw/click-app | [84298e257d70](https://github.com/simonw/click-app/commit/84298e257d70d461866f0afb5458baa12d99f8f2) | 2025-10-09 | 无 release |
| oclif/oclif | [661eb80ee3ba](https://github.com/oclif/oclif/commit/661eb80ee3ba41bc5aa9e1099f92c1d34c0fca93) | 2026-09-25 | 6.0.2（2026-09-25） |
| copier-org/copier | [38f9bb042f07](https://github.com/copier-org/copier/commit/38f9bb042f079009e5a52b5f7acf9dba17646690) | 2026-09-30 | v9.18.2（2026-09-07） |
| cli-guidelines/cli-guidelines | [697d6a29fc8c](https://github.com/cli-guidelines/cli-guidelines/commit/697d6a29fc8c93d3981a755c0c7683507ad39c3e) | 2026-05-16 | 无 release |

使用上游模板前再核对对应版本许可证与生成文件；本机依赖进入项目环境。只需内部脚本时，不安装 Cookiecutter/Copier/oclif，也不接 PyPI 发布。
