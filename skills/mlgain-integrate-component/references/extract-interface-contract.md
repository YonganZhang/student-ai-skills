# 抠出组件的真实接口契约

在写任何集成代码之前，实际读候选组件的**源码**（不是只读论文正文，论文经常省略关键实现细节），确认下面每一项，不能靠训练记忆里"这类模块大概长什么样"来猜：

## 必须确认的契约项

- **输入输出形状与 dtype**：几维张量、每一维代表什么（batch/seq/channel/feature 的具体顺序）、期望的 dtype（fp32/fp16/bf16 是否有要求）。
- **归一化顺序假设**：这个组件期望输入已经被怎样归一化/标准化过？它自己内部有没有再做一次归一化（重复归一化和缺失归一化都会悄悄破坏效果）？
- **序列长度假设**：是否假设固定长度、是否支持变长（padding/mask 怎么处理）、对超长序列有没有隐含的复杂度或数值稳定性问题。
- **是否需要预训练/warmup**：论文里这个组件是从零训练还是依赖某个预训练权重/特定的初始化方案？是否需要专门的 warmup 学习率 schedule（很多模块论文正文不提，但官方代码的默认配置里写死了）。
- **原 pipeline 里的确切插入位置**：pre-norm 还是 post-norm、是否搭配 residual connection、在 encoder 还是 decoder、在哪一层之后——这些位置选择通常是组件生效的必要条件，换个位置插入可能完全失效或起反作用。
- **哪些超参数是 load-bearing**：论文正文可能只字未提、但官方代码里写死的关键超参（比如某个 dropout rate、某个初始化 scale、某个 warmup 步数），这些经常是"复现不出论文效果"的真正原因。

## 怎么确认

- 优先读官方开源代码的这个组件类/函数定义，逐行看它的 `forward`/`call` 方法，而不是只看论文里的公式和示意图。
- 论文附录、官方 issue、官方 README 的"训练细节"部分经常藏着上面这些 load-bearing 超参，逐一查一遍。
- 如果找不到官方代码，先在候选组件自己的原始场景（论文自己的数据集/任务）上跑通一次最小复现，确认理解无误，再往你的模型里接；也可以直接对照 [labmlai/annotated_deep_learning_paper_implementations](https://github.com/labmlai/annotated_deep_learning_paper_implementations) 里对应模块的逐行注释实现核对细节，见 `feature-and-data-reasonableness.md`。

## 契约优先来自机器可读元数据，不要硬编码

能拿到框架自带的形状/通道元数据时，直接用它推导契约，不要手写channel常量：`backbone.output_shape()`（detectron2的`ShapeSpec`）、`model.feature_info.channels()/.reduction()`（timm）、`stage_names`+`out_features/out_indices`（HF `BackboneMixin`）。`size_divisibility`/`padding_constraints` 这类输入约束也是契约的一部分，不是可以忽略的细节——横向连接遇到非整除输入会在运行时才报错。详见 `framework-placement-conventions.md`。

## 验证阶梯（照抄 HuggingFace "add a new model" 的验证法）

契约抠完、代码写完之后，在拿去跑效果之前先做逐层等价性验证：

1. CPU + `model.eval()`（关掉dropout）+ 硬编码整数输入 + 小/随机初始化的dummy checkpoint（单次前向应 <10s）。
2. **按固定顺序**逐层比对中间激活：input ids → word embeddings → 第一个block的输入 → 第一个block的输出 → 其后n-1个block的输出 → 整模型输出。
3. 权重加载时逐张量断言**shape与name都匹配**，并**打印所有未被消费的checkpoint权重**——这是抓"新层静默停留在随机初始化"最直接的方法。
4. 验收门：`torch.allclose(old, new, atol=1e-3)`。

**差异时的常见命名故障目录**：漏了一层（激活或残差连接）/ embedding未tie / 位置嵌入offset差1 / dropout仍开着。这一步跟 `integration-sanity-checks.md` 的Wiring Gate（P13探针）是同一件事在契约抠取阶段的前置版本。

**执行时用HF的`model_addition_debugger_context`，不要手写脚本**：核心原则#1警告的"从零写脚本是静默bug高发区"同样适用于验证脚本本身。两个模型实现各跑一次`model_addition_debugger_context(..., do_prune_layers=False, use_repr=False)`，diff两份输出的`*_SUMMARY.json`（含每个`module_path`的input/output shape/dtype/mean/std/min/max），第一个mean/std/min/max分开的`module_path`就是失败点，不用手工插print逐层对比。⚠️ 两个坑：**只包`forward()`（不是`.generate()`）且强制`torch.no_grad()`**，所以它只验证前向契约，梯度路径问题仍走`mechanistic-diagnosis.md`的P2/P3；torch-only，依赖外部kernel的模型可能部分未被trace到。

**借用宿主 pipeline 场景下，本文件要跑两次**：第一次针对宿主基类的swap契约（`borrow-existing-pipeline.md` 的P3末尾），第二次针对候选组件本身（P5）。
