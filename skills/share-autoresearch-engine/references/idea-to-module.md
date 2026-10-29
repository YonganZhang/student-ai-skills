# 从论文到模块：找 idea、读代码、移植、对照

目标不是“找一篇看起来厉害的论文”，而是：**找到可迁移的机制，确认它解决的是我们的问题，忠实实现，并用受控实验判断它是否真的有用。**

## 0. 先判断我们的任务

在搜论文前写清：

- **任务范式**：识别/分类、检测、分割、追踪、匹配、重识别、姿态、深度估计、时序、多模态。
- **部署单元**：一张图、一个 patch、一个 track、一个视频、一个 3D volume。
- **评价器**：mAP、F1、Dice、HOTA/MOTA、IDF1、RMSE、延迟/显存。
- **瓶颈**：小目标、遮挡、尺度变化、运动模糊、长尾、域偏移、时序关联、分辨率、算力。
- **现有结构**：backbone、neck、head、skip、FPN、时序模块；模块准备接在哪一层。

识别和追踪不是一回事：识别模块常解决语义/判别，追踪模块常解决时序关联/运动/身份保持。不要拿分类论文的模块直接宣称能提升多目标追踪。

## 1. 去哪里找

### 顶会与期刊

| 方向 | 主要来源 |
|---|---|
| 视觉 | CVPR、ICCV、ECCV、WACV、BMVC、TPAMI、IJCV、TIP |
| 机器学习 | NeurIPS、ICLR、ICML、AAAI、IJCAI |
| 多媒体/视频 | ACM MM、CVPR/ICCV 的视频/追踪 workshop |
| 检测/分割/追踪 | CVPR/ICCV/ECCV 主会、WACV、BMVC；追踪另有 VOT/OTB 相关 workshop |
| 医学 3D | MICCAI、IPMI、MIDL、Medical Image Analysis |
| 时序 | NeurIPS/ICLR/ICML、KDD、AAAI；任务专属会议 |

入口：

- **CVF Open Access**：https://openaccess.thecvf.com/ （CVPR/ICCV/WACV 论文与补充材料）
- **NeurIPS Proceedings**：https://papers.nips.cc/
- **PMLR**：https://proceedings.mlr.press/ （ICML/AISTATS 等）
- **OpenReview**：https://openreview.net/ （ICLR/NeurIPS 等投稿、评审、rebuttal）
- **AAAI Proceedings**：https://ojs.aaai.org/index.php/AAAI
- **ACM DL**：https://dl.acm.org/ （ACM MM 等）
- **arXiv**：https://arxiv.org/ （预印本；注意版本与是否中稿）
- **Hugging Face Papers**：https://huggingface.co/papers （近期论文/代码入口；原 Papers with Code 入口已重定向，旧榜单只作历史线索）
- **Papers with Code（历史）**：https://paperswithcode.com/ （可能重定向到 HF；引用前先核当前页面）
- **Semantic Scholar**：https://www.semanticscholar.org/ （引用网络、相关工作）
- **Google Scholar**：https://scholar.google.com/ （找引用/后续工作；注意噪音）

### 代码与文档

- **GitHub**：官方仓库优先；看 README、`models/`、`modules/`、`configs/`、`tests/`、issue。
- **HF Papers / GitHub README**：论文页/仓库的 code 链接；没有官方代码时看高星复现，但要核对差异。
- **Hugging Face**：模型卡、Transformers/timm/Accelerate/PEFT 文档；看版本与 license。
- **框架文档**：PyTorch、Lightning、MMEngine/MMDetection/MMSegmentation、MONAI、nnU-Net、Detectron2、Ultralytics、timm。
- **作者主页/实验室页面**：补充材料、项目页、后续版本、失败案例分析。

## 2. 怎么搜

不要只搜一个关键词。用“任务 + 机制 + 代码”的组合：

```text
(task) small object detection feature fusion 2024 CVPR
(task) multi-object tracking association transformer 2023 ICCV
(task) medical image segmentation boundary-aware 2024 MICCAI
(mechanism) dynamic convolution official code
(mechanism) deformable attention implementation
(backbone) efficient backbone real-time detection github
```

筛选顺序：

1. **任务匹配**：它解决的是识别、检测、分割、追踪还是别的？评价器是否一致？
2. **机制匹配**：它假设的失败模式（小目标、遮挡、尺度、运动、长尾）我们有没有？
3. **代码可用**：官方代码、license、依赖、可复现性；没有代码的论文优先级下降。
4. **预算匹配**：训练/推理成本我们能不能承受；它是不是靠更大 backbone/更多数据涨点。
5. **证据强度**：有没有消融、位置对照、同预算 baseline、失败案例；还是只报一个总榜。

## 3. 怎么读一篇论文

按这个顺序做笔记，不要从摘要直接跳到“我们也要加”：

1. **问题**：它明确解决什么失败模式？在什么数据/任务上？
2. **假设**：为什么这个模块应该有用？机制是什么？
3. **结构**：模块的输入/输出、通道/尺度、放在哪个 stage、和谁融合。
4. **训练**：loss、优化器、 schedule、初始化、冻结策略、数据增强。
5. **对照**：baseline 是什么；有没有同参数量/同预算/位置消融；提升多少。
6. **边界**：作者自己写的 limitation、失败案例、适用条件。
7. **代码差异**：论文公式和官方实现是否一致；有没有隐藏 trick。

重点不是记住模块名，而是提取：

> **失败模式 → 机制假设 → 张量契约 → 接入位置 → 训练条件 → 证伪实验**

## 4. 怎么从 GitHub 找“创新模块”

1. 先找官方 repo；核对论文链接、commit、license。
2. 从 README 的模型表/配置文件定位模块文件，不从整个 repo 乱翻。
3. 看 `models/`、`modules/`、`layers/`、`ops/`、`blocks/`；找论文里的类名。
4. 读模块的 `__init__` 和 `forward`：输入输出 shape、归一化、激活、残差、mask。
5. 看它被插在哪个文件/哪个 stage；这比模块本身更能说明“原生位置”。
6. 看训练配置：lr、batch、schedule、初始化、freeze；这些可能是涨点的一部分。
7. 看 tests/issue：shape 边界、CUDA 扩展、版本坑、已知失败。
8. 固定 commit，把 repo/文件/行号写进实验记录。

**论文没代码 / 代码和论文不一致 / 只有部分模块开源**，都要在动手前标风险；不要用“复现版”冒充官方实现。

## 5. 把 idea 对到我们的结构

先画我们的结构图，标清：

- 输入分辨率、通道、stage 数；
- 每个 stage 的语义层级和感受野；
- skip/FPN/neck 的连接；
- head 前的特征尺度；
- 时序/多视图/多模态分支。

然后为候选模块找候选接入位置（含论文原生位置；数量按结构决定，不强制 2–3 个），逐个回答：

| 问题 | 不通过就别接 |
|---|---|
| 通道/尺度能不能对齐？ | 需要投影/插值/池化，代价多少 |
| 语义层级是否匹配？ | 浅层纹理模块接深层语义，假设可能不成立 |
| 感受野是否匹配？ | 模块假设的上下文被破坏 |
| 融合方式是否保留原机制？ | add 改成 concat 可能不再是同一模块 |
| 初始化能否接近 identity？ | 仅函数保持接口；不能则按作者初始化，查激活/更新，不强行零初始化 |
| 训练策略是否兼容？ | 新模块是否需要单独 lr/warmup/freeze |
| 推理成本是否可接受？ | 延迟/显存/吞吐是否超预算 |

如果论文说“通用”，仍然要检查：它的“通用”是在什么 backbone、分辨率、数据规模、任务上成立的。**通用是统计主张，不是数学定理。**

## 6. 移植：先忠实，再优化

1. **最小忠实实现**：保留论文的关键组件、归一化、激活、融合顺序；先不魔改。
2. **接口适配层**：把我们的张量转成模块期望的布局；适配层要薄、可测、可替换。
3. **shape/数值断言**：每个分支的通道、分辨率、mask、dtype 都断言。
4. **初始化**：仅函数保持接口做 identity/零初始化，step 0 同权重/buffers/eval/RNG 对拍；非残差模块按作者初始化，不强行零初始化。门控参数化要写清，避免双零互锁。
5. **strict reload**：保存/加载后 eval 输出一致；新参数在 optimizer 里且只出现一次。
6. **记忆/学习探针**：固定样本能到预期下限；真实增强下有下降。断梯度、全零梯度要失败；强增强/软标签不要求 loss 接近零。
7. **三种比较**：step 0 等价（仅函数保持）、训练后同 checkpoint on/off（贡献）、独立训练 baseline（净增益）。不要拿 on/off 当父模型。
8. **位置对照**：同一模块换候选位置；不适用就说明，不要只试一个插槽就判模块。
9. **同预算对照**：baseline 和候选同数据、同 split、同主预算轴、同评价器；干扰超参对称重调。
10. **消融**：每个组件、每种融合、每种初始化；最后才做技巧叠加。

## 7. 结果怎么判

- **有用**：同主预算、同评价器下稳定优于 baseline；报告效应和不确定性；消融能解释增益来源；不是只靠参数量/更久训练。
- **无用**：证据足够（接线/初始化/选点/预算有检查）、位置对照做过、对称重调后仍无增益；写清边界。
- **有害**：稳定更差，或收益以不可接受的成本/稳定性为代价。
- **不可判**：接线、初始化、选点、预算、评价器有一项没证据；先修，不写结论。

如果论文声称通用、工程也确认无误、仍不涨：优先怀疑“条件不匹配”（数据规模、分辨率、任务、位置、训练预算），把边界写清楚；不要靠反复换 seed 或看 test 硬救。

## 8. 找 idea 的更高一层

除了“找论文模块”，还可以从这些地方产生 idea：

- **失败模式驱动**：错误分析里反复出现的模式，比排行榜更适合产生模块。
- **跨域迁移**：检测的 FPN、分割的 skip、追踪的关联、NLP 的 attention/adapter，能不能迁移到我们的瓶颈。
- **组合**：两个互补机制组合，但一次只加一个，先证明各自有效。
- **简化**：把复杂模块拆成最小机制，往往比原样移植更容易成功。
- **反例**：论文的 limitation/失败案例，常是下一个改进点。

不要为了“新”而新。**先有失败模式，再有机制，再有模块。**

## 9. 检索记录模板

```yaml
paper:
  title:
  venue_year:
  arxiv:
  code:
  commit:
  config_paths: []
  weight_revision:
  dataset_revision:
  license:
  task:
  claimed_gain:
  mechanism:
  native_position:
  our_candidate_positions: []
  tensor_contract:
  training_conditions:
  risks:
  decision: port / screen / reject
```

## 相关

- 训练判断：[训练核心](training-core.md)
- 模块接入：[组件工作流](component-integration.md)、[结构判断门禁](architecture-judgment-gate.md)
- 论文移植忠实性：paper-port-fidelity（mlgain 组件接入参考库，可选，本包未包含）
- 来源与链接：[来源库](source-library.md)
