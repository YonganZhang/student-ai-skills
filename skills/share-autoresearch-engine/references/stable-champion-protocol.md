# 稳定冠军与同预算搜索协议

这份协议把“最好模型”限定为：在冻结数据、预注册候选空间和固定预算内，经重复实验与独立验收得到的稳定冠军。它不承诺全局最优，也不要求每个任务都必须产生提升。

## 1. 开始前冻结

每个任务/场景只允许一个主 endpoint，并登记：

- 数据版本、split manifest 及哈希；
- incumbent 身份、代码/权重/配置及证据路径；
- 主指标方向、计算函数与聚合口径；
- 至少一个安全指标和允许退化上限；
- 候选模型家族、最大运行次数、训练更新/样本/墙钟上限；
- 重复单位：seed、空间 fold、井族、数据集或 rolling origin；
- promotion 的最小实际改善与拒绝规则；
- frozen test 的唯一开启时点和一次性消费规则。

看到结果后不能改变这些字段。确需改变时，关闭当前 round，说明原因并创建新的 protocol id。

## 2. “稳定”的最小定义

- 随机训练模型：至少 3 个独立 seed；重要论文主结果优先 5 个。
- 确定性模型：不能伪造 seed 重复，改用至少 3 个独立 fold、空间块、井族或时间起点。
- 每个重复都使用相同候选配置和预算；失败运行保留在分母中。
- 报告所有重复的原始值、均值、标准差和 95% 区间；样本少时优先对重复单位做 bootstrap 或配对区间。
- 稳定冠军要求：主指标达到实际改善门，重复方向一致，区间支持提升，安全指标不过退化线。

三次里一次大胜、两次变差不属于稳定改善。只比较最好的 seed 属于选择性报告。

## 3. BETU 预算

BETU（Baseline-Equivalent Training Unit）只在同一场景、同一硬件 lane 内归一化。先真实测量强基线一次训练的：样本数、优化器更新数、CPU core-seconds、GPU-seconds、峰值显存和墙钟。

候选的保守收费为：

`BETU = max(samples/reference_samples, updates/reference_updates, cpu_core_seconds/reference_cpu_core_seconds, gpu_seconds/reference_gpu_seconds)`

某项不适用时不参与最大值。预训练权重下载和共同固定缓存单列一次性成本，不能藏进零成本。HPO 的每次 trial、技术性重试和失败运行都计费。

自研框架与 AutoML 的公平比较至少同时匹配：

- 可访问的数据和基础模型池；
- 候选执行次数；
- 总 BETU 与硬件 lane；
- 最大并发度和墙钟窗口；
- frozen test 开启次数。

除最终分数外，报告首次有效改善成本、有效候选率、promotion 成功率和总资源。

## 4. 分层搜索而非一次性大搜

1. **Family screen**：至少三个有意义的模型家族，小预算筛除明显不适配者。
2. **Incumbent confirmation**：对前列家族按完整 development protocol 重复，确认冠军不是偶然。
3. **Adjacent innovation**：围绕冠军一次改变 1–2 个设计原语，执行配对消融。
4. **Independent promotion**：由不读设计结论的 verifier 重算指标并检查协议。
5. **Refit/test**：配置冻结后 refit；frozen test 只消费一次且不得反馈下一候选。

Family screen 的结果不能与完整预算结果混榜。不同模态、标签空间或数据集必须分 lane。

## 5. HPO、增强与早停

- 先比较模型家族，再对最终 1–2 个家族做小规模 HPO；不要给拟推广模型更多搜索次数。
- HPO 只读取 development fold，搜索空间和 trial 数预注册；best trial 仍需独立重复。
- 数据增强只在 fold-train 拟合/采样。每种增强必须有无增强对照，并验证标签、坐标和掩码仍有效。
- 所有候选共享 early-stopping metric、patience、最小 delta、warm-up 和最大更新数。
- 早停检查频率不同时，以实际 optimizer updates 与 samples seen 计费，不能只比 epoch。
- 校准、阈值和后处理只在 development 内选择，并视为候选配置的一部分。

## 6. NaN 与训练异常

统一恢复顺序在运行前冻结，例如：

1. 保存首次失败 trace、batch id、loss/gradient/activation 摘要；
2. 同配置重放失败 batch；
3. 若所有模型都允许，启用统一 gradient clipping 或数值稳定实现；
4. 只允许一次登记过的技术重试，仍计入预算；
5. 再失败则标记 `numerical_failure`，不得悄悄降低学习率多跑几次。

OOM、超时、数据损坏、provider 失败和 NaN 分开编码。失败候选不能从有效候选率的分母中删除。

## 7. Promotion 判定

候选只有同时满足以下条件才晋级：

- 协议、数据哈希、代码与预算完整；
- 主指标相对 incumbent 达到预注册 practical delta；
- 配对重复方向达到预注册一致性门；
- 95% 区间满足对应的 superiority/non-inferiority 规则；
- 安全指标、关键类别/井族/空间区不过退化线；
- 机制反证支持候选确实使用了新增信息；
- 独立 verifier 重算一致。

若没有候选过门，正式结论是“保留 incumbent”。不要把 search 完成误写成模型提升。

## 8. 执行完整性：正式运行前后的固定动作

条件：任何要产出正式结论或上线权重的训练/评估。

- **预演**：用极小配置（少量步数/树）跑通全流程，测试集用验证集的一部分代替，正式测试行不进入预演。预演通过后才冻结协议、写入代码哈希。
- **单次评估守卫**：评估脚本开始时先写一个只能创建一次的标记文件，已存在就拒绝运行；预演中确认第二次运行确实被拒绝。
- **逐元素重载**：每个权重在独立进程重新加载，训练集和验证集预测必须与保存值逐元素相同。出现 1e-16 量级差异时，先查并行归约的顺序（线程池累加、GPU 原子操作），推理改为固定顺序或单线程，而不是放宽容差。
- **先冻结、再评估**：所有权重、预处理和代码的哈希写入账本后，才读取测试标签。
- **独立复算**：另写脚本、从标签原件重新读取，复算全部指标；子智能体或外部模型给出的数字同样复算后才引用。
- **校验工具自检**：检查脚本先用已知对、已知错的样本跑一遍，确认它能区分；检查失败时先区分是数据问题还是检查脚本问题，两种都留记录。

## 9. 候选账本最小字段

每次尝试保留：`round_id`、`candidate_id`、`parent_incumbent`、`hypothesis`、`primitive_changes`、`ablation_role`、`split_hash`、`seed_or_repeat`、`budget_planned`、`budget_actual`、`status`、`metrics`、`artifacts`、`failure_reason`、`promotion_verdict` 和 `verifier_record`。

账本只追加，不覆盖历史行。重新运行产生新的 attempt id，并显式指向原失败尝试。
