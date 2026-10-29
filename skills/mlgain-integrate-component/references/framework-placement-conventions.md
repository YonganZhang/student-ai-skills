# 采纳现成惯例：模块能接在哪，不自创

这一节回答"模块能接在哪"。**不自创**任何插槽词汇表，全部从下列已被大规模验证的惯例直接搬。

## 骨架惯例：MMEngine 的"角色注册表 + 作用域继承"

直接采纳，一字不改：

- **封闭的根注册表集合**：MMEngine 定义约 22 个 ROOT registry，按**角色**而非实现划分（`MODELS`/`DATASETS`/`TRANSFORMS`/`OPTIMIZERS`/`HOOKS`/`LOOPS`/`METRICS` 等）。下游 10 个库（mmdet/mmseg/mmpose…）从不新增根角色，只建同名子注册表。
- **组件永远可被一个 dict 寻址**：`{'type': 'Name', **kwargs}`。**放置写在 config 里，不写在代码里。**
- **直接推论（本 skill 要用的判据）**：一个新组件合法，当且仅当它恰好属于一个已有根角色。不命中任何角色，是"出现了新角色"的信号，走 `module-taxonomy.md` 的元规则 M5 新建插槽，并显式声明。

即使目标项目不用 MMEngine，也照抄"角色→注册表→config dict"这套心智模型：第一个问题永远是"它是哪个角色的实现"，不是"它插在第几层"。

## 模型内部插槽惯例（按模型家族分表）

**这是本文件的核心资产：模型家族 → 合法插槽 → 插槽契约。** 新家族（UNet、SSM、任何新架构）通过在这张表里加一行来纳入，无需改动其它文件。

| 模型家族 | 惯例来源 | 合法插槽 | 插槽的张量契约（照抄，不改写） |
|---|---|---|---|
| 检测/两阶段 CV | MMDetection | backbone/neck/head/roi_extractor/loss(head内) | `extract_feat`: `x=backbone(imgs)`；`if with_neck: x=neck(x)`。backbone `forward(imgs)->tuple[Tensor]` 多尺度；neck 是 backbone 与 head 间唯一合法插槽。**⚠️ 不要假设"输入输出层数相等"（同 arity）**：官方 Faster R-CNN + FPN config 里 backbone 输出 4 层、FPN `num_outs=5`，层数由 neck 自己的 config 显式声明，不是隐含相等。真正不变的契约是"有序的多尺度特征序列"，输入/输出层数各自由 config 决定 |
| 分割 | MMSegmentation `BaseDecodeHead` | 同上 + 显式挂载点声明 | `in_index`+`input_transform` 三值：`None`(单stage)/`resize_concat`(多stage双线性对齐后concat，有效`in_channels=sum(...)`)/`multiple_select`(list透传)。`_init_inputs` 在**构造期**硬校验，非法放置 build 时报错而非首次 forward |
| 通用视觉 backbone | detectron2 `Backbone` ABC | META_ARCH > BACKBONE/PROPOSAL_GENERATOR/ROI_HEADS | `forward()->dict[str,Tensor]`（**命名**而非位置）+ 必需的 `output_shape()->dict[str,ShapeSpec]`；下游按 `backbone.output_shape()` 自动定尺寸，放置错误表现为 KeyError 而非静默 shape bug |
| 任意视觉 backbone 切口 | timm | `forward_features`/`forward_head` 两段 | `forward_features(x)`=到最后 norm 为止，不含 pooling/head；`reset_classifier(num_classes,global_pool)` 物理删除 head 参数；`features_only=True,out_indices=...` 得多尺度输出；`model.feature_info.channels()/.reduction()` 让下游自己定尺寸，**禁止硬编码 channel 常量** |
| Transformer 子层 | HF `AttentionInterface` | attention 是被指定的可插拔子层 | 固定签名 `fn(module,query,key,value,attention_mask,**kwargs)->(attn_output,attn_weights)`。**配对不变量**：必须同名注册 `AttentionMaskInterface`，否则 `attention_mask` 被静默传入 None |
| Transformer backbone 挂载点 | HF `BackboneMixin` | `stage_names` 定义有序命名切口 | 用户给 `out_features` 或 `out_indices`，`verify_out_features_out_indices()` 在不一致或越界时抛错 |
| Encoder-Decoder/UNet | segmentation_models.pytorch `EncoderMixin` | encoder/decoder/segmentation_head/可选classification_head | encoder 声明 `_out_channels`/`_depth`/`_in_channels`，`forward()` 返回空间分辨率递减的特征 list，硬不变量 **`len(features)==_depth+1`** |
| PEFT/适配器 | HF PEFT | 不是角色表，是**选择器语言** | `target_modules`：精确名/后缀/regex，对 `named_modules()` 解析；`modules_to_save` 是另一个字段（全量训练任务头，防止 head 被静默 LoRA 化）。**社区维护的架构→默认插入点表** `TRANSFORMERS_MODELS_TO_LORA_TARGET_MODULES_MAPPING`（`peft/utils/constants.py`）才是真源，**不是所有架构都固定插 q/v**——GPT-2/BLOOM 等用 fused `c_attn`/`query_key_value`，必须查这张表而不是套用单一结论。验证 affordance 必用 `peft_model.targeted_module_names`+`print_trainable_parameters()`：选择器选空时是静默的。层类型不被支持时（如 `nn.LSTM`）的逃生门是实验性私有 API `config._register_custom_module({nn.LSTM: MyLoraLSTMLayer})`，必须在 `get_peft_model()` **之前**调用，且**不随 `save_pretrained` 持久化**——重新加载 checkpoint 时必须重新注册并显式传 config，否则 dispatch 会静默回退到内置层类 |
| 无法改 config 的既有模型 | MosaicML Composer `module_surgery` | 类型键控的替换策略 | `replace_module_classes(model, policies: dict[type,ReplacementFunction], optimizers=None)`。返回 `None`=放过该实例；**必须传 `optimizers=`** 触发参数迁移，否则新参数永不被更新 |
| 纯数据流型（YOLO 系）| Ultralytics model YAML | 无角色，只有带索引的边表 | `[from, repeats, module, args]`：`from`=-1/正索引/索引list(多输入concat/FPN横向)。**选型判据**：合法性主要取决于"谁喂谁"用这套，取决于"它是什么角色"用角色表那套 |
| 搜索/可变架构 | NNI NAS 词汇（仓库已归档，只取词汇）| `LayerChoice`/`InputChoice`/`Repeat`/`Cell` | `LayerChoice(candidates)` 候选须形状可互换；`InputChoice` 声明融合算子；`label` 机制：共享 label 的两处原语被强制做相同选择——比写校验代码更好的"这两处放置必须一致"声明方式 |

## 采纳规则

1. 先判定宿主项目属于上表哪个家族（有没有 registry/config/`forward_features`/`stage_names`/model YAML）。
2. **有惯例 → 100% 照抄惯例的插槽名、契约签名和默认放置表**。例如宿主是 HF 系+组件是 LoRA 类 → 直接查 `TRANSFORMERS_MODELS_TO_LORA_TARGET_MODULES_MAPPING`，不自己推 target_modules。
3. **无对应家族 → 在上表新增一行**，至少给出：插槽名集合、每个插槽的 forward 签名、arity/形状不变量、构造期校验函数。
4. 无论哪条路径，最终产出一个**构造期 assert**，而不是靠 forward 时报错。
