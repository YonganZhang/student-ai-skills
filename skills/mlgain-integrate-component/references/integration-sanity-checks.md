# S8 Wiring Gate：集成后的机械检查（门禁，不是建议）

这些检查回答"这个模块有没有被正确地接进去"，**不回答**"这个模块加了以后准确率有没有变高"——后者是 `controlled-comparison.md` 的事。顺序很重要：**先过完这里的检查，再谈消融，否则"没提升"这个观测结果没法归因**。全部结果记具体数字，不写"看起来正常"。

## 门禁：以下七项全绿，才允许进入 `controlled-comparison.md`

### 1. 注册与优化器一致性（对应 `mechanistic-diagnosis.md` P1）

`named_parameters()` 前后diff、`state_dict()` 键diff、optimizer可训练参数总量与模型可训练参数总量必须相等（optimizer在模块构造前建好会导致对不上）。用 `scripts/probe_hooks.py` 的 `assert_new_params_registered()`。

### 2. 前向shape/dtype检查

单独跑一次前向传播，打印插入点前后的张量shape和dtype，确认跟契约一致。不要只看"程序没报错"就当通过——广播会掩盖形状不对的问题。

### 3. 梯度检查（⚠️ 已修正，见下方"不要误判"）

跑一次backward，检查新增参数的梯度：不能全部长期为NaN/Inf；梯度量级跟模型里其他层的梯度量级在合理范围内（差几个数量级通常意味着初始化或学习率不合适）。用 `scripts/probe_hooks.py` 的 `assert_gradients_reach()`（**在 `loss.backward()` 之后调用，不要在函数内部再调一次backward**，否则会因为图已释放而报错）。

**⚠️ 不要用"梯度不能全为0"作为唯一判据**：ReZero（`alpha=0`）首步核心分支参数`F`的梯度确实为0，这是设计如此；LoRA零初始化（`A`随机、`B=0`）首步`grad(A)`可为0；ControlNet的zero conv上游分支首步梯度可为0。这些是正常的零初始化技术行为，不是接线错误。**做2-3个optimizer step后再检查"解锁后"的梯度是否符合预期模式**，详见 `residual-gating-safe-integration.md`。

### 4. Identity/No-op 退化测试

把新模块替换成恒等映射（或用开关关掉），模型输出应退化回接入前的baseline（数值上接近，浮点误差范围内）。关掉后输出**没有**退化回baseline，说明集成代码本身改动了不该动的路径——回去检查集成代码，不是模块的问题。只有这条通过，"模块打开vs关闭"的对比才是干净的单变量消融，见 `controlled-comparison.md`。**这条只是 `function-preserving-socket-protocol.md` 里S1（hard bypass）/S2（enabled no-op）两层验证的简化版**：真正区分"完全不执行"和"执行但零贡献"两种对照，请走那份协议的完整四阶段。

### 5. 输出分布/尺度检查

打印插入点前后张量的均值/方差/极值，确认新模块输出量级跟相邻层匹配。新模块输出量级跟residual stream差好几个数量级，会导致训练不稳定或被后续归一化层"吃掉"——这种情况下测出"没提升"，原因是数值尺度不匹配，不是模块设计本身无效。

### 6. 批次组成等价性 + 独立变量可达性

**批次组成等价性**（单卡版的P22）：同seed、同数据，跑(a)一步batch B与(b)N个累积步各batch B/N，loss与每个梯度张量必须在浮点容差内相等。HF真实踩过这个bug：loss按micro-batch先做mean再平均，而不是跨micro-batch求和再除以总非padding token数——**不报任何错**，修法是`reduction="sum"`再除`num_items`。凡是组件或损失内部有**隐式耦合batch组成的reduction**，batch被换一种方式切开的瞬间就静默失效：BatchNorm、任何per-batch归一化/白化、in-batch-negative对比损失、per-batch top-k或capacity-based MoE路由、任何自己做mean的自定义损失。成本是一对额外的forward/backward，放在这里两列都必做，不放分布式附录。

**独立变量可达性断言**（Curie）：现有第1-5项检查的都是**你在探针脚本里构造出来的那个model对象**，没有一条证明arm的config里那个"要不要加这个模块"的flag**真的到达了训练入口内部的构造点**——失效时产出一个与baseline逐字节相同的实验臂，读起来正好是"这个模块没用"。做法：把声明的科学变量从CLI/config一路追到构造点（含嵌套脚本），并让训练进程**从内部**打印自己解析后的config+断言构造出的模型flag一致。

### 7. 形状扫描 + 确定性检查

**形状扫描**：在一组不同输入形状上跑换入的组件，而不只是训练时那一个固定形状——第2项检查警告过广播会掩盖形状错但没有对应的测试，这条补上。

**确定性检查**：同输入同seed跑两次，输出必须逐位相同。否则组件悄悄引入的非确定性状态（比如未固定的dropout mask生成方式、未同步的CUDA非确定性算子）会以假的seed方差出现，直接污染`controlled-comparison.md`的方差带——分不清是真实trial variance还是组件本身不确定。

## 三条可执行的断言测试（做成 `tests/test_integration_<component>.py`）

1. 新模块参数一步训练后必须改变（`test_new_module_params_update`）。
2. 该冻结的参数必须没变（`test_frozen_params_dont_update`）。
3. `loss@init` 非零且无NaN/Inf（`test_loss_nonzero_at_init`）。

GPU场景显式传device，避免后端不匹配报错。PyTorch Lightning用户有三个现成flag直接对应这三项检查：`fast_dev_run=True`（单batch端到端跑通）、`overfit_batches=10`（微量过拟合）、`num_sanity_val_steps=2`（sanity check）。

## 借用 pipeline 场景专属：冒名顶替测试

第4项identity测试回答"新模块关掉后能不能退回baseline"，测的是**模块**。如果这条pipeline是从外部包借来的（见 `borrow-existing-pipeline.md`），在换真模型之前还要多一条，测的是**宿主接线**：

通过该包的swap机制塞进一个**结构上等价于其内置模型**的自定义类。**🔴 不要用组合（自定义类内部持有一个内置模型实例并在forward里透传）**：`borrow-existing-pipeline.md` 的 B4' 已用真实执行证实，这种写法在 Lightning 宿主（pytorch-forecasting/neuralforecast 等所有 Tier B 包）上会静默丢掉被重写的非 `forward()` 钩子（如 NBeats 的 `step()` 里的 backcast loss），指标变化小到 0.055% MSE delta 却完全不影响判据通过。**唯一可靠的写法是继承（inheritance）**：自定义类直接子类化内置模型类。同seed跑一遍。

- **通过判据**：预测数组与golden run（`_tests/_artifacts/golden_*.npz`）**位级相同或落在已声明的浮点非确定性算子误差范围内**（如 cuDNN 非确定性卷积）——不要写"训练随机性范围内一致"，实测同一个 seed 跑两次 golden run 得到的预测数组本身就是位级完全相同（diff=0.0），根本不存在"训练随机性范围"这回事，也就不该拿它当容差。
- **不一致=swap接线错了，不是架构问题**。常见根因：batch/seq维序反了、输出忘了按约定reshape、忘了反归一化导致输出停在标准化空间、forward形参名跟框架的batch键不匹配被静默丢弃、类名撞上了框架里基于名字子串的特判路由、**用了组合而不是继承，导致被重写的非forward钩子悄悄丢失**。
- 只有这条通过，`controlled-comparison.md` 的对照物才允许是golden run。
- 完整因果验证和边界条件见 `borrow-existing-pipeline.md` 的 B4' ——这里只放判据本身，避免两处各写一份容易再次失步。

## 可直接调用的实现

- `scripts/module_probe.py`：残差插座（硬关闭、零初始化）、第 0 步等价、优化器成员、有效贡献钩子、参数更新量、选点暴露判定。
- `scripts/train_sanity_checks.py`：严格重载往返与 eval 一致性、解冻后优化器覆盖、冻结审计（装了 torchinfo 时附逐层表）、按训练变换的小样本过拟合循环、局部变量快照（改写自 RD-Agent `debug_info_print`）。
- `scripts/alignment_probe.py`：真实批次叠图、标签处信号与行列互换反向对照、增强同步。
- 测试：`tests/test_dl_probes.py`（含"故意写错必须报错"的反例）。项目把这些检查写进[项目合同](../../share-autoresearch-engine/references/workflow/project-contract.md)第 6、7 节。

## 全部通过之后

把每一项的结果（含具体数字）填进 `integration-report-template.md`，然后才能进入 `controlled-comparison.md` 的消融流程。
