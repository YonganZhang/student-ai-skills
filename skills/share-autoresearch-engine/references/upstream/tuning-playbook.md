# 上游卡片：Deep Learning Tuning Playbook

## 链接与许可证

- 仓库：<https://github.com/google-research/tuning_playbook>
- 许可证：CC-BY-4.0（全文见 `vendor/tuning_playbook-LICENSE`）。复制或改写都要署名：Godbole, Dahl, Gilmer, Shallue, Nado, *Deep Learning Tuning Playbook*, 2023。

## 吸收的版本

- commit `7554a51f5d3002ba90308d39701b586f5a9b962e`（上游最后提交 2024-06-12），吸收日 2026-10-22。
- 逐字副本：`vendor/tuning_playbook-README.md`（与上游 `README.md` 字节一致，sha256 见 UPSTREAM.json 的 vendored 条目可重算）。

## 拿了什么

行号对应上述 commit 的 `README.md`，也就是本地逐字副本的行号。

| 上游位置 | 内容 | 状态 |
|---|---|---|
| `README.md:844-882` | 搜索边界判定：最优点贴边就扩边界；发散/不稳定点按不可行处理 | 已写进文档（`references/tuning/README.md` 第 2、4 步） |
| `README.md:901-995` | 看最优几组 trial 的训练/验证曲线：过拟合、步间方差、训练末尾仍在改进 | 已写进文档（`references/tuning/README.md` 第 5 步） |
| `README.md:996-1056` | 隔离图（isolation plot）：对每个科学变量取干扰变量最优后的分数比较 | 已写进文档（`references/tuning/README.md` 第 5 步） |
| `README.md:1057-1110` | 三种方差（trial / 研究 / 数据）；采纳前把最好配置重跑 N 次估 trial 方差 | 已写进文档（`references/tuning/README.md` 第 6 步：重跑 N 次估重训方差；三种方差的分类未写）；`references/workflow/standard-flow.md` S8 只写"配对多 seed" |
| `README.md:1111-1148`、`1663-1799` | 探索期用准随机搜索、收敛期再交给贝叶斯优化；不可行 trial 的处理 | 已实现（`scripts/hpo_study.py`:`QmcThenTpe` 先 QMC 后 TPE；`make_objective` 对非有限指标/失败命令记 FAIL）；已写进文档（`references/tuning/README.md` 第 4 步） |
| `README.md:1186-1254` | 不受算力限制时估 `max_train_steps`：无正则、恒定学习率扫到训练集拟合 | 已写进文档（`references/tuning/README.md` 第 3 步） |
| `README.md:1508-1528` | 固定步数训练，事后从周期性检查点里回看选最好的（top-N 保存） | 已写进文档（`references/tuning/README.md` 第 3 步）；`scripts/selection_exposure_check.py` 按曲线取最优步并判定该步是否测到新分支，不保存检查点 |
| `README.md:1817-1986` | 不稳定性：用 2 倍最优学习率短跑约 500 步判断；warmup 扫法；按梯度范数第 90 百分位定裁剪阈值；残差分支零初始化 | 已写进文档（`references/tuning/README.md` 第 2 步，未写"2 倍学习率短跑 500 步"的具体做法）；`../mlgain-integrate-component/scripts/train_sanity_checks.py` 没有对应检查 |

科学 / 干扰 / 固定变量的划分（同一 README 的增量调参章节）也体现在 `references/workflow/standard-flow.md` 的 S7。

## 没拿什么及原因

- 输入流水线优化、多主机、BatchNorm 实现细节（1368-1586）：与本机单卡小数据场景关系弱。
- Adam 超参与学习率衰减族 FAQ（1589-1662）：只作阅读材料，不写成规则；具体默认值由各项目合同决定。
- 准随机搜索的实现链接（1752-1772）：由 Optuna `QMCSampler` 代替，不另写实现。

## 下次升级看哪些路径

- `README.md`（唯一正文；上游近两年基本不动，重点看是否改章节顺序导致行号漂移）。
- `LICENSE`（许可证是否变化）。
- 升级时先 `diff vendor/tuning_playbook-README.md <新版>`，行号变了就同步改本表。
