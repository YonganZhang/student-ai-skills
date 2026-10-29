# Python 轻量 CLI 母模板

适用：少量内部命令，不需要发布框架。Python 3.8+，仅标准库，无安装步骤。`cli.py` 是真实只读示例：查询一个路径的元信息，不读文件内容，不写状态，不调用网络。

## 运行

在本目录执行：

```bash
python3 cli.py --help
python3 cli.py inspect README.md
python3 cli.py inspect README.md --json
python3 -m unittest discover -s tests -v
```

`--json` 可在子命令前或后。路径以 `-` 开头时，用 `inspect -- <路径>`；需要 JSON 时将 `--json` 放在 `--` 前。

## 输出契约

- 默认一行文字；成功 stderr 为空。
- JSON 成功输出 stdout：`{"schema_version":1,"ok":true,"data":{"path":"...","kind":"file","size_bytes":123}}`。版本 1 字段固定；`kind` 为 file/directory/other；跟随软链并返回解析后的绝对路径，目录 size 为文件系统元信息，不是目录内容总大小。
- 失败 stdout 为空，stderr 为诊断文字，包括 JSON 模式。退出码 0 成功，1 读取失败，2 参数用法错误；`--help` 为 0。不交互。
- 没有写入、预览、锁、认证、分页、打包、发布、hook 或 MCP。新增这些能力时补上真实实现、契约与相应测试。

## 复制与改造

把本目录复制到所属项目的**新目录**，排除 `__pycache__/` 等缓存，保留一份项目内源码。将 `inspect_path` 和命令改成真实业务，更新 README 与行为测试；不要把未改造的示例宣称为业务交付。机器契约不适用时可以调整，并同步消费者与测试。

在项目 README 的维护记录中写：来源 `~/.claude/skills/share-agent-cli/assets/python-minimal/`，以及复制时 `git -C <本技能包仓库根目录> rev-parse HEAD` 得到的提交号（从已提交母模板复制）。这是来源记录，不是运行依赖。母模板更新按 diff 人工合并；多个生成项目反复升级时评估 Copier，不整目录覆盖。
