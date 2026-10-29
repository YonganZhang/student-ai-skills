# 真实性 EDA：模态插件与反模式

用途：步骤 4 通用必检（见入口 4.1）之后，按候选数据的模态选对应插件；先识别模态再选，不要全部套用。

## 模态插件

按 cwd 数据模态选择（**先识别数据模态**：tabular / time-series / image / text / geospatial / omics / multimodal / simulation）。

### 时序 (time-series) 插件
- 频率 / 间隔均匀度 / 时区
- 周期性（昼夜 / 季节）
- 滞后相关结构
- 传感器断点
- **基于领域预期列出可检验关系**（不写死 r > 0.5）：例 PV "irradiance vs power 应 r>0.7"，例 ECG "心率 vs 时间应有正常变率"

### 图像 (image) 插件
- 分辨率方差
- 通道分布
- EXIF 元数据（是否被异常剥离）
- 重复图（perceptual hash）
- 标签泄漏（train/test 重叠）

### 文本 (text) 插件
- 词表分布 / 词频 Zipf
- 序列长度异常
- 重复段
- 语言识别一致性

### 地理 (geospatial) 插件
- 坐标系 / 投影
- 空间范围
- 栅格分辨率
- 再分析版本（ERA5 v1 vs v2）

### 医学 (medical) 插件
- DICOM metadata 完整性
- 患者级 split（防数据泄漏）
- 脱敏标记
- 类别不均衡

### 组学 (omics) 插件
- 样本元数据（reference genome / batch / cohort）
- 测序深度分布
- 重复样本（technical vs biological replicate）

### 模拟 / 合成 (simulation) 插件
- 是否显式标 synthetic
- 参数化模型来源
- 真实-合成混合比例

## 关键反模式

🔴 **第一次 EDA 看 r 低就判合成** — 必须先清洗 sentinel 再验（实证：OEDI 6179 32767 sentinel 清洗前 r=0.009，清洗后 r=0.85+）
🔴 **没识别数据模态就跑物理合理性检验** — 时序检查套到图像数据上必然失效
🔴 **凭单次 EDA 失败就判 dataset 弃** — 字段问题先查 metafile / README / 联系作者
