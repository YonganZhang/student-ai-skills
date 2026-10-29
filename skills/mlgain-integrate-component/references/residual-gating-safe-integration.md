# 零贡献残差与门控集成

用残差/门控让网络"自己决定要不要用这个模块"是成熟技术家族，**应是条件默认，不是所有组件的无条件默认**。核心认知修正：**"网络有退路"只表示假设空间包含baseline，不保证实际优化器会留在那个点，更不保证测试集泛化不掉分。门可以学到非零但有害的贡献，也可以始终近零，变成"不伤害但没作用"的死分支。**

## 五种真实存在的机制（都有官方实现，不是自创）

| 方法 | 机制 | 初始是否精确baseline | 局限 |
|---|---|---|---|
| Highway Networks | `y = H(x)*T(x) + x*(1-T(x))`，transform gate负bias初始偏向carry | 否；sigmoid只能接近0/1 | 输入依赖门引入额外失败模式；要求同shape |
| ReZero | `y = x + alpha*F(x)`，每层标量`alpha=0` | 是 | 第一步`F`参数梯度为0，先由alpha解锁分支 |
| LayerScale | `y = x + diag(lambda)*F(x)`，每通道小epsilon | 否，但可很接近 | 需选epsilon；优点是分支一开始就有梯度 |
| LoRA式零更新 | `Wx + BAx`，A随机、B=0 | 是，`BA=0` | 首步`grad(B)`可非0，`grad(A)`**恒为精确0**（`dL/dA = s·Bᵀ·Gᵀ·x`，B=0时是恒等式；实测5组seed/256×256全部`allzero=True`）。**关键：`grad(A)`是一个"值为零的张量"，不是`None`**——所以任何只查`p.grad is None`的探针（含`probe_hooks.assert_gradients_reach`）在这里返回空列表、完全不提A。不要指望它替你标出零初始化分支，做法见`scripts/probe_hooks.py`的`assert_zero_init_unlocked()` |
| ControlNet zero conv | 冻结原路，用权重/bias均0的1x1 conv注入新分支 | 是 | 零输出层上游分支的梯度也会延迟一步 |

来源：ReZero (https://proceedings.mlr.press/v161/bachlechner21a.html)、LayerScale (Going Deeper With Image Transformers, ICCV 2021)、Highway Networks (NeurIPS 2015)、LoRA 官方实现 (https://github.com/microsoft/LoRA)、ControlNet 官方实现 (https://github.com/lllyasviel/ControlNet)。

## 两条不同强度的规则

1. **强制**：每个socket都有硬`bypass` mode，不执行candidate，用于baseline路由等价（见 `function-preserving-socket-protocol.md` 的S1）。
2. **条件默认**：当新组件是与原residual stream**同shape/同语义的additive correction**，且baseline路径仍有意义时，默认用零标量、小通道尺度或零输出投影。要精确起点用ReZero/零输出投影；要分支立即有梯度用LayerScale式小epsilon，另用硬bypass做精确parity。

**不应盲目套残差的场景**：下采样/改通道维度；替换loss/head/概率归一化；必须满足硬约束、可逆性或保守性的操作；论文机制必须取代旧操作；再加residual会改变原方法的norm/信息流。这些场景用显式`baseline|replace`切换，尽可能用network morphism/恒等初始化/warm-start（Net2Net的Net2WiderNet/Net2DeeperNet思路）。

## ⚠️ 预期梯度模式（不能要求所有新参数第一步都非零）

这是与 `integration-sanity-checks.md` 的Wiring Gate直接相关的修正：

- ReZero `alpha=0`：首步`grad(alpha)`可非0，`grad(F params)=0`——**这是正常，不是接线错误**。
- LoRA `A=random, B=0`：首步`grad(B)`可非0，`grad(A)`可为0。
- zero output projection：首步projection有梯度，上游分支可为0。

**做2-3个optimizer step后再检查"解锁后分支梯度"是否符合预期**，不要在第0步就下"梯度全为0=没接对"的结论。

## 有用性诊断（区分"死分支"和"有害分支"）

死模块不能只看gate小：**小gate乘很大的raw branch仍可有实质贡献**。同时观测raw branch `z=F(x)`与effective contribution `g*z`两者：记录gate值、`RMS(z)/RMS(base)`、`RMS(g*z)/RMS(base)`、分支/gate梯度、NaN/Inf、死通道，以及**训练后强制force-bypass对指标的差异**。若有效贡献比长期近0、解锁后分支梯度仍为0、且训练后强制bypass对输出/指标几乎无影响，才有足够证据说分支未被使用。

## 落地建议

把"所有组件必须支持硬bypass"写成默认要求（见socket协议），把"零/小尺度残差合并"写成对同形状加性修正型组件的**条件**默认——不要把这两条混成一条无条件规则。代码模板见 `assets/pytorch-component-socket.py`（`ResidualScale`类实现零初始化标量/通道门）。
