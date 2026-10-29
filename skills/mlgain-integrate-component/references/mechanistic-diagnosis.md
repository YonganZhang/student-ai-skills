# 机理感知诊断决策树（Perception Interface）

**本文件是整个 skill 的价值所在。** 2026-08-29 三轮独立调研确认：GitHub 上没有一个现成工具/skill 完整覆盖"给 AI agent 一套诊断神经网络集成失败的感知力接口"，最接近的（FastVideo 的 `add-model-08-trace`、`torchtest`、Cockpit、TorchLens）都只覆盖其中一部分。本文件是本地综合设计，标注了每处引用的真实来源。

## 强制条款（最高优先级）

> **当集成后的结果不及预期（无提升/变差/训练不稳），禁止直接给原因。必须先按下面的分诊表跑至少一个探针，拿到数字，再解释。**
>
> **无效回答黑名单**（出现即视为未完成任务，必须回去跑探针）："可能是数据问题" / "可能是模型不适合这个任务" / "也许需要调超参" / "这个模块可能不适用于你的场景" / "可能是过拟合"——**只要没有附带一个具体测量值和产生它的代码**。
>
> **合格回答的格式（三段式，缺一不可）**：`【测量】<探针编号>：<具体数字，含baseline对照>` → `【读数含义】<该数字对应的机理判定>` → `【下一步】<由该判定唯一确定的动作>`
>
> 例：`【测量】P3：新模块lora_A参数grad_norm=3.1e-9，同层q_proj.weight grad_norm=4.7e-3（相差6个数量级）` → `【读数含义】新模块几乎不在梯度路径上` → `【下一步】跑P2确认是detach/no_grad/未注册中的哪一种`。

## 前瞻纪律：不要只做反应式诊断（来自生态检索，吸收自Agent-Loop-Skills的ml-autoresearch）

上面的分诊表是**症状出现之后**才查表——三条前瞻性动作把纪律往前挪：

1. **跑之前先写探针交付表**：`脚本 | 输出文件 | 它回答什么问题 | 改动有效时应该看到什么 | 无效时应该看到什么`。这是把已经施加于S0期望声明的纪律，也施加到探针本身——不是先跑完再想"这个数字说明了什么"。
2. **没写出文件的分析等于没做**：跑完一次分析，`ls` 检查预期产出的文件是否真的落盘了。这是对P11"没打印过的等于没看过"的操作化，给它一个硬清单门禁，不是一句自觉遵守的口号。
3. **前瞻性埋点**：每次分析完，问一句"我当时希望记录了什么"，并明确允许"加一个新埋点"本身就是一次合法的迭代——这条跟anti-overcaution铁律相容：加埋点是廉价动作，不是新增一道否决权。

## 探针库（按成本递增排序，永远先跑便宜的）

| 编号 | 探针 | 怎么做 | 成本 |
|---|---|---|---|
| **P0** | 结构真相：模块在不在前向路径上 | `torchinfo.summary(model, input_size=..., col_names=['input_size','output_size','num_params','trainable'])`，baseline与改动后各一份做diff；Netron 看导出图确认新模块不是悬空分支；`torchviz.make_dot(loss, params=dict(model.named_parameters()))` 看真实autograd图 | 秒级 |
| **P1** | 注册与规模：参数存在吗、可训练吗、占比多少 ⚠️ 实测踩过的坑，见下 | `new = set(dict(model.named_parameters())) - set(dict(base.named_parameters())); assert new`（新模块参数未注册的典型原因：存于普通list/dict而非`nn.ModuleList/ModuleDict`）；检查optimizer参数总量与模型可训练参数总量是否一致（优化器是否早于模块构造）；PEFT场景查`peft_model.targeted_module_names`+`print_trainable_parameters()` | 秒级 |
| **P2** | 梯度可达性：模块在不在反向图里 | `loss.backward()`后`[n for n,p in model.named_parameters() if p.grad is None]`；配合`register_full_backward_hook`观察是否触发。区分三因：`.detach()`/`torch.no_grad()`/参数未注册 | 秒级 |
| **P3** | 学习强度：梯度范数+update:weight比 ⚠️ AMP下必须先`scaler.unscale_(optimizer)`再读`.grad`；分片后端下必须经P16取数，否则读到的是分片、数字合法但无意义 | 快速代理：`scripts/probe_hooks.py`的`sgd_update_proxy()`（`lr*grad`，对Adam等自适应优化器会失真，仅作相对信号）；要真实数字用同文件的`snapshot_params()`+`measure_real_update()`（optimizer.step()前后直接测`‖p_after-p_before‖/‖p_before‖`，包含优化器真实预条件）。**两个函数对`weight_norm==0`（ReZero alpha、LoRA B、零初始化conv）都返回`inf`而不是除以一个1e-12地板**——实测这个地板会对健康的零初始化分支报出约7.7e11，读起来像灾难性爆炸，实际是最健康的起始状态。**按深度排层用`scripts/probe_hooks.py`的`diff_stats()`（默认无地板，只在两侧都是精确0时报inf；不要传老版本那种固定epsilon）**：18层无norm无残差sigmoid MLP实测真实梯度低到1e-18，旧的1e-12地板会把7层压到同一个值并**反转排序**（真正最差的输入层被排到7/8名）。判据：**update:weight ≈ 1e-3** 只是起点参考，不是跨模型/优化器/任务通用的硬阈值，显著低/高时先看是不是本任务本优化器本来就该这样 | 训练时低开销 |
| **P4** | 激活健康度：死单元/饱和/分布 | 对激活模块挂前向hook：`(o==0).float().mean(), o.std(), o.mean(), o.abs().max()`。ReLU看零占比，有界激活看饱和占比。**判据是baseline与改动后的diff，不是绝对值** | 单batch |
| **P5** | 尺度匹配：新模块输出vs它注入的流 | 打印新模块输出与它相加/拼接的residual stream的mean/std/absmax比值，`std_new/std_residual`偏离1达1-2个数量级即为问题 | 单batch |
| **P6** | 注意力熵坍塌 | `Ent(A_i)=-Σ A_ij log A_ij` 按 query 行算，**对每个 head 各自算完熵再求均值**，与 loss 并列作训练健康指标。用 `scripts/probe_hooks.py` 的 `attention_entropy()`（已内置 eps 防护）。需 `attn_implementation="eager"`（已实测：`F.scaled_dot_product_attention` 只返回 Tensor，`nn.MultiheadAttention(need_weights=False)` 拿到的 hook 输出是 None）。🔴 **实现必须加 eps**：字面写法 `-(A*A.log()).sum(-1)` 在 softmax 下溢到精确 0 时返回 NaN，实测 fp32 下 qkv init std=2.0 时 1024/1024 个 query 行全 NaN，**恰好在这个探针要抓的完全坍塌场景上失效**；fp16 下溢更早。🔴 **不要用 `need_weights=True` 的默认返回**：`nn.MultiheadAttention` 默认 `average_attn_weights=True`，先平均再算熵 ≠ 先算熵再平均（Jensen上界）。实测随机初始化虚高 +0.086 nats(+2.6%)，最坏情况下几个各自完全坍塌到不同token的head，真实per-head熵为0却读成log(L)——**完全坍塌被完全掩盖**。必须传 `average_attn_weights=False`。**已合成实验验证**（4 head、L=8 MHSA）：健康默认初始化熵≈log(L)（如L=8时2.08），坏初始化（qkv std=2.0）降到接近0，**297倍**量级的分离。⚠️ **校准提醒（与P7同类）**：低熵不等于病态，健康收敛训练中熵也会显著下降（实测某健康run熵比初值低51%，loss同时改善27倍），只读baseline vs改动后的相对差，不要用绝对阈值或"比初值低多少%"当判据 | 训练时低开销 |
| **P7** | 秩坍塌/表示坍塌 ⚠️ 分片后端下必须经P16，未接入时直接拒跑不许输出数字 | 逐层dump hidden states，`torch.linalg.svdvals`求谱，画effective rank vs depth，baseline与改动后叠图。改动后曲线在某层开始衰减而baseline平坦→残差路径在那一层被破坏。RankMe公式见`scripts/probe_hooks.py`的`effective_rank()`（label-free，对全零/退化输入已做NaN防护），只作两组对比信号不作绝对阈值。**已用合成实验验证**（24层MLP block，无残差 vs 有残差）：无残差在第6层左右就坍塌到 rank≈1.0，有残差的同深度仍有 rank≈2.4，差异非常显著，这个探针的理论声称是真实可观测的。**校准提醒**：即使有残差连接，rank 也会随深度缓慢下降（不是完全平坦），判读时看的是"baseline vs 改动后"的相对差异，不要预期健康网络的曲线是一条水平线 | 单~中等 |
| **P8** | 门控/路由健康度 | 门输出直方图、分支占用比例、门熵；MoE看expert负载分布。坍塌到单分支即诊断成立 | 单batch |
| **P9** | 因果归因：模块到底载不载荷 | Captum `LayerConductance`（新模块输出层近零conductance而并行/残差路径吃掉全部归因=模型学会绕过它）；Transformer专用TransformerLens activation patching（把好run的新模块输出patch进坏run，指标恢复=因果载荷，不恢复=惰性组件，**loss曲线说什么都不算数**）；非LM架构用NNsight（`with model.trace(x): h=model.layers[5].mlp.output.save()`） | 中~高 |
| **P10** | 初始状态自检（⚠️ 两条判据的适用范围不同，见下方说明，不要当成同时成立的两个断言）| loss@init是否等于理论值（分类`-log(1/n_classes)`）；见"两条判据"| 秒级 |
| **P11** | 测量层可信度（怀疑尺子）| 输出空间delta：baseline与新模型在同一固定样本上的输出差异统计，**自比较对照：模型与自身比delta必须≈0**；验证集结构审计（时序取连续最新块，分组数据按组切）；trial variance：baseline重跑N个seed的波动带 | 低~中 |
| **P12** | NaN定位三级阶梯（必须按序）| (1)`clip_grad_norm_`返回值的时间序列→找到范数尖刺的那一步；(1.5，HF-Trainer模型可用的第2级替代)`TrainingArguments(debug="underflow_overflow")`/`DebugUnderflowOverflow(model)`——把"逐层grad-norm hook→找到哪一层"压缩成一个flag，且额外给出量级余量（能看到值已到6.27e4、逼近fp16上限6.4e4，裸grad-norm hook只告诉你炸了）；(2)逐层grad-norm hook→找到哪一层；(3)仅在那一个可复现batch上`with torch.autograd.detect_anomaly():`→拿到制造非有限值的前向那一行。**不要在整轮训练上直接开anomaly**，太慢且噪声大。**发散可复现到已知步时**，另一个通用技巧：dump最后一个健康batch与发散batch的逐模块absmax表并对diff（`probe_hooks.py`的instrument-then-diff模式**沿时间轴**而不是baseline-vs-candidate轴的应用），配合P19的fp16 caveat——scaler把溢出吞成日志行时，这条时间轴diff常常是唯一可见处 | 递增 |
| **P13** | 逐层等价性阶梯（照抄HF add-new-model验证法）⚠️ 分片后端下必须经P16| CPU+`model.eval()`+硬编码整数输入+小dummy checkpoint。按固定顺序比对中间激活：input→word embeddings→第一个block输入→第一个block输出→其后n-1个block输出→整模型输出。验收门`torch.allclose(atol=1e-3)`。权重加载时逐张量断言shape和name都匹配，打印所有未被消费的checkpoint权重（抓"新层静默停留在随机初始化"）| 中 |

**以下 P14-P22 是分布式训练（DDP/FSDP/ZeRO）专属探针，只在 scale-up 之前需要**——单卡场景 P0-P13 已经足够，不要把分布式探针当成常规路径的强制项。核心原因：P3/P7/P13 建立在`p.grad`/`named_parameters`/hook上，这些在分片后端（FSDP FULL_SHARD、DeepSpeed ZeRO-3）下不是失效，而是**静默返回错误但看似合法的数字**（在1/8个`FlatParameter`分片上算出的梯度范数/rank collapse结论，比没有探针更危险）。v1 范围限定 **DDP+FSDP+ZeRO**；**TP/PP（Megatron式）显式不支持**，半支持比不支持更危险。

| **P14** | 跨rank参数发散（性价比最高，先跑这个）| 训练N步后对每个参数`all_gather`一个指纹（fp64的sum+L2，或字节哈希），断言各rank逐位/近逐位相等，按参数名报出第一个发散的。第1步和第N步各跑一次：第1步发散=广播/初始化问题，第N步发散=梯度没被allreduce | 低 |
| **P15** | Reducer注册集审计（DDP专用，抓最恶劣的静默desync）| DDP在构造时冻结梯度同步注册集：所有参数必须在构造时已注册，之后不得增删，构造后再改`requires_grad`不起作用。做法：把DDP构造时实际挂了autograd hook的参数集，与当前`{n for n,p in ddp.module.named_parameters() if p.requires_grad}`求差集，在任何freeze/unfreeze阶段切换后重跑，非空即fail loud。三种现实触发：懒构造参数、wrap后新增参数、分阶段解冻。⚠️ 与"有参数没收到梯度"的响亮报错区分开：后者PyTorch已有一等诊断（设`TORCH_DISTRIBUTED_DEBUG=INFO`会直接打印），别重造 | 秒级 |
| **P16** | 分片感知的full param/grad取数层（**是P3/P7/P13的前置依赖，不是独立探针**）| 一个`full_param_and_grad(module,name)`按后端分派：单卡/DDP直接`.grad`；FSDP用`FSDP.summon_full_params(mod, with_grads=True)`（要求`use_orig_params=True`）；ZeRO-3用`safe_get_full_grad(p)`/`GatheredParameters`。🔴 **必须全rank进入**（这些都是collective，写在`if rank==0`里会挂死整个job），库要断言自己不在rank guard内，并用`dist.monitored_barrier()`包起来让错误报出罪魁rank而不是永久hang。FSDP下梯度裁剪必须走`FSDP.clip_grad_norm_`。**未接入P16时，P3/P7/P13在分片后端下必须直接拒跑并报错，不许输出数字——这条不再只是文档要求**：`scripts/probe_hooks.py`的`sgd_update_proxy()`/`snapshot_params()`/`measure_real_update()`/`assert_gradients_reach()`/`assert_zero_init_unlocked()`现在都会先调用`detect_sharded_backend()`，检测到FSDP1/DTensor(FSDP2)/DeepSpeed包裹时直接`RuntimeError`拒绝返回数字，而不是只在docstring里警告——2026-08-29经独立复核发现这一条此前只是散文警告、没有任何代码真正拦截，已修复并用一个真实（isinstance可判定）的FSDP包裹模型验证过拒绝行为。**但检测是尽力而为，不是完备的**：`detect_sharded_backend()`能看到"某个祖先module是FSDP实例"，看不到FSDP1在`use_orig_params=True`下把参数`.data`替换成分片buffer视图这种没有独立类型可判的情况——探针没报错不等于确认没有分片，仍然要按P16的full_param_and_grad手动gather，不要把"没报错"读成"安全"| 中 |
| **P17** | Buffer被覆盖检测 | DDP每次迭代都把buffer从rank0广播到所有rank。新模块若把状态放`register_buffer`（VQ codebook、EMA统计、路由计数），world_size=8时7/8的更新被静默丢弃——模块仍"能用"，只是用1/N的数据学。做法：枚举新模块的buffer，一次迭代前后各`all_gather`，对"广播前各rank不一致且由rank0主导"的buffer告警 | 低 |
| **P18** | Rank参与度直方图（P8门控健康度的分布式延伸）| 每步`all_gather`一个0/1标志：新模块每个参数本步是否收到梯度。报参与比例。`find_unused_parameters=True`只是避免hang，梯度仍按全world_size求均值，条件执行的模块因此可能被静默缩小学习率。⚠️低置信（推断非文档结论，落进探针输出文案前先用双rank实验实测）：另`static_graph=True`对条件/数据相关执行的新模块是明确危险设置 | 低 |
| **P19** | Loss-scale/跳步会计（fp16下P12的替身）| 追踪`scaler.get_scale()`与跳过的optimizer step比例，按"新模块引入的那一步"归因。引入后跳步率上升=模块在fp16下溢出——**P12看不见，因为scaler把NaN吞成了日志行而不是抛出**。🔴 同时强制：P3读`.grad`之前必须`scaler.unscale_(optimizer)`，否则报的梯度范数被动态loss scale放大，阈值全部失真 | 低 |
| **P20** | Reduce-dtype敏感性（分布式独有的精度病）| FSDP `MixedPrecision.reduce_dtype`未指定时继承`param_dtype`，即梯度allreduce发生在bf16——单卡没有reduction，结构上不可能复现。做法：同一步分别用`reduce_dtype=bf16`与`fp32`算一次梯度归约并报相对误差；显著差异→对该模块钉`reduce_dtype=torch.float32` | 中 |
| **P21** | FSDP参数视图缓存检查 | FSDP每次迭代用新的Tensor视图替换被管理参数；模块若在`__init__`里缓存了参数引用（`self.w=self.weight`）而不是每次从self取，就看不到新视图，**autograd静默失效——单卡完美**。做法：断言forward内观察到的`id(param)`跨迭代变化 | 秒级 |
| **P22** | N卡vs1卡梯度等价性（分布式组的总验收，P13的延伸）| 同seed同数据顺序：1 rank×batch B 与 2 ranks×batch B/2 各跑一步，经P16取全量梯度逐张量比对。**这是"模块在规模下接对了"最有说服力的单一证据** | 高（两次跑）|
| **P23** | 检索/外部存储健康度（B15专属，非分布式）| 索引与当前checkpoint的embedding模型是否同源（记录并断言索引构建时的模型SHA）；抽样打印真实检索到的K个邻居内容与距离分布——**没打印过的等于没看过**；训练检索池与验证/测试样本的交集必须为空（泄漏自检）。读数：邻居距离分布与随机基线不可区分→该通路是噪声源不是信息源 | 低~中 |

**🔴 分布式执行模型（P14-P22的前提，不遵守会挂死整个job）**：`summon_full_params`、`GatheredParameters`、`safe_get_full_grad`全是collective，**必须所有rank同时进入**——最自然的写法`if rank==0: inspect()`会让整个作业永久hang。探针库必须：①断言自己不在rank guard内；②用`dist.monitored_barrier()`包裹，把hang变成指名罪魁rank的报错。**免费的一招**：诊断模式下设`TORCH_CPP_LOG_LEVEL=INFO TORCH_DISTRIBUTED_DEBUG=DETAIL`，它对每个集合通信做跨rank一致性与shape校验并自动插monitored_barrier，把一类静默hang变成有名字的报错；很慢，只放诊断模式不做默认。**分诊入口补一条**：单卡P0-P13全绿、一上多卡就退化/不收敛→直接进P14→P15/P17→P18→P19→P22，不要重跑单卡探针。

**P10 的两条判据，适用范围不同，不要同时套用**：
- **在 S1 hard bypass / S2 enabled no-op 配置下**（见 `function-preserving-socket-protocol.md`）：`torch.allclose(base_out, new_out, atol=1e-3)` 必须成立——这时候就是要验证"零增益=完全等价于baseline"。
- **在 S4 真实候选模块、且门控/scale 已训练解锁之后**（或本来就是 REPLACE 模式）：`model(x)` 与 baseline 在固定输入上必须数值不同——一个前向输出永远和 baseline 逐位相同的"模块"，无论训练多久都不可能改变任何指标，这时候"完全相同"才是异常信号。
两条判据分别对应"这一刻该不该有差异"，不是同一时刻的两个矛盾要求。

**工具选择备注（防止走弯路）**：TorchExplorer只在training模式记录，in-place op会破坏backward hook（需`disable_inplace=True`），对许多transformer架构不工作——遇到transformer直接退回手写hook/TransformerLens/NNsight。`wandb.watch`现行默认是`log='gradients', log_freq=1000`（不是常见的100），做诊断跑要显式设`log='all', log_freq=25~50`。Captum Insights在v0.8.0后已停止维护。`register_backward_hook`已废弃，一律用`register_full_backward_hook`。

**torch.compile/graph capture（已实测）**：探针在compile下**不失效，但注册顺序错了会静默失效**。唯一安全顺序是**先注册hook，再torch.compile，再跑**——这样hook观测到的是原始module边界张量，数值与eager逐位相同（2026-08-29真实2卡NCCL重测：实测差异**恰好0.0**，比早前报的约7e-7更干净，远小于P13的`atol=1e-3`，不要因为compile就收紧或不信P13）。🔴 **反过来（模型已compile且已被调用过一次，再挂hook）：hook一次都不触发**，`instrument()`返回空dict，`diff_stats()`会拒绝空输入而不是静默返回`[]`（已在`scripts/probe_hooks.py`里加了前置门，默认直接`RuntimeError`，除非显式传`allow_compiled=True`）。**2026-08-29补充确认——这个门本身有个已修的盲区**：早期版本只检查顶层`hasattr(model,"_orig_mod")`，一个`m.blocks[1]=torch.compile(m.blocks[1])`这种**子模块级**compile会绕过顶层检查，返回一个非空但不完整的stats dict（实测11/13个模块），`diff_stats()`的空输入`ValueError`也拦不住这种"非空但缺失"的情况——`instrument()`现在遍历`named_modules()`逐个检查，已修复并验证（子模块compile报`(True,'blocks.1')`、整模型compile报`(True,'<root>')`、干净模型报`(False,None)`）。根因是`torch._dynamo.config.skip_nnmodule_hook_guards`默认`True`（省guard执行时间，代价是编译后改hook dict不会被发现），且失败是**间歇性**的：喂新shape触发recompile后hook又会开始触发。三条补救：①在compile之前注册；②`torch._dynamo.reset()`后设`skip_nnmodule_hook_guards=False`（有guard开销）；③直接探`model._orig_mod`的eager版本。⚠️ 探针里的`.item()`/`float()`会切断dynamo图（实测1图→3图/2 breaks），**挂探针跑的不是production那张融合图**，这是测量保真度问题不只是速度问题。

**`fullgraph=True`下hook是被拒还是被静默丢弃——2026-08-29真实8×RTX-5080/2-rank NCCL实测回答，原来的"二选一"提法本身就问错了**：不是非此即彼，而是按hook类型+注册顺序分叉——backward hook注册在compile**之前**会被**响亮拒绝**（不静默）；forward hook注册在compile之前**正常工作**且与eager**逐位相同**（0.0 diff，覆盖output和grad两侧）；**任何hook只要在compile之后注册**，即使`fullgraph=True`也会被**静默丢弃**，这条和非fullgraph模式下的行为完全一致，`fullgraph`不额外提供任何保护。

**torch.compile×FSDP1交互（2026-08-29真实2卡NCCL实测）**：原本"这条交互是否安全"的担心**被推翻**——P16的`full_param_and_grad`在compile+FSDP1下完全正确（gather到的25220与unsharded参考值一致；查看sharded视图得到预期的12610），compile guard**没有**被FSDP屏蔽掉，但这**完全依赖**`instrument()`那句`hasattr(model, "_orig_mod")`的兜底分支——FSDP的`__getattr__`会把属性访问转发给被包裹的原始module，所以`isinstance()`判不出来但`hasattr()`能判出来，**这个兜底分支不能被"简化"成只用isinstance**。另外发现两条新的硬约束（都是响亮失败，不是静默）：FSDP1配`fullgraph=True`即使零hook也会崩（`Unsupported: setattr() on Tensor.requires_grad`）；在FSDP包裹**之前**逐层单独compile会硬崩（`RuntimeError('b must be 2D')`）。**还发现一条新的静默盲区，不在原来列出的待验证清单里**：`summon_full_params`context**内部**和**外部**拿到的参数FQN是**完全不相交**的两套名字——P16文档写的`full_param_and_grad(module, name)`签名，如果调用方在context外部先捕获了`name`再传进去用，会失败，必须在context内部重新按需取名。

CUDA graphs（手写`torch.cuda.CUDAGraph`，不是`torch.compile(mode="reduce-overhead")`）——**2026-08-29真实执行发现原判据是反的，这是本文件此前唯一一处教"安全"实则危险的地方，已删除**：原文说"把输出detach存下来事后算会被PyTorch直接`RuntimeError`拦住，不需要额外防护"，**这句话只对`torch.compile(mode="reduce-overhead")`成立，对手写`CUDAGraph.capture_begin/capture_end`+`replay()`是错的、而且是危险方向的错**——手写capture下，hook只在capture那一刻触发一次，之后每次`replay()`都不会再触发hook，若hook把结果存到设备端张量又没有同步读取，会读到capture时刻的同一块显存（`data_ptr`相同），三次"逐步快照"读出`[-0.2025, -0.2025, -0.2025]`而真实eager应为`[0.0619, -0.0703, -0.2025]`——数值本身完全合法、无NaN，任何数值健康检查都抓不到，是最危险的"看起来在测量但其实没在测量"的情形。已验证在torch 2.7.1/2.11.0/2.12.1/2.13.0四个版本上行为一致。正确做法见上方S-17：用`torch.cuda.is_current_stream_capturing()`守卫，`instrument()`已内置。`torch.cuda.make_graphed_callables`不是安全替代——它的hook guard只查顶层module，子模块上的hook能绕过去。

**⚠️ P3/深度梯度曲线已用合成实验验证，含一条重要校准**：18层MLP、无norm无残差、两网权重逐张量相同只换激活。sigmoid每层损失显著衰减，18层跨15个数量级，输入层梯度低到1e-17级别；ReLU衰减轻得多。**校准提醒（重要，容易踩）**：ReLU在xavier初始化下深度曲线基本平坦，但在**PyTorch默认`nn.Linear`初始化（kaiming_uniform）下ReLU也会指数衰减**，只是比sigmoid轻。所以"P3深度曲线在衰减"本身不构成"激活/新模块有问题"的判据——初始化方式是混淆变量，必须与同一初始化下的baseline叠图比较，不能凭一条曲线的绝对形状下结论。

**⚠️ P1 实测踩过的坑（合成实验验证过，不是猜的）**：`assert new`这条 diff 只有在 `base`/`candidate` 是**同一个架构、只差被测组件**时才可靠。如果拿两个结构不同的模型比（比如 base 是裸 `nn.Sequential`，candidate 的第一层用了不同的属性名），diff 出来的"新参数"会混进这些无关的命名差异，可能把真正缺注册的组件淹没在噪声里，也可能把无关层误判成"新组件"。跑这条探针前先确认两个模型除了被测组件之外逐层同构。

**⚠️ 零初始化技术的预期梯度模式（必须先知道，否则会把正常技术误判成接线错误）**：ReZero的`alpha=0`时，首步核心分支参数`F`的梯度确实为0，这是设计如此，不是bug——alpha自己先有梯度，解锁之后F的参数才会动。LoRA零初始化（`A`随机、`B=0`）首步`grad(B)`可非0、`grad(A)`可为0。ControlNet的zero conv首步projection有梯度，上游分支可为0。**判断"这个模块是否被正确接入"，不能只查"梯度是否为0"，要按初始化机制查预期梯度模式，做2-3个optimizer step后再检查解锁后分支梯度是否符合预期。** 详见 `residual-gating-safe-integration.md`。

## 症状 → 探针 → 读数含义 → 动作（分诊表）

**入口规则**：任何"没达到预期"，一律先跑 **P0→P1→P10→P2** 这四个秒级探针（合称 Wiring Gate），再看下表——最常见的原因是"模块根本没接进去"，零成本可证伪。

| # | 症状 | 查什么 | 读数→机理判定 | 下一步动作 |
|---|---|---|---|---|
| S-1 | loss完全不动/指标与baseline逐位相同 | P1→P2→P10 | 新参数不在`named_parameters()`（存于list/dict而非ModuleList）；或`p.grad is None`（detach/no_grad）；或optimizer参数量对不上（optimizer在模块构造前就建好）；或`model(x)`与baseline数值完全相同（前向没被调用）| 修注册/图连接后重跑Wiring Gate，此前不许提出任何"模块是否有效"的假设 |
| S-2 | 能训但新模块像没参与：指标≈baseline | P3→P9 | grad_norm比同层低3+数量级→不在梯度路径有效部分（零初始化门/LR组错配）；grad正常但`Δ‖p‖/‖p‖≈0`→在学但相对更新可忽略→LR问题不是架构问题；`LayerConductance≈0`而残差路径吃掉归因→模型学会绕过它 | 给新模块单独param group调LR/扩大规模或改放置/改门初始化（非零）/换插槽 |
| S-3 | 加模块后指标明显变差、训练不稳 | P5→P4→P7→P6 | 输出std比注入流大/小1-2数量级→尺度失配；下游激活死比例/饱和比例暴涨→新模块把下游推进死区（**P4读zero_frac前先跑`assert_activation_modules_visible()`，激活写成`F.relu`而非`nn.ReLU`时zero_frac恒读0.0，会被误判"健康"**）；深度-秩曲线插入层后开始衰减而baseline平坦→残差路径被削弱/绕过（token表示趋同）；某层注意力熵断崖→熵坍塌。⚠️ **不要当提前预警用**：在LR过大导致的快速发散场景实测（4组配置全部在5步内炸），熵领先loss最多1步，某些LR下反而滞后，该实验分辨率无法回答正常LR长训练下熵是否缓慢先行，只把它当同步指标用 | 加learned scale（LayerScale/ReZero）或输出端归一化；换激活/修初始化/降LR；恢复恒等残差路径；σReparam或降LR加warmup |
| S-4 | 训练发散/NaN | P12（严格按序）| 定位步→定位层→定位前向那一行。典型命中：除以近零、log/sqrt非正数、自定义autograd.Function的backward不稳、fp16/bf16溢出 | 按定位到的行修（加eps、换rsqrt、升dtype、改scaling）|
| S-5 | 一个batch都过拟合不了 | P10 | 硬伤信号不是"模块不适合"：误差上升=符号反了；误差爆炸=数值问题或LR太高；误差震荡=LR太高或label被打乱；误差平台=LR太低或容量不足 | 硬伤修完再谈效果 |
| S-6 | 模块"看起来在动"但指标不涨 | P9→P11 | activation patching指标恢复=因果载荷、不恢复=惰性组件（loss曲线怎么好看都不算数）；两条曲线重合=模块改了参数但没改计算 | 惰性→改门控/初始化/放置；若确认在起作用→转P11怀疑尺子 |
| S-7 | 提升幅度小、换个seed就没了 | P11→controlled-comparison.md | baseline重跑N个seed得trial variance波动带；delta是否超出重训方差 | 未超出→结论是"不可区分"不是"有提升" |
| S-8 | 换attention实现/加mask模块后长序列或padding异常 | P0→P6→配对注册表检查 | 注册了`AttentionInterface`却没同名注册`AttentionMaskInterface`→attention_mask被静默传入None | 补配对注册；诊断脚本单独用`attn_implementation="eager"`加载 |
| S-9 | PEFT/adapter类：可训练参数为0或远小于预期 | P1（PEFT版）| `targeted_module_names`为空→选择器regex选空；任务头出现在target_modules而非modules_to_save | 对照`TRANSFORMERS_MODELS_TO_LORA_TARGET_MODULES_MAPPING`校正 |
| S-10 | 训练集好、验证/线上不好（或反过来）| P11→误差分解 | 持有两个验证集（训练分布+测试分布），拆开`test error=irreducible+bias+variance+distribution shift+validation overfitting` | 欠拟合分支：加容量→减正则→误差分析→换架构；过拟合分支：加数据→正则→调参→误差分析 |
| S-11 | 表示"变简单了"：loss平但下游探针变差 | P7（RankMe）| effective rank低于baseline→新模块把head需要的信息压掉了——与容量/LR问题完全不同的第三类病因 | 加宽/加正则/改放置，不要靠调LR |
| S-12 | 组件在别人仓库有效、这里无效，以上探针全绿 | P13→契约复核 | 逐层等价性阶梯：零增益配置下`allclose`不过=接线错不是理论不成立；打印未消费的checkpoint权重=抓静默停留在随机初始化；核对load-bearing超参 | 全绿且契约一致→此时才允许给出"该模块在本任务上不载荷"的结论，写清覆盖了哪些探针、哪些fixed超参是caveat |
| S-13 | 新模块/新输入接上了、无报错、指标与baseline**完全一致**（连"变差"都没有）| P1（inspect型宿主版）| 有些宿主靠`inspect`从**回调方法的形参名**推断数据契约（PyG的`message()`、HF的`Trainer`、tsl的`Predictor`），形参名不是类型系统的一部分，拼错不构成错误。打印宿主实际解析出的形参集合：PyG `layer._user_args`、HF `trainer._signature_columns`、PEFT `peft_model.targeted_module_names`、tsl的warning日志。集合里缺了你以为传进去的那个名字=该张量被静默丢弃，从未参与计算。**2026-08-29真实执行修正了两处机制描述**：PyG拼错参数名时不是"那个张量不被传入"，而是`_collect`把该形参替换成`inspect._empty`**类对象本身**，所以经常表现成响亮但难懂的`TypeError: unsupported operand type(s) for *: 'Tensor' and 'type'`，缺失的形参名不会被打印出来，容易被误判成别的bug；也不是"写`**kwargs`会让inspect抓不到任何名字"——实测inspect会把字面字符串`'kwargs'`当成一个合法形参名捕获，`_user_args == ['x_j', 'kwargs']`才是这类错误的真实指纹。此诊断只覆盖自定义、带kwargs透传的层，PyG内置卷积层（GCNConv等）形参拼错会报正常的`TypeError`，不属于这个静默失败家族 | 按宿主的形参名契约改名（PyG的`_j`/`_i`后缀语义、HF的数据列名）；PyG的`message()`形参默认值不会被采纳（`edge_attr=None`+`is None`判断实测被2.8.0忽略），不要靠默认值兜底，必须显式传参 |
| S-14 | 探针全部返回空/"无差异"，且模型是`torch.compile`包的 | 见下方工具备注的torch.compile段 | hook根本没触发，不是没有差异——`instrument()`已经加了前置门会直接报错拒绝，如果看到空结果说明调用时传了`allow_compiled=True`但没有先验证hook真的触发 | 按工具备注的三条补救之一重跑；在确认hook实际触发之前，P2/P3/P4/P5/P7在compiled模型上一律拒绝输出数字 |
| S-15 | 多个组件各自单测全绿，组合起来指标却变差 | integration-sanity-checks.md的门禁逐个重跑 | 单独消融时没问题的组件之间存在破坏性交互（比如两个都做归一化、两个都改变量级） | leave-one-in二分定位：从"全加"开始，每次去掉一个组件重测，找到去掉哪个能恢复健康——报告模板的"组合关系"段要记录这个定位过程，不能只写"组合起来变差了" |
| S-16 | 训练loss健康下降，但eval指标钉在地板附近不动 | 无需探针，直接对比样本 | 训练目标和评测器打分的输出形状不匹配（比如训练是自由生成、eval要求精确匹配整数；或eval给部分分而训练reward是二值的），跟组件本身是否有效无关 | 并排打印3条训练样本与3条eval样本，问"一条满分的训练样本会不会被verifier判错，反之亦然"——换掉输出头/loss的组件正是这个问题的高发场景，排查时优先想到这条 |
| S-17 | 手写`torch.cuda.CUDAGraph`捕获训练循环下，探针数字"看起来在正常波动"但摸不到真实规律；或探针在capture那一刻直接崩出一个奇怪的CUDA错误 | 见上方工具备注CUDA graph capture段 | Hook在capture阶段只触发一次，`replay()`零次触发——三种表现：①hook里有`.item()`同步 → `cudaErrorStreamCaptureInvalidated`，报错信息不提hook也不提探针，还会**污染整个进程的CUDA context**；②hook把结果存到一个设备端张量、没有同步读 → 后续每次读到的都是capture那一刻的**同一块显存**（`data_ptr`相同），看起来像是三份合法的"逐步快照"，实际是同一份历史值的复制品，数值本身完全在合理范围、没有NaN，NaN检查抓不到；③hook什么都不做只是占位 → 什么异常都不出现，纯静默 | 用`torch.cuda.is_current_stream_capturing()`在hook第一行做守卫，capture期间直接fail-loud（`scripts/probe_hooks.py`的`instrument()`已内置这条）；真正的探针读数从graph之外单独的一次eager forward取，不要指望从被capture的hook里拿到任何per-step信息；`torch.cuda.make_graphed_callables`**不是安全的逃生门**——它自己的hook guard只检查顶层module的`_forward_hooks`等，不检查`named_modules()`也不检查`_backward_pre_hooks`，挂在子模块上的forward hook能绕过这个guard然后0/N次触发 |

## 一段可复用的探针骨架

见 `scripts/probe_hooks.py`。核心模式是 **instrument-then-diff**：① 对`model.named_modules()`注册前向hook记`(mean,std,zero_frac,absmax)`与full backward hook记`grad_output[0].norm()`，写进以模块名为键的dict；② 用相同seed、相同batch各跑一次baseline与改动后模型；③ 按模块名diff两个dict，按`|log ratio|`排序；④ 排第一的层=改动的因果入口；`handle.remove()`收尾，探针不得泄漏进训练。同一个模式还能**沿时间轴**用（P12提到的"diff健康batch与发散batch"），不是只能baseline-vs-candidate轴。

不知道该怀疑谁时，先用全局`register_module_full_backward_hook`一次性扫全网（PyTorch文档明说仅供调试/profiling）。文档化的坑：`grad_input`只覆盖位置参数（kwargs被忽略）；前向hook拿到的是张量的view，原地修改会报错。**实测坑**：`register_full_backward_hook`在某些模块上会打印`UserWarning: Full backward hook is firing when gradients are computed with respect to module outputs since no inputs require gradients`——两个独立合成实验都撞到过，都确认是无害的（通常发生在网络的第一个模块，输入本身不需要梯度），不用当成错误排查。

`assert_zero_init_unlocked()`（新增）用同样的instrument-then-diff思路，专门解决"零初始化分支到底是健康的还没解锁，还是永久性的接线bug"这个只靠单次读数分不清的问题——见`residual-gating-safe-integration.md`。`attention_entropy()`把P6公式的eps防护和"不要用先平均再算熵"的坑烘进了代码，不用每个人重新推导。`ceiling_gap()`是B4a泄漏探针（`borrow-existing-pipeline.md`）目前唯一有代码的部分。
