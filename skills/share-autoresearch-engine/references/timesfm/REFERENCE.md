---
name: timesfm (archived under share-autoresearch-engine)
description: "Google TimesFM 零样本时序预测：气候、FPV/光伏、能源负荷、传感器序列。触发：TimesFM、zero-shot forecasting、时间序列预测；静态回归不走。"
license: Apache-2.0 license
tags: [sci, forecasting, time-series, foundation-model]
allowed-tools: Read Write Edit Bash
metadata:
  skill-author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  skill-version: "1.0.0"
  upstream: https://github.com/K-Dense-AI/scientific-agent-skills
---

# TimesFM 时序预测

## 定位

TimesFM 是 Google Research 发布的解码器时序基础模型，**零样本**即可预测单变量时间序列（点预测 + 分位数区间），无需训练。本 skill 封装安全的本地推理流程（含预检、covariates、异常检测）。

## 用户常见场景

- FPV（漂浮光伏）发电功率滚动预测
- 气候/温度/降水等 ERA5 派生序列短期预报
- 城市电力负荷、储能调度场景
- 传感器异常检测（基于分位数区间）

## 工作流

0. **凭证**：下载权重需要 Hugging Face 时用 `huggingface-cli login` 配置自己的 token（不要把 token 写进脚本、日志或仓库）
1. **预检系统**（先跑，避免 OOM）：`scripts/` 下的 preflight 脚本
2. **安装**：`uv pip install timesfm`（笔记本 RTX 4060 可用 cu121 PyTorch）
3. **最小调用**：
   ```python
   import timesfm
   tfm = timesfm.TimesFm(...)
   point, quantiles = tfm.forecast([series])
   ```
4. **加协变量**：`timesfm[xreg]` 扩展
5. **异常检测**：用 10%/90% 分位数 + 三档严重度

## 路由

| 想知道 | 读 |
|---|---|
| 详细 API 签名 / ForecastConfig 参数 | `references/api_reference.md` |
| 数据准备（频率对齐、缺失值、长度约束） | `references/data_preparation.md` |
| 硬件 / 显存 / 模型版本对照 | `references/system_requirements.md` |
| 示例（CSV 批量、covariates、anomaly） | `examples/` 下脚本 |
| 预检 / 安装辅助脚本 | `scripts/` |

## 硬件（笔记本）

- RTX 4060 8GB：可跑 TimesFM 1.0 / 2.0 base；超长 horizon 注意显存碎片
- CPU 退化可用，单序列 ~秒级；批量可用 Apple MPS / CUDA

## 与其他 skill 关系

- 画预测结果曲线 → `share-sci-plot`（可选，本包未包含）
- 预测 vs 真实的统计评估 → `share-sci-write/tools/statistical-analysis`（可选，本包未包含）
- 大规模 ERA5 / CMIP6 数据后端 → `share-autoresearch-engine/references/zarr`
- FPV 选址空间分析 → `share-sci-plot/references/geopandas`（可选，本包未包含）

## 注意

- 上游仓库：K-Dense-AI/scientific-agent-skills（Apache-2.0）
- 本地保留了 scripts/ 和 examples/，首次使用先跑 preflight
