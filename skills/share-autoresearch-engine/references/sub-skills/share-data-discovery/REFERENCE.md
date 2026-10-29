---
name: share-data-discovery
description: "跨平台查找并验证数据集真实性。"
metadata:
  parent: share-autoresearch-engine
  type: subskill
  version: v2
  created: 2026-05-16
  reviewed_by: [codex, gemini]
---

# 数据调研 — 召回优先 + 真实性多模态验证

## 0. 核心原则（不变）

**召回率 > 精确率**。先广捕 30-50 个候选数据集（**强制最少 30**），再用真实性 EDA 验证。**永远不要凭单一信号过滤数据集**（votes / description / 下载量 / 上传时间 / 星级 / Tier 等级）。

### 学术数据下沉原则（Academic Data Trickle-down）

权威机构的数据集经常被社区用户搬运到 Kaggle / HuggingFace / GitHub，**搬运过程会丢失原元数据** —— Kaggle 上一个 description 空、低 vote 的 dataset 可能是 NREL / WHO / CERN 真金。**判垃圾前必须先做同名反向追踪到权威源**。这是本 skill 的核心洞察，跨能源 / 医学 / 气候 / 社科 / 金融全适用。

实证案例（FPV 搬运 OEDI 6179）与医学 / 气候 / 金融 / 基因组类比：`references/trickle-down-cases.md`（需要向用户举例解释时读）。

## 1. 步骤 1 — 关键词扩展阻塞 gate（搜前必做）

**强制 gate**：在调用任何搜索工具之前，**先输出 Markdown 表格**，否则视为本 skill 执行失败。

### 1.1 必输出表格格式

```
| 类 | 关键词（至少 3 个，含中英 + 缩写全称 + 学术 vs 工业 / 黑话）|
|---|---|
| 同义词 | <≥3 词> |
| 上下位词 | <≥3 词> |
| 反向查询 | <≥3 词组 — 含"X benchmark"/"X data availability"/"X dataset paper">|
| 邻接领域 | <≥3 词> |
| 任务词 | <≥3 词 — forecasting/segmentation/detection/classification>|
| 数据类型词 | <≥3 词 — tabular/time-series/image/text/geo/omics> |
| 机构 / 资助方 | <≥3 词 — NREL/NIH/CERN/IEA/WMO/ESA>|
| 文件格式词 | <≥3 词 — csv/parquet/zarr/nc/dicom/hdf5>|

总计 ≥ 24 词，**严禁少于 12 词进入下一步**。
```

### 1.2 必输出布尔查询模板（每平台一份）

```
Kaggle:    "<同义词1>" OR "<同义词2>" (dataset OR data OR measurements)
GitHub:    site:github.com (<同义词>) AND (dataset OR data) AND (csv OR parquet)
Scholar:   "<task>" "<domain>" benchmark OR "data availability"
政府站点:  inurl:.gov "<同义词>" data
```

### 1.3 搜索日志（强制记录）

每轮记录：关键词 / 平台 / 命中数 / 保留数 / **若有排除：必须给出具体理由**（不许"看起来质量低"这种笼统理由）。

## 2. 步骤 2 — 多源广捕（Tier 0 → 4，每平台**必查 + 必保留候选**）

⚠️ **关键纪律**：每个 Tier 至少跑 1 个 query；查到候选 **必须进清单**，不得在此阶段以任何理由淘汰。**目标：30-50 候选**（极窄领域可放宽到 ≥15，必须明示理由）。

| Tier | 类别 | 代表平台 | 本步要点 |
|---|---|---|---|
| 0 | 元搜索引擎（最先跑，破单一平台孤岛） | Google Dataset Search / Mendeley Data / DataCite Commons / BASE | 直接搜，crosswalk 多平台 |
| 1 | 政府 / 学术权威 + 区域权威 + 垂直注册表 | OEDI / data.gov / NASA POWER / NASA Earthdata / Zenodo / Figshare / IEEE DataPort / Harvard Dataverse / OpenAIRE | 区域 / 国际官方源按 §7 地理范围动态选择；垂直领域权威按数据模态 / 领域**强制补充至少 3 个** |
| 2 | 商业比赛（赞助方真业务数据） | Kaggle Competitions / DrivenData / Zindi / AIcrowd / CodaLab / Numerai | ⚠️ Kaggle Competitions 跟 Datasets **独立两条路** |
| 3 | 社区上传（混质，**必查 + 必反查源**） | Kaggle Datasets / Hugging Face Datasets / GitHub / OpenML | 元数据空 → **必反查 Tier 0/1 同名** |
| 4 | 论文逆向（最稳，慢） | paperswithcode / Google Scholar / Semantic Scholar / OpenReview / arXiv | 论文 + code + dataset 三件套、"Data Availability" 章节、supplementary |

每次步骤 2 选平台时读 `references/sources-tier-table.md`：完整 URL、覆盖范围、搜索语法、区域 / 国际官方源清单、垂直领域注册表与跨平台搜索顺序。

## 3. 步骤 3 — 同名反向追踪 SOP（**只用于溯源 + 评级，绝不删除候选**）

⚠️ **纪律**：反向追踪的输出**只能**是"原始权威源 URL / DOI / 引用"，**不能**作为删除任何 Tier 3 候选的理由。所有 Tier 3 低信号候选必须保留入清单，标注"待 EDA 验证"。

```
对每个 Tier 3 候选:
  1. 标题搜 Tier 0/1（Google Dataset Search / OEDI / Zenodo / 各领域权威）
  2. 标题 + 关键作者 / 机构 → Google Scholar
  3. 找到权威源 → 切换到原始源（搬运可能丢 metadata、license 更清晰）
  4. 找不到权威源 → 候选**保留**，标"⏳ 待 EDA 验证（source 待溯源）"
```

## 4. 步骤 4 — 真实性 EDA（通用必检 + 多模态插件）

⚠️ **纪律**：每个候选**都要跑通用必检**，再按数据模态加插件。**禁止凭主观印象判合成或真**，必须有 EDA 输出支撑。

### 4.1 通用必检（所有数据模态）

| 检 | 内容 | 红旗 |
|---|---|---|
| 文件可读性 | 能否打开 / schema 一致 / 编码无错 | 损坏 / 编码乱 → 弃 |
| 样本量 | 总记录数 / 文件数 / 文件大小符合声称 | 大小差 10× 以上 → 怀疑 sample/搬运 |
| 重复样本 | 行级 / 关键键级重复率 | 极高重复 → 怀疑伪造 |
| 缺失编码 | 是否含 sentinel（32767 / -9999 / -1e9 / 0xFFFF / 65535 / NaN）| 必清洗后再做后续检查 |
| 异常值 | 数值字段 IQR / z-score 极端 | 可能是 sentinel 未清洗 |
| Schema vs 数据字典 | 字段类型 / 单位 / 时间戳 / 坐标系一致性 | 不一致 = red flag |
| License | 是否标 license + 是否允许研究 / 商用 | 无 license → 不可发表 |
| 来源链 | 是否有 source 反推（DOI / 论文 / 机构）| 无 source + 元数据空 = 学术数据下沉嫌疑 |

**模态插件**（时序 / 图像 / 文本 / 地理 / 医学 / 组学 / 模拟）与 EDA 关键反模式：先识别数据模态，再按 `references/eda-modality-plugins.md` 选对应插件跑。

## 5. 步骤 5 — 验证优先级表（**不是过滤等级**）

⚠️ **关键改名**：从 "信任度等级" → **"验证优先级"**。星级**不是**真假判据，是**先做哪个的排序**。

| 优先级 | 类型 | 何时跑 EDA | 决策 |
|---|---|---|---|
| ⭐⭐⭐⭐⭐ | Tier 0/1 政府/权威 | **优先跑**，最可能是主数据 | 通过 → main / baseline 候选 |
| ⭐⭐⭐⭐ | Tier 2 商业比赛 + 论文 supp | 次优先 | 同上 |
| ⭐⭐⭐ | Tier 3 高质量（高 vote + 多 kernel + paper 引用）| 次次优先 | 同上 |
| ⭐⭐ | Tier 3 一般质量 | EDA + 反查源 | 通过 → 辅助 / 对照 |
| ⭐ | Tier 3 低信号（元数据空 / 低下载） | **必跑 EDA + 必反查 Tier 0/1 同名** | **可能是搬运金矿** → 通过反查 + EDA 后可升 ⭐⭐⭐⭐⭐ |

**纪律**：⭐ 级候选**含有以下任一信号则强制进 EDA**：
- 大文件（> 10 MB）
- 真实字段名（含物理单位 / 站点 ID / 时间字段）
- 时间跨度声明（> 1 年）
- 机构名 / 作者背景 / DOI 痕迹
- README / metafile 存在
- license 明确

## 6. 步骤 6 — 决策与召回停止条件

### 6.1 决策树（逐 gate 通过才进下一步）

1. gate 1：关键词表格 ≥12 词输出 → 通过 → 进入步骤 2
2. gate 2：Tier 0-4 广捕（每平台必查必保留候选）→ 候选 ≥30
3. gate 3：Tier 3 候选反向追踪到 Tier 0/1（只溯源不删）
4. gate 4：通用必检 + 多模态插件 EDA → 输出分类（真 / 部分真 / 合成 / 异常）
5. gate 5：按主题相关度 + 验证优先级 → main / baseline / fallback

### 6.2 召回停止条件（不写死 30-50）

**默认目标 30-50 候选**。但召回停止条件可参数化：

- **连续 3 轮新关键词 + 新平台不再产生新候选** → 可停
- **极窄领域**（如 FPV 时序）→ 候选可放宽到 ≥15，**但必须明示"为什么"** + 已穷举哪些平台
- **热门领域**（如 ImageNet 类）→ 候选可超 50，但要分层（benchmark 类 / sample 类 / 衍生类）

## 7. 跨项目参数化（**触发时必先收集这 5 个参数**）

```
1. 研究领域: <能源/医学/气候/石油/社科/金融/...>
2. 数据模态: <tabular/time-series/image/text/geo/omics/multimodal/simulation>
3. 目标任务: <forecasting/classification/segmentation/detection/causal-inference/...>
4. 地理范围: <全球/北美/欧洲/亚太/特定国家/区域>
5. 时间范围: <历史 N 年 / 实时 / 特定窗口>
```

→ 根据参数动态选择 Tier 1 区域权威 + 垂直注册表 + 步骤 4 EDA 插件。

## 8. 反模式（**绝对不做**）

🔴 凭单一信号过滤（votes / description / 下载量 / 上传时间 / Tier 等级）
🔴 只搜 Kaggle / 只搜 GitHub / 只搜 1 个 Tier
🔴 元数据空就跳过（必反查 Tier 0/1）
🔴 EDA 不清洗 sentinel 就判合成
🔴 没识别数据模态就乱跑时序检验
🔴 关键词只用几个直觉词，不输出 ≥12 词扩展表
🔴 找到一个就停（必 ≥30 候选，极窄领域 ≥15 + 理由）
🔴 凭单次 EDA 失败就判 dataset 弃（字段问题先查 metafile / README / 联系作者）
🔴 同名反向追踪当淘汰机制（**只溯源不删**）
🔴 星级当过滤器（**改为验证优先级**）
🔴 凭"想象数据应有什么字段"写 proposal（必须先 EDA）

## 9. 触发协议

任何项目说：找数据 / 数据调研 / 找 dataset；"X 领域有什么公开数据"；验证 X 数据真实性 / X 数据是不是合成；数据可信度 / 学术数据下沉 → 加载本 skill。用户只问"Kaggle / GitHub / HuggingFace 上 X 有数据吗"也要走全流程，不是只查这一个。执行顺序：步骤 1 → 6，逐 gate 见 §6.1。

## 10. 配套资源

- `scripts/data-reality-check.py` — 真实性 EDA 模板脚本（含 sentinel + 物理 + 相关 + 缺失通用四检；模态插件 v2 待加）
- `references/sources-tier-table.md` — Tier 0-4 平台详表（含区域权威 + 垂直注册表）
- `references/keywords-expansion-matrix.md` — 关键词扩展矩阵示例（多领域案例）
- `references/eda-modality-plugins.md` — 步骤 4 模态插件（时序 / 图像 / 文本 / 地理 / 医学 / 组学 / 模拟）+ EDA 关键反模式
- `references/trickle-down-cases.md` — 学术数据下沉实证案例与类比领域

## 11. 关系

- 父技能：share-autoresearch-engine（L1→L2 选题阶段强制触发）
