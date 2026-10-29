# 上游卡片：Optuna

## 链接与许可证

- 仓库：<https://github.com/optuna/optuna>
- 许可证：MIT（Preferred Networks）。

## 吸收的版本

- 阅读的源码：commit `2b50cfc626355d3f6e6b055b5a275a9ea2e134ed`（2026-10-21，`version.py` 为 5.1.0.dev），吸收日 2026-10-22。
- 核对过的已安装版本：optuna 5.0.0（2026-10-22，`scripts/hpo_study.py` 及其测试按此版本编写）。用到的 API 以已安装版本为准；下列行号对应上面的 commit。安装用当前项目的解释器。

## 拿了什么

| 上游位置 | 内容 | 状态 |
|---|---|---|
| `optuna/storages/_rdb/storage.py:143-170`（`RDBStorage` 参数）、`:1041` `record_heartbeat` | SQLite 存储 + 心跳，进程被杀后 trial 能判定为过期 | 已实现（`scripts/hpo_study.py`:`open_storage`，`RDBStorage(heartbeat_interval, grace_period, …)`） |
| `optuna/storages/_heartbeat.py:156` `fail_stale_trials` | 过期 trial 标记为 FAIL | 已实现（`scripts/hpo_study.py`:`cmd_run`） |
| `optuna/storages/_callbacks.py:17` `RetryHeartbeatStaleTrialCallback`（`:135` `RetryFailedTrialCallback` 是已弃用别名） | 过期 trial 自动重排 | 已实现（`scripts/hpo_study.py`:`open_storage`，只用新名） |
| `optuna/storages/journal/_file.py:25` `JournalFileBackend` | 不想用 SQLite 时的文件日志存储（NFS 下注意锁） | 备选，未接入 |
| `optuna/study/study.py:843` `enqueue_trial(skip_if_exists=…)`、`:694` `set_user_attr` | 基线配置先入队且不重复；把 run 清单/哈希挂到 trial | 已实现（`scripts/hpo_study.py`:`cmd_create` 入队、`make_objective` 挂 git HEAD 与 run 清单 sha256） |
| `optuna/study/study.py:980` `add_trials`、`:738` `trials_dataframe` | 导入历史 trial；导出表格 | 备选，未接入（`report` 自己汇总，不调用 `trials_dataframe`） |
| `optuna/samplers/_partial_fixed.py:21` `PartialFixedSampler` | 固定变量钉死，只搜干扰变量 | 已实现（`scripts/hpo_study.py`:`cmd_run`）；已写进文档（`references/tuning/README.md`） |
| `optuna/samplers/_qmc.py:38` `QMCSampler` | 探索期准随机搜索 | 已实现（`scripts/hpo_study.py`:`QmcThenTpe`） |
| `optuna/samplers/_tpe/sampler.py:342-345`（`multivariate` / `group` / `constant_liar`） | 收敛期 TPE；并行时 constant liar 防止重复采样 | 已实现（`scripts/hpo_study.py`:`QmcThenTpe`，`multivariate=True, constant_liar=True`；`group` 未用） |
| `optuna/pruners/_wilcoxon.py:27` `WilcoxonPruner` | 按图像配对的逐步剪枝 | 已写进文档（`references/tuning/README.md`"剪枝"条）；`scripts/hpo_study.py` 故意用 `NopPruner`，未接 |
| `optuna/pruners/_patient.py:17` `PatientPruner` | 带耐心的剪枝包装 | 备选，未接入 |
| `optuna/importance/_ped_anova/evaluator.py:51` `PedAnovaImportanceEvaluator` | 超参重要性（对高质量区间） | 已实现（`scripts/hpo_study.py`:`importance`，供 `report` 用） |
| `optuna/visualization/_slice.py:148` `plot_slice`、`_edf.py:42` `plot_edf` | 边界检查与研究间比较的图 | 备选，未接入 |
| `optuna/terminator/` | 基于改进上界的提前终止 | 备选，未接入 |
| `optuna/_callbacks.py:15` `MaxTrialsCallback` | 预算按完成、剪枝、失败与运行中 trial 计（运行中占位，失败仍花预算） | 已实现（`scripts/hpo_study.py`:`cmd_run`）；已写进文档（`references/tuning/README.md`） |

更正：`MaxTrialsCallback` 在 `optuna/_callbacks.py`，不在 `optuna/study/_callbacks.py`。

## 没拿什么及原因

- CMA-ES、GP、NSGA 系列采样器：当前任务单目标、维度低，TPE + QMC 够用。
- gRPC / Redis 存储：本机单机，SQLite 足够。
- Optuna Dashboard：不新增常驻服务。

## 下次升级看哪些路径

- `optuna/storages/_rdb/storage.py`、`optuna/storages/_heartbeat.py`、`optuna/storages/_callbacks.py`（心跳与重试 API 近期改过名）。
- `optuna/samplers/_tpe/sampler.py`（`multivariate` / `constant_liar` 默认值在 5.x 变过）。
- `optuna/study/study.py`、`optuna/_callbacks.py`、`optuna/pruners/_wilcoxon.py`。
- 升级已安装版本前，在 `scripts/hpo_study.py` 的测试上重跑一遍。
