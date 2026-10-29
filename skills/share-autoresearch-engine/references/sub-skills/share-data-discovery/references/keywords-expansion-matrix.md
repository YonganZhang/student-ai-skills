# 关键词扩展矩阵

任何领域调研，关键词必须扩展到 4 类：同义 / 上下位 / 反向 / 邻接。每类至少 3 词。

---

## 通用扩展规则

| 类 | 含义 | 举例规则 |
|---|---|---|
| **同义词** | 不同社区对同一概念的不同叫法 | 中文 / 英文 / 全称 / 简称 / 学术词 vs 工业词 |
| **上下位词** | 概念层级 | 父类 → 子类 → 兄弟类 |
| **反向查询** | 从结果反推数据 | "做 X 任务的论文用了什么数据" |
| **邻接领域** | 相似 / 互补 | 方法可迁移 / 数据可借鉴 |

---

## 领域案例

### FPV（水上光伏）

| 类 | 词 |
|---|---|
| 同义 | floating photovoltaic / FPV / floating solar / aquatic PV / water-based PV / 漂浮光伏 / 水上光伏 / 浮体光伏 / floating solar farm |
| 上下位 | solar → PV → photovoltaic / 漂浮 → 浮体 → 水面 / 水上 → 海上 → 近海 → 离岸 |
| 反向 | "FPV 出力预测 论文" / "FPV benchmark" / "floating PV machine learning dataset" |
| 邻接 | 陆地 PV / 风电 / 海上风电 / 水电站 / FPV 选址 / FPV 浮体水动力 / 水温 / 水库光伏 |

### 电力负荷预测

| 类 | 词 |
|---|---|
| 同义 | electricity load / power demand / electricity demand / 电力负荷 / 用电负荷 / load forecasting |
| 上下位 | electricity → power → energy / load → demand → consumption / 工业 → 居民 → 商业 |
| 反向 | "load forecasting benchmark" / "电力负荷预测公开数据" / "smart grid time series" |
| 邻接 | 工业能耗 / 居民能耗 / 微电网 / 智能电表 / 电网频率 / 电价 |

### 石油测井

| 类 | 词 |
|---|---|
| 同义 | well logging / petrophysics / wireline logging / 测井 / 测井解释 / 物探 |
| 上下位 | logging → wireline / MWD / LWD / cased-hole / open-hole / petrophysics → reservoir |
| 反向 | "well logging dataset open" / "测井解释 SOTA" / "petrophysics ML benchmark" |
| 邻接 | 地震 / 钻井 / reservoir / lithology / 岩性识别 / 储层评价 / SHAP 测井 |

### 气候时序

| 类 | 词 |
|---|---|
| 同义 | climate time series / atmospheric reanalysis / 气候时序 / 气象再分析 / 大气数据 |
| 上下位 | climate → weather → atmospheric → meteorological / reanalysis → observation → forecast |
| 反向 | "climate forecasting benchmark" / "气候预测 公开数据" / "ERA5 vs MERRA2 ML" |
| 邻接 | 海洋 / 水文 / 农业 / 能源气象 / 极端事件 / 城市气候 |

### 医学影像

| 类 | 词 |
|---|---|
| 同义 | medical imaging / radiology / X-ray / CT / MRI / 影像组学 |
| 上下位 | imaging → diagnostic → screening / radiology → cardiology / oncology |
| 反向 | "medical imaging benchmark MICCAI" / "RSNA challenge data" |
| 邻接 | 病理 / 基因组学 / 临床记录 / 多组学 |

---

## 自检：扩展前的"懒搜"清单

如果你只用了下面这些词，**没扩展**，请回去再扩：

- 直接拼写（如只搜 "floating photovoltaic"）
- 只英文 / 只中文
- 只搜一个 Tier 平台
- 没做反向查询（没找 review paper）

---

## 实证（FPV 案例反思）

示例：一次 FPV 数据调研用了：
- floating photovoltaic ✓
- floating solar ✓
- FPV ✓
- offshore solar ✓
- 水上光伏 ✓

但**没用**：
- aquatic / 水面 / 水库
- "FPV dataset NREL" 等反向查询  ← **没做反向查询导致漏掉 OEDI**
- IEA PVPS Task 11（直接的 FPV 学术报告）
- paperswithcode "floating photovoltaic"

规则：**反向查询 + Tier 4 论文逆向**是召回率的最后一公里。
