# 可分发 Python CLI 母模板

多子命令、需要安装短入口或打包分发时用本模板。几十行内部脚本用旁边的 `python-minimal`；已有项目沿用原框架。本模板借鉴 click-app 的包结构，命令交互用 Click，生成与升级用 Copier，不另造生成器。

## 生成一个新项目

需要 Git、Python 3.10+ 和 uv。生成器依赖放任务环境；生成的项目拥有自己的依赖和业务代码。

```bash
uv venv /tmp/cli-template-env
uv pip install --python /tmp/cli-template-env/bin/python copier==9.18.2
/tmp/cli-template-env/bin/copier copy --defaults --vcs-ref HEAD \
  --data command_name=example-cli --data 'description=查询项目数据' \
  <本技能包仓库根目录或其 Git URL> /path/to/new-project
```

目标必须是新目录，已有项目不要直接套模板覆盖。来源是本技能包 Git 仓库根；根 `copier.yml` 只引入本技能配置，`_subdirectory` 限定输出目录。不会复制共享规则、其他技能或配置。`HEAD` 固定到当时提交；生成前确认源工作区干净，想复现实验时传具体提交号。模板没有任务、迁移或自定义扩展，无需 `--trust`。

命令名仅接受小写 ASCII 字母开头的字母、数字和连字符；Python 模块去掉命令名末尾的 `-cli` 再追加 `_cli`，例如 `example-cli` → `example_cli`、`class` → `class_cli`，避免重复后缀及关键字。描述经 JSON 字符串转义写入 TOML；带引号或换行也可生成。

进入生成目录，按生成 README 创建项目 `.venv`、安装 `.[test]`，验证真实命令、JSON、错误通道和退出码，再把路径查询示例换成实际业务。版本只维护在 pyproject；改版本后重新安装或构建。`.copier-answers.yml` 随项目提交，记录源路径、提交与答案，不手改。

## 更新已生成的项目

先让项目进入 Git 并提交本地业务改动，确认工作区干净。从生成项目目录运行：

```bash
/tmp/cli-template-env/bin/copier update --defaults --vcs-ref HEAD
git diff --check
.venv/bin/python -m pytest
.venv/bin/python -m build
```

再审 `git diff` 和 `git status`。Copier 会尝试重放项目改动，仍可能产生冲突；退出码 0 不能证明无冲突。默认 inline 模式用 `git diff --check` 检查；若改用 rej 模式，另外检查全部 `.rej` 文件。解决冲突、验证真实业务后再提交；不使用 recopy 覆盖本地业务。跨机器使用前保证答案里的源路径仍可访问，或者一开始使用可访问的共享仓库 URL。

母模板更新在共享仓库一次维护。生成物是项目源码，不运行时软链回本技能。测试 CI 只做测试和构建，PyPI/部署/凭证配置按真实项目另行决定。

## 验证与来源

生成项目附 Click 测试；生成器另有隔离 Git 测试，覆盖输出范围、答案版本、特殊字符、非法路径名、保留本地业务的升级及冲突。生成器测试使用 Python 3.11+（stdlib tomllib），不改变生成项目的 Python 3.10+ 要求。

另建消费环境，只安装构建出来的 wheel，再运行 `tests/verify_distribution.py --python <消费环境>/bin/python --command <消费环境>/bin/<命令> --target <生成项目>/README.md`。它从项目外的目录验证已安装短命令、模块入口、JSON、错误通道和退出码，不能用源码目录里的 editable 安装代替。

```bash
CLI_TEMPLATE_COPIER=/tmp/cli-template-env/bin/copier \
  python3.12 -m unittest discover -s ~/.claude/skills/share-agent-cli/tests \
  -p test_copier_template.py -v
```

源路径和版本以 [UPSTREAM.json](../../UPSTREAM.json) 为准；下载指纹与采纳取舍见 [吸收说明](../../references/absorbed/upstream-cli-patterns.md)。模板保留 click-app 的 Apache-2.0 LICENSE 和 NOTICE；未复制自动发布、作者 demo 更新或上游账户信息。
