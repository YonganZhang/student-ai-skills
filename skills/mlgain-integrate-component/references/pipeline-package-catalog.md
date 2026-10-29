# Pipeline 包目录：按领域查、只读自己那一行

`borrow-existing-pipeline.md` 的 P0 选包、P3 定位 swap 点时查这张表。全部信息经源码/官方文档核验（2026-08-29），不是转述 README 宣传语。

## 时序（time-series）

| 排名 | 包 | 精确 swap 机制 | 何时选它 | 硬约束 |
|---|---|---|---|---|
| **T1** | **sktime/pytorch-forecasting**（v1, MIT；实测 1.8.0）| 继承 `pytorch_forecasting/models/base/_base_model.py` 四个基类之一：`BaseModel` / `BaseModelWithCovariates` / `AutoRegressiveBaseModel` / `AutoRegressiveBaseModelWithCovariates`。实现 `forward(x: Dict[str,Tensor]) -> Dict[str,Tensor]` + `@classmethod from_dataset(cls, dataset, **kwargs)`。**无需注册即可用**（1.8.0 起包内有 `_registry/` 目录，但那是给已收录模型用的索引，不是新模型接入的前提）：`MyModel.from_dataset(training_ds, ...)` 直接可用 | 面板/多序列+静态协变量+时变已知/未知协变量+需要分位数概率输出。**默认首选** | 必须 pin `<2.0.0`（v2 的 `_base_model_v2.py` 是并行的另一套 API，无 `from_dataset`，不要把两套基类的方法互相套用）。`TimeSeriesDataSet` 的 batch dict 是硬契约。另：依赖 `lightning` 发行版（命名空间 `lightning.pytorch`），与 T2 的 `pytorch-lightning` 是不同类对象，同环境混装会让 Callback/Logger isinstance 失败，见"通用训练循环标准化"。🔴 **`step()` 是被重写的关键钩子**（`models/nbeats/_nbeats_adapter.py:177`）：内置模型的核心损失项（如 NBeats 的 backcast loss）可能写在这里而不是 `forward()` 里，`borrow-existing-pipeline.md` 的 B4' 冒名顶替测试如果只组合转发 `forward()` 会静默丢掉这部分——必须继承整个基类，不要只包一层转发 `forward` 的组合类 |
| **T2** | **Nixtla/neuralforecast**（Apache-2.0）| 继承 `neuralforecast.common._base_model.BaseModel`（`pl.LightningModule` 子类）。设 6 个类级布尔 `EXOGENOUS_FUTR/HIST/STAT/CAT/MULTIVARIATE/RECURRENT`，实现 `__init__`+`forward(windows_batch)`，batch 键为 `insample_y/insample_mask/futr_exog/hist_exog/stat_exog`，输出按 `self.loss.outputsize_multiplier` reshape。已核实 `NeuralForecast(models=[...])` 无白名单，零库内编辑即可用 | 要 `cross_validation()` 滚动回测、conformal/quantile 区间、Auto* HPO | 🔴 `NeuralForecast.save()/load()` 对直接 `BaseModel` 子类会 `raise ValueError`（`MODEL_FILENAME_DICT` 里没有 `"basemodel"`）。绕法：monkeypatch 该 dict，或继承一个内置模型（会以父类反序列化，改了超参是陷阱）。另：依赖 **legacy** `pytorch-lightning`（命名空间 `pytorch_lightning`）；Trainer 由包内部 `pl.Trainer(**model.trainer_kwargs)` 构造，不要自己实例化 Trainer |
| **T3** | **thuml/Time-Series-Library (TSLib)**（MIT, **仅 vendor**）| 把 `models/MyModel.py` 丢进去即可，`class Model(nn.Module)`，`__init__(configs)`，`forward(x_enc, x_mark_enc, x_dec, x_mark_dec)`。`exp/exp_basic.py` 的 `_scan_models_directory()` 自动发现，`python run.py --model MyModel` 直接可用 | 要在标准 LTSF 基准上对打 iTransformer/TimesNet/PatchTST/DLinear 等强 baseline | 🔴 不是 pip 包，只能 fork 并 pin commit SHA。🔴 `models_dir='models'` 是相对 cwd 的路径，不在仓库根目录启动会静默扫出空 dict。2026-04 已公告停止加新特性 |

### 时序分类（TSC）

| 排名 | 包 | 精确 swap 机制 | 何时选它 | 硬约束 |
|---|---|---|---|---|
| **T4** | **aeon** 1.5.0（BSD-3）| 纯 sklearn 式估计器互换：所有分类器继承 `aeon.classification.base.BaseClassifier(ClassifierMixin, BaseCollectionEstimator)`，公共 `fit` 是 `@final`，子类只实现 `_fit(X,y)/_predict(X)/_predict_proba(X)`。**换模型=换一行 import**：`from aeon.classification.convolution_based import MultiRocketHydraClassifier as C` → `C().fit(X,y).predict(X)`。批量扫用 `aeon.utils.discovery.all_estimators(type_filter="classifier", tag_filter={...})` | **TSC默认首选**。要的是"哪个已发表算法在我数据上赢"：HIVECOTEV2/MultiRocketHydra/QUANT/FreshPRINCE/RDST/ProximityForest 全在；需要 `predict_proba` 与 sklearn `Pipeline/GridSearchCV`；需要不等长或多变量集合 | 🔴 `requires_python 3.11–<3.15`，需单独 env。🔴 X 是**集合** `(n_cases, n_channels, n_timepoints)`，不是一条长序列（与 T6 正好相反）。🔴 `deep_learning` 子包是 **Keras/TensorFlow**，PyTorch 项目要 DL 走 T5。HIVECOTEV2/ElasticEnsemble 训练近 O(n²)，是精度天花板参照不是生产默认 |
| **T5** | **tsai** 1.0.1（Apache-2.0）| 一个关键字 `arch=`：`TSClassifier(X, y, splits=splits, arch="InceptionTimePlus", arch_config=dict(nf=64, depth=9), metrics=accuracy)`。字符串→类惰性 import 分派（`tsai/learner.py`，约 110 个合法名：MiniRocket/MultiRocket/Hydra/TST/TSTPlus/TSiT/PatchTST/ConvTran/XCM/LSTM_FCN…）；也可直接传已构造的 `nn.Module`。`TSRegressor`/`TSForecaster` 同一套 `arch=` 通用 | 要**深度模型+PyTorch**：Rocket 家族与 TST/PatchTST/ConvTran 在同一个旋钮下，附带 fastai 的 LR finder/one-cycle/mixup/TTA | 🔴 硬依赖 **fastai**：`TSClassifier` 是 `fastai.learner.Learner` 子类，不兼容 sklearn `Pipeline`，按"通用训练循环标准化"属 **Tier C（保留其原生 fastai 循环）**。**纠正一条易过期认知**：tsai 不是停更包——1.0.0/1.0.1 于 2026-05 发布，repo 持续有 push |

### 时序异常检测（TSAD）

| 排名 | 包 | 精确 swap 机制 | 何时选它 | 硬约束 |
|---|---|---|---|---|
| **T6** | **PyOD** 3.6.5（BSD-2）| `pyod.models.ts_od.TimeSeriesOD(detector='IForest', window_size=50, step=1, score_aggregation='max', contamination=0.1)` → `fit(X)`/`decision_function(X)`/`labels_`。`detector=` 是swap旋钮：滑窗化序列→任意 PyOD 检测器跑窗口矩阵→窗口分数按 max/mean 映回时间戳（23 项内置检测器：KNN/LOF/ECOD/COPOD/HBOS/PCA/OCSVM/IForest…）。另有专用 TS 模块共用同一契约：`ts_lstm.LSTMAD`、`ts_anomaly_transformer`、`ts_matrix_profile` | **TSAD默认首选**。要的是一条长（单/多变量）序列的逐时间戳分数，一个for循环扫20+检测器，包活跃维护 | 🔴 输入是**一条序列**`(n_timestamps,)`或`(n_timestamps,n_channels)`，不是序列集合（与T4相反）。🔴 `contamination∈(0,0.5]`，benchmark里报`decision_scores_`/AUC，不要报`labels_`。🔴 因果检测器（LSTMAD）前`window_size`个时间戳无回看，必须从指标里剔除 |
| **T7** | **Orion**（`orion-ml`）0.7.1（MIT）| swap的是**命名JSON pipeline**不是类：`Orion(pipeline='aer', hyperparameters={...})` → `fit(train_df)`/`detect(df)`（可选：AER/TadGAN/LSTM-DT/AnomalyTransformer/Matrix Profile）| **只为一个能力保留**：交付物是**带severity的异常区间`(start,stop)`**而不是逐点分数（下游是告警/工单流程）。PyOD和aeon都不能一次给出区间输出+基准评测 | 🔴 PyPI `requires_python>=3.8,<3.12`，必须独立env。🔴 **仅单变量**：`timestamp,value`两列DataFrame。🔴 MLBlocks/MLPipeline依赖栈重且版本脆 |

**已在 aeon 生态内的第三条路（不单列一行）**：`aeon.anomaly_detection.series.PyODAdapter(pyod_model=LOF(), window_size=10, stride=1)`，把PyOD检测器塞进aeon的`fit/predict/fit_predict(X, axis=...)`契约。⚠️ aeon的series异常检测模块里没有深度学习检测器（只有distance_based/distribution_based/outlier_detection经典方法）——"用aeon做AD"=经典AD。

### 时序缺失填补（imputation）

| 排名 | 包 | 精确 swap 机制 | 何时选它 | 硬约束 |
|---|---|---|---|---|
| **T8** | **PyPOTS** 1.5（BSD-3）| 任务类+统一三方法契约：`pypots.imputation`下每个模型继承`BaseImputer`/`BaseNNImputer`，签名逐字相同——`fit(train_set, val_set=None)`、`predict(test_set)->dict`（键`'imputation'`）、`impute(test_set)->np.ndarray`。**换模型=换import+换架构超参**：`from pypots.imputation import SAITS` → `SAITS(n_steps=T, n_features=D, ...).fit(train_set, val_set).impute(test_set)`。约49个模型共享该契约（SAITS/BRITS/CSDI/GPVAE/TimesNet/iTransformer/PatchTST…）| **缺失本身就是问题时的唯一严肃选项**：不规则临床/传感器序列。决定性优势：**朴素基线`Mean`/`Median`/`LOCF`用完全相同的API**，"深度模型vs前向填充"对照表就是一个for循环 | 🔴 `n_steps`/`n_features`是**无默认值的必填构造参数**，序列必须预先切成固定长度。🔴 输入是3-D`[n_samples,n_steps,n_features]`，`NaN`标记缺失。🔴 `val_set`必须除`"X"`外再带**`"X_ori"`**（真值）——只传`"X"`是静默陷阱。🔴 复制`pypots/<task>/template/`写自定义模型时，模板`model.py`把`fit/predict`桩成`NotImplementedError`，照抄会禁用基类可用实现——以官方dev_standard_nn文档为准 |

**跨任务提示**：`pypots.anomaly_detection`用同一模式导出21个模型（`BaseDetector(anomaly_rate=...)`，`fit/predict/detect`）。**当项目同时需要"填补+在不完整数据上做AD"时，PyPOTS是唯一能用一个依赖同时回答两者的包**——这是唯一该把T6换掉的情形。

**分支路由**：数据是图/传感器网络（井间干扰）→ `TorchSpatiotemporal/tsl`，`Predictor(model_class=MyModel, model_kwargs=...)`，⚠️ forward 形参名必须匹配 batch 键（`x`/`edge_index`/`edge_weight`/`u`），不匹配只 `logger.warning` 后静默丢弃——这是"inspect型宿主靠形参名推断契约、拼错不报错"这一类问题的一个实例，同类还有PyG的`message()`和HF的`Trainer`，诊断统一见`mechanistic-diagnosis.md`的S-13。只要评估/回测框架、模型用现成的 → `darts`，但自定义架构路径全部下划线私有且历史上删过基类，不建议走这条。**不要用**：`mlforecast`（不训练 nn.Module）、`statsforecast`（只做经典 baseline）、`AutoGluon-TS`（swap 在整个 estimator 层级）。

**⚠️ 本表是快照不是常识**：全部信息经源码/官方文档核验（2026-08-29）。任何一行在使用时若距核验日期超过~6个月，或与实际装到的版本行为不符，以`pip show`/源码为准并回写本表。已知易漂移字段：`requires_python`、最后发布日期、是否archived、私有API路径（本次核验中就发现两处过期认知：tsai 曾被误判停更、PyOD 曾被误判仅限表格数据）。

## 计算机视觉

| 排名 | 包 | 精确 swap 机制 | 何时选它 | 硬约束 |
|---|---|---|---|---|
| **C1** | **timm**（Apache-2.0）| (a) 当可换 backbone 用：`timm.create_model(name, features_only=True, out_indices=(2,4))` → `.feature_info.channels()/.reduction()` 拿通道数和 stride，禁止硬编码 channel 常量。(b) 注册自己的架构：`from timm.models import register_model` 装饰**工厂函数**（不是类），之后 `create_model('my_arch')` 可用 | 分类/需要带干净 channel-stride 元数据的 backbone | (b) 官方文档完全没写这条，只能读源码抄内置模型文件 |
| **C2** | **segmentation_models.pytorch (smp)**（MIT）| 常规：`smp.Unet(encoder_name='tu-<任意timm名>', encoder_weights='imagenet', classes=N)`。自定义 encoder：`class MyEncoder(nn.Module, EncoderMixin)`，设 `_out_channels`/`_depth`/`_in_channels`，`forward()` 返回按空间分辨率降序的特征 list（depth=5 → 6 个张量），注册用裸 dict 赋值 `smp.encoders.encoders["my_enc"]={...}` | 语义分割，想快速对比 decoder×encoder 组合 | 🔴 官方文档注册代码块有个多余逗号，照抄会变成 tuple 报错。维护已进入托管模式 |
| **C3a** | **Ultralytics**（检测/分割/pose，**AGPL-3.0**）| 干净路径是 `class CustomTrainer(DetectionTrainer): def get_model(...)`，整条数据/增广/损失/mAP 留用。加新 block 到 YAML 图必须改三处源码（无 registry，名字解析是 `globals()[m]`）| 需要开箱即用的检测全流程 | 🔴 AGPL-3.0，联网使用即触发 copyleft，商用要买license。不加进 `base_modules` 会静默不生效 |
| **C3b** | **Detectron2**（Apache-2.0）| `@BACKBONE_REGISTRY.register()`，`forward(image) -> {name: tensor}`，`output_shape() -> {name: ShapeSpec}` | 需要 Apache 许可、可接受自编译 | 🔴 2021 后无 release，现代 toolchain 上编译是主要失败点 |

**已排除**：MMDetection/MMSegmentation registry+config 机制全场最好，但 `mmdet/__init__.py` 硬 assert `mmcv<2.2.0`，torch≥2.5 无对应 wheel，实际被钉死在 PyTorch≤2.1。`lightning-flash` 已 archived。**特殊域**：视觉异常检测 → Anomalib，`Padim(backbone=<自定义nn.Module实例>)` 支持传实例但 YAML/CLI 路径不支持；医学 3D → MONAI，`_target_: my_pkg.MyUNet` 任意可导入路径零注册。

## LLM 微调/后训练

⚠️ **置信度声明**：本节已于 **2026-08-29 在本机隔离 venv 实测执行**（`transformers 5.16.1` / `peft 0.20.0` / `trl 1.12.0` / `torch 2.13.0+cpu`，全程 `HF_HUB_OFFLINE=1`，模型由 config 构造、tokenizer 本地构造）。L1 行的 swap 机制、AttentionInterface 掩码陷阱、PEFT 自定义层三条主张均已跑通或复现失败模式。**已纠正一处过期认知**：`transformers` v5 确实把 `PretrainedConfig` 改名 `PreTrainedConfig`，但 `configuration_utils.py` 保留了 `PretrainedConfig = PreTrainedConfig` 别名（实测 `is` 判等 True，无 DeprecationWarning），**旧教程 import 不会 ImportError**——真正会炸的是把两者当独立类做 `isinstance` 区分。复核周期仍建议约 3 个月：`trl` 一年内从 0.29 跳到 1.12，默认值随大版本漂移。

| 排名 | 包 | 精确 swap 机制 | 何时选它 | 硬约束 |
|---|---|---|---|---|
| **L1** | **HF Transformers + PEFT + TRL**（Apache-2.0；实测 `trl 1.12.0` / `peft 0.20.0` / `transformers 5.16.1`，`trl` 版本已从旧认知的 0.29.1 大幅跳升，复核周期约3个月）| **四个分层swap点，按侵入度递增**。**L0换整个架构**：`class MyConfig(PreTrainedConfig): model_type="myarch"` + `class MyModel(PreTrainedModel): config_class=MyConfig`，`AutoConfig.register(...)`/`AutoModelForCausalLM.register(...)`；**接进pipeline的官方入口就是`SFTTrainer`的第一个形参**：`model: "str \| PreTrainedModel \| PeftModel"`——直接传构造好的实例（实测CONFIRM：自定义`PreTrainedModel`直接传入、`AutoConfig.register`+save/from_pretrained往返均可用）。**但不是"零config字段"**：实测发现`SFTConfig`两个默认值会直接把从零训练的自定义架构训练崩——`gradient_checkpointing`默认`True`；`loss_type`字段默认虽是`None`，但`sft_config.py:331-332`的`__post_init__`会把它解析成`"chunked_nll"`（除非设置`use_liger_kernel`），自定义模型不满足该loss实现假设的forward契约就会崩在`train()`内部，不是构造期报错。**L1只换attention内核**：`AttentionInterface.register("custom", fn)`，签名硬契约`fn(module,query,key,value,attention_mask,...,**kwargs)->(attn_output,attn_weights)`，再`from_pretrained(...,attn_implementation="custom")`。**L2只训adapter**：`get_peft_model(model, peft_config)->PeftModel`；`SFTTrainer(...,peft_config=LoraConfig(...))`。**L3只换损失**：`SFTTrainer(...,compute_loss_func=...)`，或换trainer类（SFT→DPO→GRPO）| 要接LLM后训练（SFT/DPO/GRPO）、或只想换attention内核/加adapter而不碰模型文件 | 🔴 `AttentionInterface.register`**必须配套**`AttentionMaskInterface.register("custom", sdpa_mask)`——未注册同名mask函数时Transformers**跳过mask构建、直接传`attention_mask=None`**，causal/padding约束被静默丢弃（对应S-8）；实测数字：真实非pad token上`max|Δlogits|`，未配对mask=**0.149**，配对后=**4.47e-08**。另有一处mask dtype细节：mask函数按bool/float32分支处理，混用会绕过预期的mask逻辑，写自定义mask函数时显式声明返回dtype。🔴 不能同时传`PeftModel`和`peft_config`（实测复现出确切的`ValueError`）。🔴 PEFT自定义adapter层类型只有实验性私有API `config._register_custom_module({nn.LSTM: MyLoraLSTMLayer})`，必须在`get_peft_model`**之前**调用，且**不随`save_pretrained`持久化**——重新加载时必须重新注册（实测：完整dump `adapter_config.json`，零痕迹）。🔴 **peft 0.20.0 API 已漂移**：跟公开教程对不上——`LoraLayer.update_layer`现在要求位置参数`config`；`_get_in_out_features`返回`(None, None)`；`in_features`不能再实现成`@property`。🔴 **`transformers` v5 确实把 `PretrainedConfig` 改名 `PreTrainedConfig`，但保留了 `PretrainedConfig = PreTrainedConfig` 活别名**（`is` 判等为 True），旧教程 `import PretrainedConfig` 不会 ImportError——上面"置信度声明"已更正 |

**三处必须打的作用域补丁（否则新行与既有文本互相矛盾）**：
1. 下方"通用训练循环标准化"Tier C行「代表包」列追加：`TRL/transformers Trainer（仅限Transformers/PEFT模型）`——`SFTTrainer/DPOTrainer`继承`transformers.Trainer`，经继承拿到accelerate/DeepSpeed ZeRO/FSDP/DDP/gradient checkpointing。**"写一个LightningModule去包SFTTrainer/DPOTrainer"是本节68行点名反模式的LLM版**，失败方式同样恶劣（丢packing掩码或ref-adapter切换不会崩，只会静默掉几个点）。
2. Tier A行「代表包」列的`HF backbone`加限定：`HF backbone（当作纯nn.Module单独取用时）`，否则与新增的Tier C归属直接冲突。
3. "明确降级/禁用"里HF `Trainer`的判断改成双向作用域：`对非Transformers模型是本组最危险的（原有两条机制不变）；对Transformers/PEFT模型它就是Tier C的原生循环，必须用、不许重写`。

## 图神经网络（GNN）

✅ **G1 已于 2026-08-29 在本机实测执行**：隔离 venv（`torch 2.13.0+cpu` / `torch-geometric 2.8.0.post1` / `pyg-lib 0.8.0+pt213cpu`），覆盖 MessagePassing 子类化、`propagate` 形参名契约、Cora GCN 端到端复现（test acc **0.8130**，Kipf 原文 0.815）、torch-scatter/pyg-lib 安装路径实测。Tier A 归类经官方 `examples/gcn.py@tag 2.8.0` 与 wheel 内零 `Trainer`/`fit(` 命中双重确认。

| 排名 | 包 | 精确 swap 机制 | 何时选它 | 硬约束 |
|---|---|---|---|---|
| **G1** | **PyTorch Geometric (PyG)** 2.8.0（MIT）| **无注册机制**：继承`torch_geometric.nn.MessagePassing`，构造签名`MessagePassing(aggr='sum', flow='source_to_target', node_dim=-2)`；覆写`message()`(φ)/`aggregate()`/`update()`(γ)；触发入口`propagate(edge_index, **kwargs)`。直接import当普通`nn.Module`用——**本目录里swap成本最低的一个** | 图/关系型数据的自定义消息传递层 | **注意归属：PyG核心没有原生pipeline**（官方`examples/gcn.py`的`train()`是手写`zero_grad/forward/loss/backward/step`，没有Trainer、没有官方指标复现harness）→按10秒判别测试是**Tier A，强制Lightning**。`torch_geometric.data.lightning`提供`LightningDataset`/`LightningNodeData`处理邻居采样与分布式切分。🔴 **形参名是硬契约**：`propagate(edge_index,**kwargs)`里的kwargs**只有名字对得上才会喂进`message()`**，拼错或在`message()`里写`**kwargs`：**不报错、不warning，那个张量静默不参与计算，loss照常下降**（诊断见`mechanistic-diagnosis.md`的S-13，2026-08-29真实执行确认了两处更细的机制并推翻了原判据的两句话：不是"那个张量不被传入"，而是`_collect`会替换成`inspect._empty`**类对象本身**，所以失败经常是响亮但难懂的`TypeError: unsupported operand type(s) for *: 'Tensor' and 'type'`，缺失的参数名不会被打印出来；也不是"写`**kwargs`会让inspect抓不到任何名字"，实测inspect会把字面字符串`'kwargs'`当成一个参数名捕获，`_user_args == ['x_j', 'kwargs']`才是真实指纹）。🔴 `message()`形参**不认Python默认值**：`def message(self, x_j, edge_attr=None)`配合函数体内`if edge_attr is None`的判断实测是坏的，PyG 2.8**会忽略**该默认值，务必显式传参或在`propagate`调用处兜底。🔴 `torch-scatter`/`torch-sparse`装法已过期（实测`torch-scatter 2.1.2`的sdist直接`ModuleNotFoundError: No module named 'torch'`装不上），2.8.0起改推`pyg-lib`（实测`pyg-lib 0.8.0+pt213cpu`装得干净）。🔴 `pip install torch_geometric`**不会**连带装`torch`和`scipy`，需要自己补装。🔴 `inspector.get_flat_param_names()`在2.8.0会抛`IndexError`，诊断只能用`_user_args`/`get_param_dict`。🔴 上面的S-13诊断只覆盖自定义、带`**kwargs`透传的层——内置卷积层（GCNConv等）形参拼错会报正常的`TypeError`，不是这个静默失败家族 |

**分支路由/已排除**：`torch_geometric[graphgym]`extra装的是**legacy `pytorch-lightning`**（Tier B坑#1的第三实例——GraphGym试`lightning.pytorch`失败才回落到`pytorch_lightning`），且GraphGym的`main.py`/`configs/`不在pip包里（同TSLib只能fork+pin SHA），只为大规模结构/超参网格搜索保留，默认图任务仍走G1。**已排除DGL**：GitHub release停在2024-09、约13个月无push，按本目录一贯的活跃度判据（`lightning-flash`已archived被排除）同一把尺子下排除，纯粹是维护节奏问题不是API质量评判。

## 通用训练循环标准化

**唯一规则**：Lightning 是"**循环由你自己写**"时的强制默认且唯一选项；**你永远不是那个该为"已自带经过验证的循环"的包重写循环的人**——那些包保留其原生 trainer。不提供并列的循环框架菜单（之前 G1/G2/G3 三选一的写法已核实是错的：7 个借用包源码核验后，5 个自带完整非-Lightning 循环，硬包一层 Lightning 只会丢掉已验证基础设施）。

**10 秒判别测试**：该包是否自带一个能算出该任务**官方指标**（COCO mAP、LTSF 基准 MSE）并复现出**已发表数字**的 trainer？

| 档 | 判别结果 | 强制做法 | 代表包 |
|---|---|---|---|
| **Tier A** | 只提供 `nn.Module` 架构，没人写过循环 | **Lightning，无例外**：`class LitModel(L.LightningModule): def __init__(self, encoder)`，必需方法只有 `training_step`+`configure_optimizers`；配置化换模型走 `LightningCLI` 的 `class_path/init_args`（submodule 级也支持）。**项目必须明文规定使用 automatic optimization**——自动模式下 `zero_grad/backward/step` 顺序被关在框架内，agent 无法改错；手动优化（GAN/多优化器）这几行会回到用户代码 | timm、smp、torchvision.models、**HF backbone（当作纯nn.Module单独取用时）**、PyG（`torch_geometric.nn.*`/`MessagePassing`）、自写 `nn.Module`、TSLib 的 `models/*.py` 单独取用时 |
| **Tier B** | 包本身已经是 Lightning | "借"和"统一"是同一条指令，零成本。但两条已核实的坑必须遵守（见下）| pytorch-forecasting（`class BaseModel(..., LightningModule, ...)`，依赖 `lightning>=2.0,<2.7`，命名空间 `lightning.pytorch`）、neuralforecast（`class BaseModel(pl.LightningModule)`，依赖 **legacy** `pytorch-lightning>=2.0,<2.6`，命名空间 `pytorch_lightning`）|
| **Tier C** | 自带完整原生循环+官方指标验证器 | **保留原生循环**，通过其既有扩展点（Ultralytics callbacks / detectron2 hooks / MMEngine hooks）接入，禁止重新包一层 | Ultralytics（`BaseTrainer` 拥有 `build_optimizer`、`torch.amp.GradScaler`、`ModelEMA`、DDP、warmup、`last.pt/best.pt`、`EarlyStopping`、`resume_training`，外加 24+ 格式 `Exporter`）、Detectron2（`TrainerBase/SimpleTrainer/AMPTrainer`+`DefaultTrainer.build_hooks()`）、MMDet/MMSeg（`mmengine.model.BaseModel`+Runner+OptimWrapper+hooks+Evaluator）、**TRL/transformers Trainer（仅限Transformers/PEFT模型）**|

**🔴 Tier B 两条坑**：
1. **发行版分裂是活的地雷**：pytorch-forecasting 装的是 `lightning`（`lightning.pytorch.Callback`），neuralforecast 装的是 `pytorch-lightning`（`pytorch_lightning.Callback`），**是两个不同的类对象**——跨命名空间的 Callback/Logger 会 isinstance 检查失败或静默不触发。**"一个环境只允许一个命名空间"这条规则本身不成立**：2026-08-29 实测在同一个 `pytorch-forecasting 1.8.0` 环境里 `lightning 2.6.5` 和 `pytorch_lightning 2.6.5` 两个命名空间**同时存在**（pytorch-forecasting 的依赖树自带了两者）。判据改成运行时探测，不要用"装了几个包"判断：现场问宿主 `issubclass(HostBaseModel, lightning.pytorch.LightningModule)`（实测 pytorch-forecasting 的模型基类 → `True`）还是 `issubclass(HostBaseModel, pytorch_lightning.LightningModule)`（→ `False`），跨命名空间混用 Callback/Logger 前一律先跑这条判断，不要假设"只装了一个就是它"。
2. **neuralforecast 里你不拥有 Trainer**：它在 `_fit()`/`_fit_distributed()`/`predict()` 内部构造 `pl.Trainer(**model.trainer_kwargs)`。你通过 `trainer_kwargs` 配置 Lightning，**不要自己 `pl.Trainer(...)`**。

**🔴 点名反模式**："写一个 LightningModule 去包住 YOLO / Detectron2 模型并调它的 forward"。这是本节最贵的错误——你继承不到任何已验证基础设施，却全盘继承了该模型所有未文档化的假设。失败方式最恶劣：忘了 EMA 或 mosaic close-out 不会崩，只会悄悄掉几个点 mAP，然后你得出"这个方法没用"的结论。**反证（框架作者自己给的）**：detectron2 官方 `tools/lightning_train_net.py` 里的 `class TrainingModule(LightningModule)` 仍然要调 `build_model/build_optimizer/build_lr_scheduler/build_detection_train_loader/DetectionCheckpointer/SimpleTrainer.write_metrics/build_evaluator`，**并且额外**手工管理 `EventStorage`、`IterationTimer`、`on_save_checkpoint/on_load_checkpoint` 里的 iteration 状态。它没有替换 detectron2 的基础设施，只是换个地方托管它并附赠一张手工重接线账单——成本侧满、收益侧空。

**逃生门（带闸门）**：把 Tier C 模型移植到 Lightning，只有当原生循环**结构上**做不到你要的事才合法：跨两个包的联合多任务训练、双优化器/对抗方案、自定义分布式策略。一旦启动，它是一次**有预算的移植+硬验收门**——**必须先用你的循环在该包自己的基准上复现出它公布的指标，才允许相信它产出的任何新数字**。没有这道门，"我移植到了 Lightning"和"我悄悄弄坏了它"不可区分。

**TSLib 是边界穿过包内部的特例，必须明写**：`models/*.py`（iTransformer/TimesNet/PatchTST/DLinear，经 `LazyModelDict`/`importlib` 懒加载）是纯 torch module=**Tier A**，随便用 Lightning 包；`exp/exp_*.py` 是基准 harness（特定 data provider、scaler、split 和产生已发表数字的评测协议）=**Tier C**。判据：**要复现/对打 TSLib 基准数字→原封不动跑它的 `exp` 循环，偏离即比较失效；只是把某个 TSLib 架构用到自己应用里→直接 import `Model` 类当 `nn.Module` 用 Lightning 包**。

**真正该统一的不是循环，是外层契约**（四种原生循环都能通过既有扩展点支持，这条才是七个包上都可强制执行的）：每次 run 写到 `runs/<exp_id>/`，含 `config.yaml`+`metrics.jsonl`+checkpoints；一套 seeding 约定；一个指标日志目的地。**"到处都是同一个 LightningModule"做不到，别装作做得到。**

**明确降级/禁用**：`PyTorch Ignite` 和 `fastai` 不再作为并列选项（Tier A 只有 Lightning）——除非该包的官方 swap 点本身就是 fastai（如 tsai 的 `TSClassifier` 就是 `fastai.Learner` 子类，那属于 Tier C，用它的）。**HuggingFace `Trainer` 是双向作用域的**：对非 Transformers 模型是本组最危险的——`model_accepts_loss_kwargs` 靠 `inspect.signature` 推断，forward 写了 `**kwargs` 会跳过 loss 除法；`remove_unused_columns=True` 按形参名删数据列且只 `logger.info` 提示；**对 Transformers/PEFT 模型它就是 Tier C 的原生循环，必须用、不许重写**——但那两条机制在自定义 `PreTrainedModel` 上仍可能咬人：走 TRL 标准数据格式时 `_prepare_dataset` 覆写规避了这两条，走自定义列名/自定义 forward 签名时不被规避，这个边界正是自定义架构最容易踩的位置。Keras 3 的 `train_step` 覆写是 backend 特定的。MosaicML Composer 契约最严但 13 个月无 release，不建议新项目采用。

## 石油/领域专用（已排除，见 `borrow-existing-pipeline.md` 的两层分离方案）

`petroflow`/`deepfield`/`seismiqb` 已 404 或 CC-BY-NC 禁商用；`Skoltech-CHR/DeepField` 已 archived 且 `torch.no_grad:`（漏括号）导致验证/早停路径从未被执行过；`hiesabx/reservoirflow` 的 PINN 全版本都是 `NotImplementedError` 空桩；`equinor/ert` 真实活跃但无训练循环、模型靠 shell 子进程调用（GPL-3.0）；`lasio`/`welly`/`dlisio` 只是解析器不是 pipeline。唯一近似替代：`NVIDIA/physicsnemo`，`class MyModel(physicsnemo.Module, register=True)`，但 swap 点在 `examples/` 参考代码里，无 API 稳定性保证。
