# 可扩展的模块分类体系

分类不是贴标签，是在正交轴上各取一个值，保证新模块总有落点，也保证遇到 2027 年的新架构时有固定流程纳入，而不是每次重新发明。

## 分类卡（每个组件必填）

```
组件分类卡
A. SLOT（插槽）        : 它占据 framework-placement-conventions.md 里哪个插槽？
B. FAMILY（机制家族）  : 下面 B1-B17 的哪一族？（⚠️ 见 M8：族数已到17，B轴混着"算什么"和"扮演什么角色"两个问题，新增族前先读M8）
C. COMPUTATION（计算法): 参数组合(sparse/low-rank) / 输入组合(prompt/retrieval) / 函数组合(adapter) / 超网络(条件生成参数)
D. ROUTING+AGGREGATION : 路由={固定|学习硬路由|学习软路由}；聚合={参数|表示|输入|函数}
E. TRAINING SETTING    : 联合多任务 / 持续学习 / 冻结底座上的参数高效迁移 / 从零联合训练
+ 附加标签（多标签，非互斥）:
   - 复杂度机制: FP固定模式 / M全局记忆token / LP可学习模式 / LR低秩 / KR核方法 / RC递归 / DS下采样
   - 作用轴: channel / spatial / temporal / branch / token / head / expert
   - 兼容性标记: KV-cache兼容? 流式兼容? 依赖batch统计量? 需要因果mask? 改变下游channel数?
   - 训练态: 底座冻结/全量微调/分阶段解冻（哪一阶段解冻谁）——Flamingo/BLIP-2/LLaVA/RETRO-fit/Chinese-LLaMA 的差别主要在这里，不在层算什么，是 2022+ 移植类工作的主导设计变量
   - 零初始化残差门: 有/无（Flamingo tanh(α) α=0、DiT adaLN-Zero、LoRA B=0、ReZero 是同一招，跨 B3/B7/B8/B14 复现，属性不是族；置位后按 mechanistic-diagnosis.md 的"零初始化预期梯度模式"判读探针）
   - 可学 latent/query 库: 有/无（Perceiver 64 latents、Q-Former 32 queries、DETR object queries、soft prompt、ViT registers：作为输入token注入的可学参数张量，用来把输出长度与输入长度解耦，挂B14或B12并显式备注）
   - 血缘(仅元数据,不作分类轴): 它是谁的后代
```

## 模块家族表（B 轴取值）

每族给：编码什么归纳偏置 / 典型合法插入点 / 误用时的典型失败模式 / 必跑的诊断探针（见 `mechanistic-diagnosis.md` 的 P 编号）。

**B1 attention-like**：偏好性假设——任意两个位置可能相关，权重由数据学出。合法插入点：Transformer attention 子层（走 `AttentionInterface`）；CV 里作为 conv block 后/残差分支内的重加权模块。失败模式：①严格因果任务无因果 mask→数据泄漏；②注意力熵坍塌（⚠️ 已合成实验验证判别力本身很强——健康3.41 nats vs 坏初始化0.0115，297倍差距——但"先于loss发散"这条**只在快速发散场景实测过，领先量≤1步，某些LR下反而滞后，别当提前预警用，详见mechanistic-diagnosis.md P6**）；③无 skip 的纯 attention 按深度双指数收敛到 rank-1；④换实现未注册配对 mask→静默丢弃。探针：P6/P7/P2/P5。

**B2 normalization-like**：约束激活分布改善优化景观，按统计区域(batch/layer/instance/group)×归一化算子×表示恢复(affine)三要素分解。失败模式：①依赖 batch 统计量的在小 batch/序列/对比训练/对抗训练下失效。**已用合成实验验证：决定因素是每个统计量归约的元素数，不是batch size本身**——BN2d 在 bs=2、16×16特征图上每通道仍归约512个元素，BN1d在bs=2上只归约2个；同样bs=2，running_var/真实var的最大偏差实测1.15×(CNN) vs 8.44×(MLP)。🔴 **重标定running stats救不回来**：把bs=2训好的BN模型running stats清零、用大batch完美重估，只回收0.005~0.023的精度，而BN-vs-GN的差距是0.26~0.42——**>91%的损伤已经固化在训练出来的权重里**（重估统计量无法回收；具体固化机制未测量，不要归因成"梯度噪声"）。对策是换归一化算子（GN/LN），不是precise-BN。**失效是静默的**：全部小batch run的NaN step数为0，只掉精度。**必须按batch size分条件下结论**：同一组实验里BN在bs=64是最好的一档，bs=2才崩，且BN整条LR曲线都在GN之下（排除了"BN只是需要别的LR"这个反驳）。⚠️ 本族**不要**用P7/effective_rank当判据：实测方向不一致（一个架构上BN<GN符合预期，另一个架构上方向相反）。P4用std/absmax diff有效（`diff_stats`正确把紧邻归一化的上游层排到第一）。②与宿主已有同类归一化叠加相互抵消；③post-LN 无 warmup 不稳，pre-LN 稳但收敛后常略逊——这是真实权衡不是审美。探针：P4(std/absmax，不是zero_frac)/P5/P3。

**B3 gating-like（含 MoE/early-exit）**：计算量应随输入自适应。按粒度(sample/spatial/temporal/token/channel/expert)×决策机制(阈值/软门/硬门)分类。失败模式：①门坍塌到单一分支；②决策不可微导致梯度绕过；③**门被零初始化后永远学不动**（尤其配合零初始化残差时）。探针：P2/P3/P8。

**B4 positional-encoding-like**：序列/空间顺序本身携带信息。必填子schema：`<注入位点(input embedding/attention logits/attention bias/value向量), 相对vs绝对, 加性bias vs旋转, KV-cache兼容?>`。失败模式：绝对PE超训练长度不外推、换PE后KV cache语义失效。探针：P6/P9。

**B5 conv-like/局部算子**：限制性假设——局部性+平移**等变**性（不是不变性：单层卷积输出跟着输入一起平移，"同位置pattern都被同样识别"这个不变性效果要靠等变性质加下游池化/聚合才成立，不是卷积层单独保证的，见`architecture-placement-theory.md`）+规则网格采样。失败模式：①接到位置本身有强语义的特征上（表格第3列固定某物理量）→"把不同位置当成同一个pattern的平移出现"这个假设不成立；②接到稀疏/不规则采样数据（不同深度不同频率的测井曲线）不重采样→假设从一开始不成立。探针：P0/P4。

**B6 structured-token-mixer-like（结构化 token 混合：SSM/Mamba、FFT/长卷积、RNN、GNN 消息传递）**：序列/图相关性由状态递推、全局卷积或稀疏邻接结构表达。与 attention 同插槽，**继承插槽契约但不继承其 mask/KV-cache 语义**。**必填子schema：混合结构从哪来**——{位置索引(序列) | 输入自带的稀疏edge_index(图) | 无序集合}。**图消息传递（GCN/SAGE/GIN）落这里而不是新族**：MPNN 已把整类收敛成 `message/aggregate/update`（PyG `MessagePassing` 显式拆分三步），PyG 的 `Aggregation` 抽象基类把 mean/max/sum 统一为可换核。⚠️ **图的要求是置换不变性，与序列顺序假设正好相反**——沿用 attention/序列 mask 逻辑是本族最常见误用。GAT/GATv2/TransformerConv/HGTConv 这类学习型注意力聚合属 B1 不属这里。失败模式：直接套用 attention 的 mask 逻辑、双向实现用在因果任务上、状态初始化/离散化步长是 load-bearing 超参但论文不提、图场景对无序邻居用了有序操作破坏置换不变性；⑤（PyG专属，inspect型宿主的通病）`message()`/`aggregate()`/`update()`的形参名是硬契约，拼错或写`**kwargs`会让对应张量静默不参与计算——**具体机制不是"不报错不warning"这么简单，2026-08-29真实执行已修正**：拼错时`_collect`把该形参替换成`inspect._empty`类对象本身，往往表现成响亮但难懂的`TypeError`（缺失的形参名不会被打印出来，容易被误判成别的bug）；写`**kwargs`时inspect会把字面字符串`'kwargs'`当成一个合法形参名捕获（`_user_args == ['x_j', 'kwargs']`），不是"抓不到任何名字"。完整机制、判据和处置见`mechanistic-diagnosis.md`的S-13（唯一权威版本，这里不重复第二份）；具体宿主惯例见`pipeline-package-catalog.md`的G1行。探针：P2/P7/P9。

**B7 residual/skip-like**：恒等路径保证深层可优化。分类=`<跨度(global/local/recursive/dense), 合并算子(identity-add/gated-add/concat/learned-scaled), 是否门控>`。ReZero/LayerScale=learned-scaled local add；DenseNet=concat-dense；Highway=gated-local。失败模式：①随手削弱/重缩放/绕过残差→rank collapse 按深度显现（往Transformer block插模块最常见的结构性bug）；②concat型改变下游channel数，与add型**不可互换**；③zero-init的门/缩放系数配合未注册参数→永远为零。探针：P7（深度-秩曲线）/P0/P5。

**B8 adapter-like（LoRA/adapter/prefix/prompt）**：下游适配所需的参数变化是低秩/低维的，底座冻结。合法插入点由 PEFT 的选择器语言+架构默认表决定（见 `framework-placement-conventions.md`）。失败模式：①选择器regex选空（静默不匹配）；②任务头被误纳入target_modules而不是modules_to_save；③与底座共用同一LR（新模块严重欠训）；④自定义adapter层类型重载后，加载checkpoint时忘记重新注册自定义module class→dispatch静默回退到PEFT内置的`lora.Linear`，权重虽然在safetensors里但没被正确的层类消费。探针：P1（`targeted_module_names`+`print_trainable_parameters`）/P3。

**B9 capacity-like（宽FFN、激活函数替换）**：模型欠拟合的原因是容量或非线性表达力不足。失败模式：①在过拟合体制下加容量；②参数占比过低、且这一族本身假设的机制正是"多加点容量/非线性"时，小容量确实更难体现——但**参数占比低本身不是"不可能有效"的证据**：LoRA 官方论文报告 GPT-3 上可将可训练参数减少一万倍，效果仍能持平甚至超过全量微调，B8 adapter-like 整个家族的存在就是这条反例。参数占比只作容量背景参考，不得从"占比 <1%"直接跳到"这个模块不可能有用"的结论——要不要生效看的是 `mechanistic-diagnosis.md` 的 effective contribution（P9 activation patching / 训练后强制 force-bypass 的指标差异），不是参数计数。探针：P1（给背景，不给结论）/P4/P9。

**B10 loss-like/监督信号类**：目标函数应更贴近真实评估目标。契约：`forward(pred,target,weight=None,avg_factor=None,reduction_override=None)`+`@weighted_loss`装饰器→所有loss可直接互换。失败模式：权重量级与主loss差数量级、传logits还是概率搞混、输出维度错误使交叉熵恒为0完美掩盖bug。探针：P10（loss@init与理论值对照）。

**B11 data-like/预处理与增强类**：应当强加的不变性。失败模式：与现有增强破坏性叠加、与为旧架构调好的正则化互相掩盖新模块收益。探针：P11（干净val+增强val的鲁棒性带，掉<3%可接受，>10%说明缺一个可执行的不变性）。

**B12 adapter-shape/形状适配类**：唯一职责是让两个本不兼容的模块可连接（Merge/SpatialReduction/投影层），不编码任务偏置。**显式命名的原因**：CV框架常把它隐式塞进neck里，导致"加个投影层"这种引入额外自由参数的改动被当成无关紧要的胶水。显式命名后必须进 `controlled-comparison.md` 的单变量记账。**⚠️ 边界裁定：可学习的语义粗化不算glue**。DiffPool/SAGPooling/TopKPooling、Perceiver Resampler、Q-Former 的 32×768 瓶颈都改变 N→K，但它们是学出来的语义压缩，不是惰性 rearrange/reshape——按其主导机制归 B1/B6，只把"改变了下游形状"记为兼容性标记。真正的 B12 只包含无参数或纯投影的连接件（含 global_mean_pool 这类固定 readout）。

**B13 optimizer/schedule-like & training-loop-like**：改进的是优化过程而非函数族。**必须在本表里的原因**：最常被误当成"模块"混进config diff，破坏单变量。分类到这里=自动被判为nuisance或独立变量，不能与架构改动同轮引入。

**B14 conditioning/modulation-like（条件调制类）**：偏好性假设——一个旁路信号（timestep、类别、文本、风格、任意标量）应当**重参数化主路径的计算**，而不是被拼接进主路径当作又一个token。合法插入点：norm层的affine参数处（AdaGN/AdaLN/adaLN-Zero）、residual block内conv之间（FiLM/`time_emb_proj`）、block输入端作为in-context token、或以残差注入形式旁挂（ControlNet/T2I-Adapter）。**显式命名的原因**：同一语义在实现上会随"乘法发生在哪里"被拆散到B2/B3/B7——diffusers `ResnetBlock2D`的`"default"`是`h+temb`（看着像B7）、`"scale_shift"`是`h*(1+scale)+shift`（看着像B3）、`"ada_group"`把条件吸进norm（看着像B2）、DiT的adaLN-Zero从t+c回归γ/β/α（B2+B3）。**同一功能落五个族=分类切错了**，必须单列。失败模式：①条件嵌入与主流尺度失配（`std_cond/std_residual`差1-2个数量级）→条件要么无效要么淹没主路径；②zero-init的α/γ门未注册或未解锁→条件通路永远为零（与B3③同源）；③训练/推理条件分布不一致（训练时dropout掉条件，推理时忘了对应处理）→指标在验证集上正常、在真实使用中崩；④误当成B7只做`+temb`，丢掉scale分支从而丢掉DiT报告的收益。探针：P5（尺度匹配，必跑）/P8（把条件通路当门控看）/P3/P10。

**B15 external-state/non-parametric-memory-like（外部状态与非参记忆类）**：偏好性假设——前向所需的信息可以**不存在权重里**，而在推理时从一个可变的外部存储中检索出来。合法插入点：检索结果经cross-attention注入选定层（RETRO在第6/9/12层）、kNN分布与模型分布做门控插值（Memorizing Transformer）、KV cache/滑窗记忆。**显式命名的原因**：它的**层**部分完全落在B1+B3+B8，但**存储本身**（冻结retriever、推理时增删的非可微KV memory）是一个**有前向依赖、无可学权重、状态在推理期变化**的对象——B11是训练期预处理，B9指参数量，两者都不描述它。失败模式：①索引与checkpoint版本漂移（换了embedding模型没重建索引）→检索全是噪声但一切"正常运行"；②训练/推理检索池不一致造成的隐性泄漏（训练时检索池含验证样本）；③记忆淘汰策略把load-bearing条目挤掉，指标随序列长度缓慢退化；④检索命中率低时模型学会完全忽略该通路（退化成惰性组件）。探针：P23（检索/存储健康度）/P9（activation patching判因果载荷）/P11（怀疑尺子：检索池是否泄漏进验证集）。

**B16 inference/decoding-procedure-like（推理与解码过程类）**：改进的是**采样/解码过程**，不改权重也不改架构。典型：classifier-free guidance、diffusion sampler与schedule（DDIM/Euler/DPM++/UniPC）、temperature/top-p、beam search、speculative decoding。**必须在本表里的原因**：与B13同理且更隐蔽——B13覆盖训练侧，**采样侧此前无人认领**，而它对最终指标的影响常常大于被测模块本身。分类到这里=**自动判为nuisance变量或独立变量，不得与架构改动同轮引入**；做对照时采样器、guidance scale、步数、schedule必须在两个arm里逐字相同并写进报告的fixed超参列表（若不相同，则必须在两个arm内各自重调，同B13的nuisance规则）。失败模式：①换模块的同时换了sampler/guidance，收益全部无法归因；②CFG的无条件分支需要训练时以概率丢弃条件，模块改动破坏了该丢弃逻辑→推理端静默降级；③只在默认sampler下测，换sampler后收益消失（等价于seed方差问题，走S-7）。探针：无专属探针（与B13同）；强制走`controlled-comparison.md`的fixed超参记账；效果存疑时用P11。

**B17 tokenization/vocabulary-interface-like（离散接口与索引契约类）**：管的是**离散↔连续的边界**及其索引契约：tokenizer/merge table、词表扩充与新行初始化、tied `lm_head`、VQ codebook、patchify。它在其它轴上会被拆解（embedding矩阵变大→B9；只训embedding的stage-1→B8；merge table→B11），**但没有任何一族表达它真正的不变量**：checkpoint、`lm_head`每一行、KV cache、logit processor、评测harness必须共享同一个"整数→符号"映射。**这是本表里唯一一类不可热插拔的改动**。合法插入点：`resize_token_embeddings(new_num_tokens, mean_resizing=True)`（新行按旧embedding的均值与协方差采样，压低扩充前后next-token分布的KL）；新token一律追加到矩阵末尾以保证原词表embedding不受影响。失败模式：①改了tokenizer没改评测harness→指标不可比且不报错；②`lm_head`与embedding tied时只resize了一侧；③新行用默认随机初始化（不用mean_resizing）→初期loss尖峰、常被误诊为LR问题；④忘了`pad_to_multiple_of`导致Tensor Core掉档（性能问题伪装成架构问题）。探针：P1（新参数注册与规模）/P13（逐层等价性+打印所有未被消费的checkpoint权重，专抓resize后错位）/P10（loss@init与`-log(1/V_new)`理论值对照——词表变了理论值也要跟着变）。

## 元规则：如何归档一个全新模块（可扩展性的核心）

遇到不认识的新模块，按固定顺序判定，禁止跳步：

**M1 先填 A 轴（SLOT）**：它在宿主 forward 里替换、包裹、还是插在哪两个已有算子之间？命中已有插槽→M2；不命中→M5。

**M2 再填 B 轴，用"改变了什么不变量"判，不用名字判**：在这个插槽内它改变了稀疏模式/秩/核函数/先验/头结构/位置注入点/归一化统计区域或算子/容量/门控粒度/跳连拓扑或合并算子中的哪一个？命中→它是该族的新叶子，在本文件对应族下加一行（名字+改变的不变量+多标签tag），**不改任何轴**。90%的新模块停在这里。

**M3 若B轴无法单值命中，尝试多标签拆解**：新的高效机制几乎总能分解成已有tag的组合（如FP+M、KR+DS）。能分解→仍是新叶子只是多标签，只有引入全新的复杂度削减机制才配拥有新tag。

**M4 若仍不命中，走设计模式回退分类器**：它实例化了哪一个——Multi-X（同一元件并行重复，近似集成）/ Higher-order layer（用更富的算子替换linear+ReLU）/ Moving average（跨迭代平均参数或状态：momentum、EMA）/ Decompose（矩阵或卷积核分解、低秩）/ Weighing function（用参数化函数加权输入而非朴素聚合=信息门控）。命中一个→在最接近的族下新建子分支；五个都不命中→M5。

**M5 新建插槽/新建轴（最高成本，需显式声明）**：必须同时满足——(a)不属于任何已有ROOT角色；(b)M2-M4全不命中；(c)能写出自己的插槽契约。产出三件套，缺一不可：① `framework-placement-conventions.md` 新增一行家族/插槽含契约与一行assert；② 本文件新增一族含"偏置/合法插入点/失败模式/必跑探针"四栏；③ `mechanistic-diagnosis.md` 为这族至少绑定一个已有探针或新增一个探针并写清读到什么数字意味着什么。**没有第三条就不算归档完成**——不能诊断的分类是死分类。

**M6 血缘只做元数据**："它是X的后代"记在血缘字段，永远不作为分类轴（按外形/谱系分类不提供插入点、兼容性规则和失败模式，不可用作骨架）。

**M7 定期反向校验**：每归档5个新叶子，检查是否有某族叶子数畸多且失败模式高度雷同→说明该族该拆分子轴。这是唯一允许"重构分类体系"的触发条件。

**M8 双轴警戒线**：本表混着两个问题——"它算什么"（B1/B2/B4/B5/B6/B14 计算轴）与"它扮演什么角色"（B8/B9/B10/B11/B12/B13/B15/B16/B17 角色轴）。**族数超过约17之前必须拆成两轴、每个模块各取一个tag**，否则会继续出现"LoRA同时是三族""AdaLN落三个地方""CFG无处可落"这类症状。新增族之前先自问：这是计算轴还是角色轴的空洞？如果是同一功能被实现细节拆散（B14的情形），那是切错而不是缺族。当前已到17族，这条警戒线已经触发，下一次要新增族之前，先把B轴拆成"计算轴+角色轴"两个独立字段，不要继续加B18。

## 分类的直接用途

分类卡填完后，agent 应从对应族的条目里**直接读出**三样（这是"读表推导"，不是脚本自动生成——当前是自然语言表格，还没有结构化成可被程序解析的数据文件）：① **合法插入点候选集**（来自A轴+插槽表）——超出这个集合的放置必须写理由；② **必查兼容性清单**（来自B轴的失败模式+兼容性标记）；③ **必跑探针清单**——这三样直接喂给 S5/S8/S10。（已知待办：把这张表结构化成 `assets/module-family-registry.yaml` 会让这一步真正可脚本化，目前尚未做）
