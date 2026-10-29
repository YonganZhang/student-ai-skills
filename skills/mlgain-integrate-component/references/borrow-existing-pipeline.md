# 借用现成 Pipeline：先把宿主接对，再谈换模型

核心命题：agent 引入 subtle bug 的高发区不是模块本身，而是它顺手重写的那条 data/training pipeline。已有官方/可信包的 pipeline 是**已经对过的**，正确做法是借那条 pipeline，只换模型定义。**顺序不可颠倒——跳过 P4 直接换模型，测出的任何结果都无法归因。**

## P0 — 选包（≤15 分钟，不许发散调研）

1. 把任务归成一个通用形状，不按业务领域搜包：面板时序预测 / 图结构时序 / 带缺失时序 / 序列分类 / 图像分类-backbone / 语义分割 / 目标检测 / 视觉异常检测 / PDE-代理 / 纯训练循环标准化。
2. 查 `pipeline-package-catalog.md`，取该形状排名第一的包。只有以下情况才考虑备选：数据容器与你的数据形状明确冲突、需要备选独有的能力、许可冲突（AGPL/GPL/CC-BY-NC）。
3. 写下一句选择理由 + 一条 kill criterion（例："如果 P4 打不过 seasonal-naive baseline，就换另一个包"）。

## P1 — 取用：install 还是 vendor

| 条件 | 决策 |
|---|---|
| 有 pip 包且 swap 点是公共 API | `pip install <pkg>==<精确版本>`，写进 requirements，装到项目自己的虚拟环境（如 `<项目环境目录>/<name>`） |
| 没有 pip 包、或 swap 点是私有 API、或有安装墙 | **vendor**：`git clone` 到 `_vendor/<pkg>/`，记录 `git rev-parse HEAD` 到 `_meta/_registry.yml`，`_vendor/<pkg>/VENDOR.md` 写来源/SHA/日期/改动文件清单 |
| 只想借"参考脚本" | 复制那一个目录到 `_vendor/`，视为一次性冻结起点，不追上游 |

必做：clone/装完立刻记录 commit SHA 或版本号——后面所有 golden run 数字只在这个 pin 下有效。

## P2 — 找出包的数据格式约定，把用户数据转过去

不要凭印象猜格式：

1. `grep -rn "class .*Dataset\|class .*DataSet\|class .*DataModule" <pkg>/` 定位规范数据容器，读它的 docstring/`__init__` 签名。
2. 跑一次包自带的玩具数据，打印真实结构（这是"看一线数据"，不是看文档）：`.head()`、`.dtypes`、形状、索引、取值范围，贴进集成报告。
3. 写一个文件 `data/to_<pkg>_format.py`，只暴露 `to_<pkg>(user_raw)`，内置三条断言：**结构断言**（转出来的对象能被包自己的构造器接受）、**往返断言**（`inverse_transform(transform(x)) ≈ x`，相对误差 <1e-5）、**对齐断言**（随机抽 3 条原始记录，人工比对转换后的位置和数值，不许只看聚合统计）。

## P3 — 定位精确的 swap 点

先判定属于哪一类，再确认：

| 类型 | 识别命令 |
|---|---|
| A. ABC 子类 | `grep -rn "@abstractmethod\|raise NotImplementedError" <pkg>/` |
| B. 构造注入 | 读训练器/引擎 `__init__` 签名找 `model`/`model_class`/`arch`/`backbone` 参数 |
| C. registry/dict | `grep -rn "register_module\|register(\|REGISTRY\|entry_points" <pkg>/` |
| D. 文件名约定 | 读 exp/runner 里有没有 `os.listdir`/`importlib.import_module` |
| E. 配置字段 | `grep -rn "_target_\|class_path\|type=" <pkg>/configs <pkg>/docs` |

**确认这一步做完的判据**：你能指着源码里具体一行说"我的模型在这里被实例化/被调用"。找不到这一行就不要往下写代码。定位完，对**宿主的 swap 契约**（不是候选组件）跑一遍 `extract-interface-contract.md`。

## P4 — 🔴 关键步骤：验证借来的 pipeline 本身接对了（换模型之前）

全部用包自带的原装模型跑，一行模型代码都不许改。

- **B1 原装闭环**：包自己的示例数据 + 自己的内置模型，按官方 quickstart 跑一遍记指标。落不进官方声明范围 → 是环境问题（版本/CUDA），先修环境。
- **B2 换数据不换模型**：接上 P2 的适配器，用户数据 + 仍是内置模型。同时算一个平凡基线（时序：seasonal-naive；分类：多数类；分割：全背景）。**内置模型必须显著优于平凡基线，打不过就停**——这是数据适配器接错的最强信号（列错位、时间未排序、标准化在 split 之前做、mask 语义反了）。
- **B3 微量过拟合**（Karpathy overfit-one-batch）：1 个 batch，关掉全部正则，训到底。train loss 必须掉到接近 0，掉不下去就停——loss/mask/标签对齐/缩放反变换里有 bug。
- **B4 泄漏与因果探针**（三个子探针判别力完全不同，不要平列使用——已用合成实验验证，其中一条原判据是真实危险）：
  - **B4a 前移探针——唯一有判别力的一个，必跑，但有一条前置条件（2026-08-29 真实执行发现，会假阳性）。** target 整体前移1步，让target落进输入窗口。它测的不是"变好没有"，而是**这条pipeline在这份数据上的天花板**（任务退化成copy，误差趋近0）。判据是`scripts/probe_hooks.py`的`ceiling_gap()` = `MSE_base / MSE_前移`：接线正确时应有数个数量级；**`ceiling_gap≈1` = baseline已经贴在天花板上 = 输入窗口里已经含有target，是泄漏**。已合成实验验证（因果时序预测任务，泄漏为窗口起点off-by-one）：正确接线1566~6315倍，泄漏0.7~1.6倍，多个随机种子下两组数值区间完全不重叠。**前置条件——先确认两件事，否则会误判一条本身正确的pipeline为泄漏**：真实执行 pytorch-forecasting 自己的官方 quickstart（结构上正确）测得 `ceiling_gap` = 0.9971（前移1步）/ 0.6754（前移20步），落在文档自己声明的"泄漏"区间内，原因是①预测horizon越长，前移1步只让1/horizon的解码步真正落进输入窗口内，horizon=20时19/20步仍未见到target，判别力被稀释；②更根本的是如果`target`同时出现在`time_varying_unknown_reals`里（即target是它自己的历史特征），前移target会连带把这份历史特征也前移，天花板判断的前提"只动了target"不成立。跑B4a前先确认：horizon是否够短（或分horizon段分别测）、target是否同时是自己的unknown-real特征——是就先移出该特征或换用专门构造的诊断数据集，不要直接对生产用的完整pipeline跑。
  - **B4b 后移探针——⚠️ 只看单调性，绝不要拿"退化到平凡基线"当判据。** 这条原判据（"必须退化到平凡基线水平"）经实测证实是**真实危险的错误判据**：后移1步只是把h步预测变成h+1步，自相关序列本来就还剩大量可预测性，正确pipeline实测只从健康水平小幅下降，离平凡基线差得远——**照旧判据会误判正确pipeline有问题**；更危险的是，**泄漏pipeline在后移探针下反而"看起来健康"**（后移恰好抵消掉泄漏的那一步，读数与正确pipeline的健康基线几乎相同）。**只跑后移探针会把泄漏放行，这是本skill目前已知最危险的一处旧判据，如果之前只靠这条下过"无泄漏"的结论，视为未验证。**
  - **B4c 打乱探针——保留，但它不测泄漏。** 实测正确/泄漏两条在打乱后都退化到接近平凡基线、差值小于跨seed噪声，**零判别力**。真实用途是校准平凡基线数值、并证明target管线与指标代码确实连在一起（不是算了个跟target无关的数）。
  - 报告里记`ceiling_gap`的**具体数值**，不要只记"通过"。时序+全局池化/全局注意力的宿主尤其要做B4a。
- **B5 反变换与量纲检查**：`predict()` 输出必须回到原始物理单位，打印 min/max/mean 跟 ground truth 比量级。
- **B6 冻结 golden run**：固定 seed，把 B2 的预测数组（不只是指标）存成 `_tests/_artifacts/golden_<pkg>_<builtin_model>.npz`，连同包版本/SHA、超参、指标、日期。这是后面所有对比的锚点。
- **B4' 冒名顶替测试**（借 pipeline 场景专属的 identity 测试）：换真模型之前，先用 swap 机制塞一个结构上等价于内置模型的自定义类。**🔴 2026-08-29 真实执行发现：文档曾经给的"最省事"写法（自定义类内部持有内置模型实例，forward 里透传）在 Lightning 宿主（pytorch-forecasting/neuralforecast 等所有 Tier B 包）上会静默失败，不要再用。** 组合（持有实例+forward透传）只转发了 `forward()`，没有转发内置模型被重写的其它 Lightning 钩子——真实复现：NBeats 把 backcast loss 项写在被重写的 `step()` 里，组合写法把这部分损失丢了，指标看起来几乎没变（MSE delta 仅 0.055%、rel-L2 0.4%），**如果按旧判据"训练随机性范围内一致"去检查会直接判定通过**。因果验证是硬控制，不是推断：内置 NBeats 把 `backcast_loss_ratio` 设成 0.0 单独重跑一次，MSE 与冒名顶替跑出来的数字**位级完全相同（0.0 diff）**——即组合版本等价于把这项损失关掉了。补丁式修复（把 `step()` 也一并委托转发）本身也不可用，实测直接崩：`MisconfigurationException: You are trying to self.log() but it is not managed by the Trainer control flow`——**这意味着组合（composition）在任何 Lightning 宿主上都不是可用选项**。**唯一可靠的写法是继承（inheritance）**：自定义类直接子类化内置模型类，只重写你要替换的那部分——实测继承写法的预测数组与 golden run **位级完全相同**（`np.array_equal` 为 True）。
  **判据本身也要改**：旧文档说"指标/预测数组必须在训练随机性范围内一致"——这个说法本身有问题，实测同一个 seed 跑两次 golden run 得到的预测数组是**位级完全相同（diff=0.0）**（192线程与4线程下都一样），**根本不存在"训练随机性范围"这回事，也就不该拿它当容差**。正确判据：预测数组必须与 golden run **位级相同或在浮点非确定性算子已知的极小误差范围内**（如 cuDNN 非确定性卷积；这类情况要显式声明用的是哪个非确定性来源，不能笼统写"随机性"）。**不一致 = swap 接线错了，不是架构问题**：常见根因除了维度顺序反了、输出忘了按约定 reshape、忘了反归一化、forward 形参名跟框架的 batch 键不匹配被静默丢弃之外，**现在要新增一条：用了组合而不是继承，导致被重写的非 forward 钩子（Lightning 的 `step`/`training_step`/`validation_step` 等）悄悄丢失**。只有这条通过，才允许把真正的候选模型放进同一个 swap 点。

## P5 — 换入候选模型，交回原有 SOP

宿主 pipeline 已被证明正确，唯一变量回到"模型定义"，落回本 skill 主链路：`extract-interface-contract.md`（这次对候选组件）→ `architecture-placement-theory.md` → `feature-and-data-reasonableness.md` → `compatibility-check.md` → `integration-sanity-checks.md` → `controlled-comparison.md`（对照物是 B6 的 golden run，不是随手跑的 baseline）→ `integration-report-template.md`。

## 石油领域：两层分离

不存在可借的石油专用 pipeline 包（petroflow/deepfield 已 404 或 CC-BY-NC，DeepField 已 archived 且验证逻辑有 bug 从未真正执行过，reservoirflow 的 PINN 是空桩）。做法：**石油知识全部下沉到一个 data adapter 文件，pipeline 层一律用通用包**。

| 石油任务 | 通用形状 | 借哪条 pipeline |
|---|---|---|
| 单井/多井产量、递减曲线预测 | 面板时序+静态协变量+时变已知协变量 | pytorch-forecasting 或 neuralforecast |
| 井间干扰/注采井网 | 图结构时序 | tsl (Torch Spatiotemporal) |
| ESP/抽油机/SCADA 故障预警 | 传感器遥测异常检测 | PyOD（`pipeline-package-catalog.md` T6，逐点分数默认）；只有交付物必须是带 severity 的异常区间时才用 Orion（T7，注意 <3.12 的 Python pin）；若已是图像/热像图用 Anomalib |
| 测井曲线岩性/相分类 | 序列集合分类 | aeon（T4，默认；注意需 Python≥3.11 独立 env、X 是集合形状）；要 PyTorch 深度模型走 tsai（T5）|
| 油藏数值模拟代理 | 网格张量/mesh-graph | NVIDIA physicsnemo |

`data/petro_adapter.py` 只做：I/O（LAS→lasio，DLIS→dlisio，ECLIPSE→resfo/res2df）、实体映射（井→unique_id/图节点）、**协变量分类**（static/known-future/unknown-past——把"注入速率是 known 还是 unknown"搞错就是典型泄漏）、时间轴规整、单位换算。**绝不进入训练循环**。石油领域知识（递减规律、水驱物理、渗流假设）走油藏领域知识技能 `petro-knowledge`（可选，本包未包含）；本 skill 只管"pipeline 从哪借、怎么接对"。
