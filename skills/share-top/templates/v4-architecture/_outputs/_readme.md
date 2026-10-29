# _outputs/ — 运行结果

> Git：小结果（csv/json/md/png 汇总表与图）追踪；批量二进制（npy、parquet、h5、权重等）不追踪，只追踪配方（脚本 + 配置 + 参数）。

## 放什么

主流程或实验的运行结果，按运行建子目录（如 `<日期>-<主题>/` 或 run id），失败的运行也保留。

## 不放什么

- 代码 → `_code/`、`_pipelines/`；这里只放产物。
- 沙盒试验的输出 → 留在 `_sandbox/<日期>-<主题>/outputs/`。

## 入口

先看跑次登记（`_meta/_runs.yml`，若启用）或本目录最近的运行子目录，找到结果对应的配置与提交。

## 文件角色

每个运行子目录建议带一份运行说明（提交 SHA、配置、参数、成败与原因），数字才能追溯到配方。

## 改动原因去哪查

`python3 ~/.claude/skills/share-top/scripts/sixone-cli.py record for-file <文件>`，或 `git log -- <文件>`。
