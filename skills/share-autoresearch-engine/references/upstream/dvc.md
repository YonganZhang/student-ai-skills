# 上游卡片：DVC（工具，只借思路）

## 链接与许可证

- 仓库：<https://github.com/treeverse/dvc>（默认分支 `main`）
- 许可证：Apache-2.0。

## 吸收的版本

- 记录点：2026-10-22 查到的默认分支 HEAD `56e59829512ff134aa269099a2099587b810b4dd`（提交于 2026-08-06）。行号对应此 commit。
- 未安装，也不计划作为依赖引入。

## 拿了什么（只借思路）

| 上游位置 | 内容 | 状态 |
|---|---|---|
| `dvc/stage/serialize.py:195` `to_lockfile`、`:143` `to_single_stage_lockfile` | `dvc.lock` 为每个阶段记录命令、依赖与输出的内容哈希、参数值；任一哈希变化即判定该阶段过期 | 已实现记录部分（`scripts/run_manifest.py`:`main` 记录命令、代码/数据/配置/检查点的 sha256、seed、划分；代码不引用 DVC）；"哈希变化即判过期"备选，未接入（该脚本只写清单，不读回比较） |
| `dvc/dvcfile.py:394` `Lockfile` | 锁文件的读写与 schema | 备选，未接入（`run_manifest.py` 只写不读，字段自定） |
| `dvc/schema.py` | 锁文件字段约定 | 备选，未接入 |

## 没拿什么及原因

- DVC 本身：与项目已有的 `_meta/_registry.yml`、数据账本和 TOP 记录职责重叠；再加一套会形成两个真源。
- 远端存储与 `dvc push/pull`：数据传输已有固定渠道。
- `dvc exp` 实验管理：调参已用 Optuna 存储，见 [optuna 卡片](optuna.md)。

## 下次升级看哪些路径

- `dvc/stage/serialize.py`、`dvc/dvcfile.py`、`dvc/schema.py`（锁文件格式是否变化）
- 只在要调整 `run_manifest.py` 的哈希字段设计时才需要看。
