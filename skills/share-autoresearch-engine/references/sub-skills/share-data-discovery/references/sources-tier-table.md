# 数据源 Tier 0-4 平台详表

每个领域都至少跑过本表全部 Tier 1 + Tier 2 + Tier 4 一遍才能下"数据稀缺"结论。

---

## Tier 0 — 元搜索引擎（最先跑，破单一平台孤岛）

| 平台 | URL | 用法 |
|---|---|---|
| Google Dataset Search | datasetsearch.research.google.com | 直接搜，crosswalk 多平台 |
| Mendeley Data | data.mendeley.com | Elsevier 旗下，含论文配套 |
| DataCite Commons | commons.datacite.org | DOI 跨平台索引 |
| BASE | base-search.net | 学术资源元搜索（含数据） |

## Tier 1 — 政府 / 学术权威（99% 真实，最高优先）

| 平台 | URL | 主覆盖 | 接入 | 搜索语法 | 注意 |
|---|---|---|---|---|---|
| **OEDI** | data.openei.org | NREL/DOE 能源全谱：太阳/风/电网/建筑/储能/水文 | Web 搜索 + 直链下载 + DOI | `q=<keyword>` URL query | submissions ID 永久（如 6179），可直接 wget |
| **data.gov** | catalog.data.gov | 美国政府开放数据全谱 | Web 搜索 + JSON API | `keyword` 字段 | Publisher 信息看是 NASA/DOE/NIH 哪家 |
| **NASA POWER** | power.larc.nasa.gov | 全球气象/太阳能/水文/农业 | REST API + Web UI | 经纬度 + 时间范围 | 适合做 baseline 气象数据 |
| **NASA Earthdata** | earthdata.nasa.gov | 地球科学 | | | |
| **IEA PVPS** | iea-pvps.org/research-tasks | 国际能源署 PV 任务报告 + 数据 | PDF report + 任务页 supp | Task 11 (FPV) / 13 / 16 重点 | 部分数据需会员，但报告 PDF 全开 |
| **Zenodo** | zenodo.org | CERN 学术开放仓库 | Web + DOI + API | "topic" + 排序 by 引用 | 论文 supplementary 主阵地 |
| **Figshare** | figshare.com | 学术 + 机构 + 个人 | Web + API | 标签 + 引文 | 跟 Zenodo 互补，Springer/Nature 论文 supp 常落这 |
| **IEEE DataPort** | ieee-dataport.org | IEEE 学术数据 | 部分开放部分付费 | IEEE Author + 标签 | 工程类常去 |
| **Harvard Dataverse** | dataverse.harvard.edu | 社科 + 部分自然科学 | Web + API | 关键词 + 学科 | 经济/政策类辅助 |
| **OpenAIRE** | explore.openaire.eu | 欧盟 H2020 项目数据 | Web | 项目编号 + DOI | 欧洲资助论文数据集中 |

### Tier 1 补充 · 区域 / 国际官方源（按项目地理范围动态选择）

| 平台 | URL | 区域 |
|---|---|---|
| UNData | unstats.un.org/unsd/databases.cshtml | 联合国 |
| World Bank Open Data | data.worldbank.org | 世界银行 |
| OECD Data | data.oecd.org | OECD 成员国 |
| WHO Data | who.int/data | 世界卫生 |
| FAO Stat | fao.org/faostat | 联合国粮农 |
| WMO | wmo.int | 世界气象 |
| Copernicus / ECMWF | climate.copernicus.eu, ecmwf.int | 欧洲气候 |
| Eurostat | ec.europa.eu/eurostat | 欧盟统计 |
| UK Data Service | ukdataservice.ac.uk | 英国社科 |
| Australian Data Archive | ada.edu.au | 澳大利亚 |
| 日本气象厅 (JMA) | jma.go.jp | 日本气象 |
| 韩国 KMA | kma.go.kr | 韩国气象 |
| 中国国家数据 | data.stats.gov.cn | 中国统计 |
| 国家青藏高原科学数据中心 | data.tpdc.ac.cn | 中国地球科学 |
| 国家地球系统科学数据中心 | geodata.cn | 中国地球系统 |

### Tier 1 补充 · 垂直领域权威（按数据模态 / 领域**强制补充至少 3 个**）

| 领域 | 平台 |
|---|---|
| **能源 / 电力** | ENTSO-E Transparency, EIA, NREL, OpenEI, Pecan Street, LBNL DataX |
| **医学影像** | TCIA, PhysioNet, MIMIC, OpenNeuro, Grand Challenge, Synapse, BioStudies |
| **基因组 / 组学** | NCBI GEO, NCBI SRA, EBI ENA, GenBank, UK Biobank |
| **地球 / 遥感** | NASA Earthdata, ESA Sentinel, USGS Earth Explorer, NEON, ARM |
| **社科** | ICPSR, IPUMS, Pew Research Data |
| **金融** | Wharton WRDS, Quandl, FRED, BIS Statistics |
| **气候** | NOAA NCEI, NCAR RDA, CMIP archives, BerkeleyEarth |

## Tier 2 — 商业比赛（赞助方真业务数据）

| 平台 | URL | 注意 |
|---|---|---|
| **Kaggle Competitions** | kaggle.com/competitions | ⚠️ 跟 Datasets **完全独立**两条路，必须分别搜 |
| **DrivenData** | drivendata.org | 社会公益（climate / health / energy）+ 学术 |
| **Zindi** | zindi.africa | 非洲 / 新兴市场 |
| **Numerai** | numerai.com | 金融市场（加密数据）|
| **AIcrowd** | aicrowd.com | 学术比赛偏多 |
| **CodaLab** | codalab.lisn.upsaclay.fr | 法国 + 欧洲学术比赛 |

## Tier 3 — 社区上传（混质，必查 + 反向追踪）

| 平台 | URL | 反查策略 |
|---|---|---|
| **Kaggle Datasets** | kaggle.com/datasets | 元数据空 → 必反查 Tier 1 同名 |
| **Hugging Face Datasets** | huggingface.co/datasets | NLP/CV 多，能源/气候/表格在增。**别只搜 NLP 关键词** |
| **GitHub** | github.com | `gh search repos "<keyword> dataset"` / `awesome-X` lists + paper repo |
| **OpenML** | openml.org | 经典 ML benchmark，表格数据为主 |
| **PhysioNet** | physionet.org | 医学/生理信号 |

## Tier 4 — 论文逆向（最稳，慢）

| 平台 | URL | 操作 |
|---|---|---|
| **paperswithcode** | paperswithcode.com | 顶级 — 论文 + code + dataset 三件套 |
| **Google Scholar** | scholar.google.com | 找到的 paper → 看 "Data Availability" / "Methods - Data" 章节 |
| **arXiv** | arxiv.org | 论文 supplementary 链接（ancillary files）|
| **Semantic Scholar** | semanticscholar.org | 比 Scholar 引用图更准 |
| **OpenReview** | openreview.net | ICLR/NeurIPS 等会议论文 + 附件 |

---

## 跨平台搜索的高效顺序

```
新主题 → 1. paperswithcode 看是不是已经有 benchmark
       → 2. Tier 1 政府权威（OEDI / Zenodo）搜同义词
       → 3. Tier 2 Competitions（Kaggle Comp / DrivenData）查商业比赛
       → 4. Tier 3 社区（Kaggle Datasets / HF / GitHub）穷举关键词
       → 5. Tier 4 论文逆向：找 review paper / SOTA paper 看其数据
       → 6. 反向追踪 Tier 3 候选到 Tier 1（同名/同主题）
       → 7. 真实性 EDA 四检
```

---

## 领域特化（FPV 实证案例）

- ✅ **OEDI submissions/6179** — FPV 真金矿（4 站 + 2 陆地共址 + 2 年 1 分钟）
- ⚠️ Kaggle `muraakhil2001/high-resolution-floating-solar-pv-data` = OEDI 6179 搬运
- ❌ Kaggle `datasetengineer/multimodal-coastal-solarpanel-assessment-dataset` = 合成数据（昼夜全 flat / r≈0）
- 📑 IEA PVPS Task 11 (Performance, Operation and Reliability of Photovoltaic Systems) — FPV 报告 + 部分数据
- 📑 paperswithcode 搜 "floating photovoltaic" — 仅个位数 entry，但每个都标了真实数据源
