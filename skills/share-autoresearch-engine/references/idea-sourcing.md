# Idea 采购：从 Kaggle、Hugging Face、论文和失败样本里找可用的 trick

目标不是收集“奇技淫巧”，而是建立一条**主动发现 → 机制判断 → 小成本验证 → 固化/淘汰**的流水线。trick 只有接上我们的失败模式，才算 idea；否则只是别人的排行榜噪音。

## 1. 先定“采购需求”

不要漫无目的地刷榜单。先写采购单：

- **当前瓶颈**：小目标、遮挡、尺度、长尾、域偏移、时序关联、分辨率、延迟、显存、标签噪声、训练不稳。
- **任务/评价器**：识别、检测、分割、追踪、匹配；指标和阈值规则。
- **预算**：可接受的训练时间、推理延迟、显存、标注成本。
- **现有 baseline**：哪一格最强，差距多少，错误样本长什么样。
- **禁止项**：不能改数据边界、不能泄漏 test、不能靠外部数据/伪标签绕过规则。

采购单越具体，越不容易被“SOTA 模块”带偏。

## 2. 去哪里找

### Kaggle：比赛代码与讨论

| 入口 | 找什么 | 注意 |
|---|---|---|
| https://www.kaggle.com/competitions | 同任务的历史比赛 | 看 metric、数据规模、规则 |
| 比赛页 `Code` | 高分 notebook、训练/推理脚本 | 许可、依赖、是否用外部数据 |
| 比赛页 `Discussion` | 第一名方案、失败复盘、技巧帖 | 很多“技巧”是公榜过拟合 |
| https://www.kaggle.com/code | 通用 notebook/教程 | 质量参差，先看 vote/复现 |
| https://www.kaggle.com/datasets | 数据/预训练资源 | 许可与泄漏风险 |

重点看 **solution writeup**，不是单个 notebook。一个高分方案通常包含：数据切分、增强、模型、loss、训练 schedule、后处理、集成、阈值。要拆开看哪一项真正贡献。

### Hugging Face：论文、模型、数据、Space

| 入口 | 找什么 | 注意 |
|---|---|---|
| https://huggingface.co/papers | 近期论文/代码 | 不是正式评审；看社区讨论 |
| https://huggingface.co/models | 预训练 backbone、微调模型卡 | 看训练数据、license、评测口径 |
| https://huggingface.co/datasets | 数据卡、划分、预处理 | 数据卡不等于无泄漏 |
| https://huggingface.co/spaces | demo/可视化/推理代码 | demo 不等于可复现训练 |
| https://huggingface.co/learn | 课程/教程 | 入门可以，研究判断仍看原文 |
| https://huggingface.co/blog | 工程/训练技巧 | 版本相关，别当定理 |

模型卡重点：训练数据、预处理、输入分辨率、归一化、评测集、license、已知偏差。**不要拿模型卡上的分数直接和我们任务比。**

### 论文、代码与工程博客

- CVF Open Access、NeurIPS Proceedings、PMLR、OpenReview、AAAI、ACM MM、MICCAI；
- Papers with Code、Semantic Scholar、arXiv；
- 官方 GitHub、issue、release、tests；
- 框架文档：PyTorch、Lightning、timm、MMEngine、MONAI、nnU-Net、Detectron2、Ultralytics；
- 技术博客：Karpathy、Google Tuning Playbook、fast.ai、PyTorch tutorials、Hugging Face blog；
- 比赛/实验室的 solution writeup、workshop paper、tech report。

详细检索流程见 [从论文到模块](idea-to-module.md)，链接总表见 [来源库](source-library.md)。

## 3. 怎么读一个“高分方案”

不要从“用了什么模型”开始，按下面拆：

1. **数据**：划分、增强、伪标签、外部数据、重采样、类别平衡、hard negative。
2. **模型**：backbone、neck、head、attention、归一化、初始化、重参数化。
3. **loss**：任务 loss、辅助 loss、权重、label smoothing、focal、对比/蒸馏。
4. **训练**：lr、batch、schedule、warmup、EMA、SWA/model soup、梯度裁剪、AMP、freeze。
5. **推理**：TTA、多尺度、滑窗、阈值、NMS/WBF、track management、集成。
6. **评测**：本地 CV、公榜/私榜、阈值选择、是否泄漏、是否过拟合公榜。
7. **成本**：训练/推理资源、依赖、可复现性、license。

然后问：**它解决的是哪个失败模式？机制是什么？在我们的数据/结构/预算下还成立吗？**

## 4. Trick 分类库

| 类别 | 常见 trick | 主要风险 |
|---|---|---|
| 数据 | 强增强、mixup/cutmix、cutout、copy-paste、伪标签、外部数据、重采样、hard negative | 改变分布、泄漏、标签噪声放大 |
| 模型 | 更强 backbone、FPN/neck、attention、可变形卷积、重参数化、归一化/初始化改动 | 参数量/算力上涨，收益归因不清 |
| Loss | focal、dice、boundary、label smoothing、辅助任务、蒸馏、对比学习、多任务权重 | loss 尺度、任务冲突、指标不对齐 |
| 训练 | lr schedule、warmup、EMA、SWA/model soup、grad clip、AMP、freeze/分层 lr、长训练 | 预算不同、不稳定、和结构耦合 |
| 推理 | TTA、多尺度、滑窗、阈值搜索、NMS/WBF、track 关联、集成/校准 | test 调参、延迟、过拟合公榜 |
| 评测/选择 | CV 策略、OOF、阈值选择、best−2nd、seed 平均 | 选择泄漏、噪声当信号 |
| 工程 | 混合精度、compile、DDP、缓存、数据 loader | 只影响速度，不改善科学结论 |

## 4.1 高价值 trick 清单（按机制用，不按名字抄）

| Trick | 机制/适用 | 主要风险 | 最小验证 |
|---|---|---|---|
| EMA | 同一 run 的权重指数滑动平均，降尾段方差 | BN 统计量要重估；与 lr/衰减强相关 | select 段比较 EMA/非 EMA，冻结后 test 验收 |
| SWA | 尾段多 checkpoint 等权平均，常配重估 BN | 不是任何训练都适用；学习率阶段要匹配 | select 段比较，单独重估 BN |
| Model soup | 多个独立微调模型（同 init/架构）权重平均 | 模型必须同源/可插值；不是 EMA 的别名 | 先验证单模型，再在 select 选 soup 权重 |
| TTA / 多尺度推理 | 平均多视图预测，降方差 | 阈值/匹配要重选；延迟上涨；可能过拟合公榜 | select 段选 TTA 组合，固定后 test |
| 伪标签/自训练 | 用高置信预测扩数据 | 确认偏差、test 泄漏、阈值依赖 | 只用训练集无标签数据；独立 select |
| Hard negative mining / OHEM | 聚焦难负样本，适合匹配/检测/追踪 | 噪声标签被放大；训练不稳 | 固定负样本池，比较命中率/误检 |
| Copy-paste / mosaic / mixup / cutmix | 增强组合/正则，适合小数据/检测 | 分布改变、遮挡/边界不真实 | 同 split 下对照；看错误切片 |
| Label smoothing / focal / class-balanced | 处理噪声/长尾/难例 | 软目标下限、权重拍脑袋；指标不升 | 先算 loss 下限，再比较校准/召回 |
| Dice / boundary / deep supervision | 分割小目标/边界；多尺度监督 |  loss 尺度、辅助头抢主任务 | 单加一项，同预算消融 |
| 辅助任务（ReID/跟踪/分割） | 给主任务补监督/表示 | 任务冲突、标签成本 | 冻结/解冻对照，看主指标 |
| 多尺度训练 / progressive resizing | 适应尺度变化、省算力 | BN/锚框/感受野不匹配 | 固定推理尺度，比较尺度切片 |
| 重参数化（RepVGG 类） | 训练多分支、推理单路；主要收益可能在部署/速度 | 训练精度不一定涨；融合规则/BN 等价易错 | 训练/推理输出对拍，延迟实测，同预算比精度 |
| 分层 lr / freeze-unfreeze | 保护预训练、稳定新模块 | 不是所有任务都需要；可能欠拟合 | 同预算比较，看新参数梯度 |
| OOF stacking / 加权融合 | 利用模型互补性 | 泄漏、权重过拟合 select | 严格 OOF，权重只在 select 选 |
| WBF / NMS / 阈值搜索 | 检测后处理；合并重复框 | 阈值过拟合；指标口径不同 | 在 select 上选，test 固定 |
| 跟踪管理（birth/death、Kalman、运动） | 补时序关联/身份保持 | 参数多、场景依赖 | 按 track 长度/遮挡切片评估 |

**用法**：先选 1 个 trick，对应 1 个失败模式；用最小验证回答“有没有超过噪声”。不要一次把表里的东西全加上。

## 5. 采纳前的“trick 记分卡”

每个候选 trick 先打分，不直接进主线：

| 问题 | 不通过就 |
|---|---|
| 它对应我们的哪个失败模式？ | 先不做；只是“别人涨”就放观察池 |
| 机制能不能用一句话说清？ | 说不清，先读论文/代码，不接入 |
| 在我们的数据/结构/预算下是否可迁移？ | 先做最小 screen，不直接全量 |
| 是否依赖外部数据/伪标签/公榜信息？ | 标风险；可能违反规则或不公平 |
| 是否能在同预算、同 split 下对照？ | 不能对照，不做结论 |
| 预期收益 vs 复杂度/延迟 | 收益不明且成本高，拒绝 |
| 有没有官方代码/许可/可复现？ | 没有，降级为“读 idea”，不移植代码 |
| 会不会和现有 trick 冲突？ | 一次只加一个，先消融 |

记分卡可直接复制 [trick scorecard 模板](../assets/trick-scorecard.template.yml)；一个**未在本项目实跑**的字段示例见 [Copy-Paste 示例](../assets/trick-scorecard.example.yml)，不要把示例当结果。

**“trick 叠加”不是科学。** 先证明单个有效，再做 2×2 或“单加/组合”对照：若 A+B 不大于 max(A,B)，组合没有证据；否则只是把排行榜配方搬过来。

## 6. 公榜/私榜与泄漏红线

Kaggle/HF 的高分方案常见陷阱：

- **公榜过拟合**：反复看 public LB 调阈值/融合，私榜崩。
- **泄漏**：同一病人/视频/位置跨 fold；预处理统计用了全量；伪标签把 test 信息带进训练。
- **外部数据**：比赛允许不代表我们允许；数据来源/license 要核。
- **不可复现**：缺 seed、缺预处理、缺推理代码；notebook 只保存输出。
- **算力不对等**：靠更多 GPU/更长训练涨点，不能当方法增益。
- **指标口径不同**：mAP 的 IoU 阈值、F1 的匹配半径、追踪的 ID 切换定义不同。

我们的规则不变：**选择在 select 段，test 最后验收；公榜不是我们的验证集。**

## 7. 主动发现 underwater 问题

不要等模型失败才找问题。固定做这些扫描：

1. **错误切片**：按类别、尺度、遮挡、亮度、视图、track 长度、边界、空真值分组，找最差 slice。
2. **曲线异常**：train/val gap、平台、尖峰、best-at-cap、验证指标和 loss 脱节。
3. **数据异常**：重复样本、近重复、错标、空标、标签分布、预处理统计、split 泄漏。
4. **基线异常**：baseline 是否调过、预算是否一致、评价器是否同版本。
5. **选择异常**：`best − 2nd`、并列数、阈值敏感度、seed 方差。
6. **部署异常**：输入分辨率/归一化/通道顺序、延迟、显存、batch 组成。
7. **文献异常**：论文 claim 的条件、代码和论文差异、复现失败、负结果。
8. **比赛复盘**：高分方案里哪一项是我们的盲区；哪一项是公榜噪音。

每个异常写进 **issue ledger**（见 [从问题到流水线](incident-to-pipeline.md)），不要停在“感觉哪里不对”。

## 8. 从 trick 到 pipeline

一个 trick 只有满足下面条件，才进入默认流程：

1. 在至少两个独立 split/seed 上有效；
2. 同预算、同评价器下增益稳定；
3. 消融能解释增益来源；
4. 不破坏数据/test/许可边界；
5. 成本可接受；
6. 有回归检查，防止以后改坏。

进入 pipeline 后写：触发条件、默认参数、对照、失败回退、负责人、最后验证日期。没有这些，它只是“某次实验的技巧”，不是团队能力。

## 8.5 生成自己的 idea，而不是只搬运

1. **从失败切片反推机制**：最差的 50 个样本有什么共同点？需要更多上下文、尺度对齐、时序关联，还是标签修正？
2. **从比赛方案拆机制**：把“第一名用了 X”拆成“X 改变了哪条梯度/特征/决策”，再判断是否适用于我们。
3. **跨域迁移**：检测的 FPN、分割的 skip、追踪的关联、NLP 的 adapter/attention，先找结构同构，再移植。
4. **做减法**：去掉一个模块/一层/一个 loss，若不变差，说明原结构冗余；简化往往比叠加更稳。
5. **改约束**：把“更大模型”换成“更小模型 + 更好监督/蒸馏/数据”，常能逼出真正的方法。
6. **组合但只加一个**：两个互补机制可以先各自验证，再组合；不要用组合掩盖单模块无效。

好 idea 的判据不是“新”，而是：**对应真实失败模式、机制可解释、工程可验证、成本可接受。**

## 9. 每周/每个 plateau 的 20 分钟扫描

- 10 分钟：看当前任务最新比赛/论文/模型卡，记录 3 个候选；
- 5 分钟：对每个候选填 trick 记分卡，只留 1 个；
- 5 分钟：写最小验证实验和证伪条件；进 issue ledger。

不要每天刷榜；plateau、换任务、负结果、新比赛时触发即可。

## 相关

- 论文→代码→模块：[idea-to-module.md](idea-to-module.md)
- 训练判断：[training-core.md](training-core.md)
- AI 检查点：[ai-checkpoints.md](ai-checkpoints.md)
- 问题固化：[incident-to-pipeline.md](incident-to-pipeline.md)
- 来源总表：[source-library.md](source-library.md)
