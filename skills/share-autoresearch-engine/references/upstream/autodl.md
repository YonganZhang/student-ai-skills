# 上游卡片：AutoDL（AutoDL Challenge 冠军方案）

## 链接与许可证

- 仓库：<https://github.com/DeepWisdom/AutoDL>
- 许可证：Apache-2.0。

## 吸收的版本

- commit `48db4eb04d55ce69e93d4a3bdc24592bdb34a868`（2021-01-12，仓库已多年不更新），吸收日 2026-10-22。
- 代码绑定 2019-2020 年的比赛接口与旧版 PyTorch，**不可直接复用**；只取机制和一个反例。

## 拿了什么

| 上游位置 | 内容 | 状态 |
|---|---|---|
| `AutoDL_sample_code_submission/Auto_Image/skeleton/projects/logic.py:295-297` `handle_divergence` | 发散时回滚到上一个检查点，学习率乘 0.25 | 已写进文档（`references/tuning/README.md`"训练过程里的保护"）；`mlgain/scripts/train_sanity_checks.py`（本包未包含） 没有对应检查 |
| 同文件 `:299-386`（`break_train_loop_condition`、`terminate_train_loop_condition`） | 按剩余时间预算估"再跑一轮测试+两轮训练"的耗时决定停止；指标平台期停止 | 备选，未接入 |
| `AutoDL_scoring_program/score.py:214-230`（`transform_time` 对数时间、`auc_step`）、`:626` `get_alc` | 学习曲线下面积（ALC）在对数时间轴上计算，兼顾早期表现与最终分数 | 备选，未接入 |
| `AutoDL_scoring_program/score.py:427` `compute_scores_bootstrap` | bootstrap 估误差；它按样本重采样，宜改为按图像（独立单位）重采样 | 备选，未接入 |
| `AutoDL_sample_code_submission/Auto_Image/model.py:135-220` `adapt` | **反例**：在验证集上搜索数据增强策略（142 行取验证分数，159-165 行搜索 100 个策略）= 用验证集做模型选择，之后验证分数不再是无偏估计 | 已写进文档（`references/tuning/README.md`"不要"第 1 条：不在评测集上调增强策略；未点名 AutoDL） |

## 没拿什么及原因

- 全部代码：比赛专用接口、Python/PyTorch 版本过旧，许可证允许但无复用价值。
- 文本、语音、视频、表格各赛道方案：与当前图像/定位任务无关。
- AutoAugment 快速搜索实现：其使用方式本身就是上面的反例。

## 下次升级看哪些路径

- 仓库自 2021 年起无更新，预计不会变化；`watch` 保留以便发现归档或删除。
- 如有更新，看 `AutoDL_sample_code_submission/Auto_Image/skeleton/projects/logic.py`、`AutoDL_scoring_program/score.py`、`AutoDL_sample_code_submission/Auto_Image/model.py`。
