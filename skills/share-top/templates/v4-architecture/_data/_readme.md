# _data/ — 清洗后、给流程消费的数据

> Git：说明文件（README、清单、schema、下载/清洗脚本）追踪；原始与大体量数据不追踪，登记到 `_meta/_data_registry.yml`（来源、路径、校验和、获取方式）。

## 放什么

流程要读的数据集，一个数据集一个子目录，建议命名 `<来源>_<范围>_<版本或日期>/`。

## 不放什么

- 原始参考资料（PDF、网页、截图）→ `_refs/`；临时下载 → `_tmp/`。
- 运行产生的结果 → `_outputs/`。

## 入口

先看 `_meta/_data_registry.yml` 找数据集的来源与获取方式，再进对应子目录。

## 文件角色

每个子目录可放一份短说明（字段含义、单位、已知问题）；获取/清洗脚本放本目录或 `_code/`，在登记里指过去。

## 改动原因去哪查

`python3 ~/.claude/skills/share-top/scripts/sixone-cli.py record for-file <文件>`，或 `git log -- <文件>`。
