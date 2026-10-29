# 学术数据下沉：实证案例与类比领域

用途：向用户解释为什么元数据空、低 vote 的候选也不能跳过，或需要举例说明搬运链时读。原则本身见入口 §0。

## Why（实证血案）

**FPV 案例**：Kaggle `muraakhil2001/high-resolution-floating-solar-pv-data` 元数据全空 / 18 下载 / 1 vote，凭这俩信号判垃圾被跳过。**它实际是 NREL/DOE OEDI 6179（DOI 10.25984/2441306）真实学术数据的搬运** —— 4 个 FPV 站 + 2 陆地共址对照 / 2 年 1 分钟 / 4.5 GB / CC-BY 4.0。一周 proposal 工作建在错误的"FPV 数据稀缺"假设上。

**类比领域**（教训通用）：
- **医学**：Kaggle 匿名肺结核数据 → 可能是 WHO TB 数据库 / NIH ChestX-ray 截断版
- **气候**：低票数 ERA5 子集 → 可能是 ECMWF 哥白尼计划搬运
- **金融**：匿名股票 OHLC → 可能是 Yahoo Finance / Quandl 搬运
- **基因组**：Kaggle 测序数据 → 大概率 GEO / SRA 搬运
