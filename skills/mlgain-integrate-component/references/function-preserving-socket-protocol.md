# 函数保持的组件插座协议

**修正一个不够严格的直觉**：不要用"占位物换上去分数应该几乎不变或略升"来验证接口对不对——随机初始化的线性层已经改变了函数、输出尺度和条件数，额外参数可能让优化变难或过拟合，不会自动提分；重训后的分数又受随机性影响，不适合当接线正确性的第一判据。正确做法是把"接线等价"和"训练后分数"彻底拆开，用三种不能混淆的对照：

- **hard bypass**：不执行candidate，只验证wrapper/路由本身。
- **enabled no-op**：执行candidate，但用零门/零输出投影使有效贡献为0。
- **trainable control**：简单affine/MLP/conv，验证插入位置的通用容量，**不证明接线**（它是active control，不是neutral control）。

## 必跑阶段

| 阶段 | 配置 | 验收信号 | 回答的问题 |
|---|---|---|---|
| S0 | 原baseline checkpoint | 固定样本的logits/中间张量 | 真实参照函数 |
| S1 | socket存在，`mode=bypass`，不执行candidate | 同checkpoint、`eval()`、同输入逐元素`torch.allclose`；核对state/RNG | wrapper/路由是否改了baseline |
| S2 | candidate启用，但用零门或零输出投影 | 初始输出与S0等价，报max_abs/max_rel | 展开后模型能否从baseline函数出发 |
| S3 | affine/MLP/参数匹配的可训练control | 小batch可过拟合，记激活/梯度/分数 | 该位置增加一般容量是否有用；**不是**接线证明 |
| S4 | 真实component v1/v2，共用adapter/merge | 单变量指标+分支机制诊断 | 特定机制相对S3是否有额外价值 |

**S1才是"插座有没有接坏"的硬测试。** S3的占位物通过不能代替S4的contract测试。若要声称提升来自候选模块的特有机制，应加尽可能匹配参数量/FLOPs的通用MLP/conv对照；若只问整体改动值不值，不必强制配平，但仍要报告资源变化。

## 实操坑点（都是真实会踩的）

- 占位物与真组件的非线性、感受野、mask、归一化和输出统计可能完全不同，S3通过不能代替S4。
- 插入新对象会消耗RNG，可能改变其他层初始化；必须加载同一baseline checkpoint，不能只相信"同seed"。
- 即使有效输出被零门乘成0，**BatchNorm running stats仍可更新，Dropout仍可消耗RNG**。`bypass`必须真正不执行分支；"启用但零贡献"应是另一个mode，不能混为一谈。
- adapter若改了norm、channels、padding或mask，试验已经不是"只换component"了——adapter必须显式、有版本、可独立测试。
- 额外参数可经全局gradient clipping、optimizer param groups、EMA、分布式同步或显存压力间接改变baseline训练；要记录optimizer membership和被迫改动的batch/sequence length。
- 输出等价只证明baseline路径没坏，**不证明candidate启用时的语义维度、因果性和padding正确**——还需专项测试（见下方PyTorch模板的测试清单）。

## parity验收标准

- 从同一checkpoint加载，eval mode + 固定输入。
- 比较最终输出和插入点两侧张量；报max_abs/max_rel，按dtype设atol/rtol。
- bypass时不执行candidate；检查BN buffer、RNG和train/eval副作用。
- 等价通过后仍要测semantic axes、mask、padding和causality。

## 失败定位

- S1失败：wrapper/路由/基线权重加载错。
- S1过、S2失败：merge/init/adapter不是真no-op。
- S2过、S3无法过拟合：梯度/optimizer/尺度或位置有问题。
- S3过、S4不佳：检查真组件contract、归纳偏置和raw/effective contribution（见 `residual-gating-safe-integration.md` 的"有用性诊断"）。

代码模板见 `assets/pytorch-component-socket.py`；版本化 manifest 见 `assets/component-integration-manifest.yaml`；最小测试清单见 `assets/test-component-socket.py`。
