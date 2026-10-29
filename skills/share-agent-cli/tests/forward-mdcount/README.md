# mdcount

给人和自动化统计一个目录【直接子项】里 Markdown 文件数量的只读小工具。不递归、不写入目标目录。

## 安装与入口

Python 3.8+，仅标准库，无需安装。入口：本目录 `cli.py`。
源码所属：本技能 `tests/forward-mdcount/`，是独立前向演练的固定样例，供复跑验证；不是全局业务命令。

## 最短调用

```bash
python3 cli.py --help
python3 cli.py count tests
python3 cli.py count tests --json
python3 -m unittest discover -s tests -v
```

`--json` 可在子命令前或后。目标名以 `-` 开头时用 `count -- <目录>`。

## 输出与失败

- 默认一行文字：`<N> markdown files  <解析后的绝对路径>`；成功时 stderr 为空。
- JSON 成功输出 stdout：`{"schema_version":1,"ok":true,"data":{"path":"...","markdown_files":N}}`。
  版本 1 字段固定；`path` 为跟随软链解析后的目录绝对路径。
- 失败时 stdout 为空、stderr 为中文诊断（JSON 模式同样走 stderr）。
- 退出码：0 成功；1 运行/业务失败（目标不存在、无权限、软链环、目标不是目录）；2 用法错误（缺子命令、缺目录参数、未知选项）。`--help` 为 0。不交互（stdin 接 DEVNULL）。

## 状态变化

全程只读：仅 `resolve` + `stat` + `scandir` 目标目录，不读取文件内容，不写入、不删除、不递归子目录。无预览/确认/锁/认证/分页/打包/发布/hook/MCP。

## 计数规则（业务定义）

- 只数目标目录的**直接子项**，不进入子目录。
- 只数**普通文件**且文件名以小写 `.md` 结尾。
- 名为 `x.md` 的**目录**不计入；指向 `.md` 的**子项软链**不计入（子项分类用 `follow_symlinks=False`）。
- 目标目录参数**本身**跟随软链；指向文件而非目录时按业务失败（退出码 1）报“不是目录”。

## 验证与维护

```bash
python3 -m unittest discover -s tests -v   # 12 项进程行为测试
```
测试覆盖：help、文本/JSON 计数、非递归、.md 目录排除、子项软链不计、空目录为 0、
缺目标与“不是目录”的真实失败、用法错误退出码 2、`--` 分隔选项样路径、目录软链跟随、软链环无 traceback、只读不改输入目录。

来源：复制自 `~/.claude/skills/share-agent-cli/assets/python-minimal/`，
复制时母模板所在仓库的提交号（原私有仓库，已省略）
（注意：复制时母模板在该提交仍为**未提交**工作区文件，提交号只标记工作区基线，不构成运行依赖）。
母模板更新按 diff 人工合并。
