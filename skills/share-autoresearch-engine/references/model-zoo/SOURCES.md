# Model Zoo — 来源与授权

> 归档于 2026-08-26。用途：石油/油藏及其他**参数→轨迹**代理建模任务的可复用基线。
> 上游代码为 `--depth 1` 克隆后**剥离 `.git`**（commit SHA 已记录于下表，可按 SHA 复原）。
> 公开技能包不随附 `upstream/`（约 32 MB 第三方代码与数据）；需要时按下表仓库与 commit 自行克隆到 `upstream/<目录>`。

## 上游仓库

| 目录 | 仓库 | Commit | 授权 | 含哪些模型 |
|---|---|---|---|---|
| `upstream/Time-Series-Library` | [thuml/Time-Series-Library](https://github.com/thuml/Time-Series-Library) | `4e938a1767106324dd753b2a44832bf870a0252e` | MIT | **42 个模型**：Autoformer, DLinear, iTransformer, PatchTST, TimesNet, Mamba, Koopa, Crossformer, FEDformer, Informer, Reformer, SCINet, SegRNN, TimeMixer, TimeXer, Nonstationary_Transformer, LightTS, MICN, ETSformer, FreTS, MSGNet, Pyraformer, TiDE, WPMixer, Chronos/Chronos2, Moirai, Sundial, PAttn, KANAD … |
| `upstream/LTSF-Linear` | [cure-lab/LTSF-Linear](https://github.com/cure-lab/LTSF-Linear) | `0c113668a3b88c4c4ee586b8c5ec3e539c4de5a6` | Apache-2.0 | DLinear / NLinear / Linear 原始实现 |
| `upstream/N-BEATS` | [ServiceNow/N-BEATS](https://github.com/ServiceNow/N-BEATS) | `c746a4f13ffc957487e0c3279b182c3030836053` | MIT | N-BEATS 官方实现 |
| `upstream/neuraloperator` | [neuraloperator/neuraloperator](https://github.com/neuraloperator/neuraloperator) | `00b7d86f8d74ff0af55da53eb585fe26df9c71f0` | MIT | FNO / TFNO / U-NO / 神经算子全家 |

## 论文出处

| 模型 | 论文 | 会议/期刊 |
|---|---|---|
| Autoformer | Wu et al., *Autoformer: Decomposition Transformers with Auto-Correlation for Long-Term Series Forecasting* | NeurIPS 2021 |
| DLinear / NLinear | Zeng et al., *Are Transformers Effective for Time Series Forecasting?* | AAAI 2023 |
| PatchTST | Nie et al., *A Time Series is Worth 64 Words: Long-term Forecasting with Transformers* | ICLR 2023 |
| TimesNet | Wu et al., *TimesNet: Temporal 2D-Variation Modeling for General Time Series Analysis* | ICLR 2023 |
| iTransformer | Liu et al., *iTransformer: Inverted Transformers Are Effective for Time Series Forecasting* | ICLR 2024 |
| N-BEATS | Oreshkin et al., *N-BEATS: Neural Basis Expansion Analysis for Interpretable Time Series Forecasting* | ICLR 2020 |
| FNO | Li et al., *Fourier Neural Operator for Parametric Partial Differential Equations* | ICLR 2021 |
| U-FNO | Wen et al., *U-FNO — An enhanced Fourier neural operator-based deep-learning model for multiphase flow* | Adv. Water Resour. 2022 · [arXiv:2109.03697](https://arxiv.org/abs/2109.03697) |
| DeepONet | Lu et al., *Learning nonlinear operators via DeepONet* | Nat. Mach. Intell. 2021 |
| 傅里叶特征嵌入 | Tancik et al., *Fourier Features Let Networks Learn High Frequency Functions in Low Dimensional Domains* | NeurIPS 2020 |

## 🔴 使用前必读：这些模型不能直接搬到"参数→轨迹"任务上

上表绝大多数是 **history → future** 预测器。若你的任务是
**静态参数向量 → 多通道轨迹**（代理模型的典型形状，推理时没有历史序列可编码），
它们的编码器端是空的，必须适配。可复用的适配实现见
[`param_to_trajectory.py`](param_to_trajectory.py)，统一做法是：

> **把历史编码器换成条件向量注入，保留各模型自己的特征机制。**

适配对所有模型一视同仁，横向比较公平；但**不是原生设定**，论文必须声明。

## 🔴 实测结论（Volve/Norne 注水代理，2026-08）

原始记录未随本包发布。一句话结论：**越"高级"的骨干在这个任务上不一定越好**，
FNO 与 DeepONet 都显著输给一个普通的条件化 Transformer。**先跑基线，别先堆模块。**
