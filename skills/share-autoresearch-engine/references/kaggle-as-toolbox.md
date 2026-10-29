# Kaggle 当四库用 — 模型库 / 算法库 / 知识库 / 领域数据库

## 核心思想
Kaggle 不是"刷分平台"，而是**最强的 DL 实战 toolbox**：
- **模型库**：现成 weights / notebook / pipeline
- **算法库**：top kernel 里的 trick / loss / 后处理
- **知识库**：discussion 里的 root cause / failure mode / 调参直觉
- **领域数据库**：300k+ 公开数据集，比论文 dataset 大且杂

不试 Kaggle 而自己重新发明 = 浪费 90% 时间。

## 触发时机（任何一条触发即查 Kaggle）

- 接到新 domain / 新 task type → 第一件事查 Kaggle 历史比赛
- baseline 卡住 1 天没新方向
- 想改 loss / arch / 后处理但拿不准
- 用户问"前人怎么解的"
- 怀疑 leakage / 数据问题
- 找现成预训练 weights

## 4 库速查（用 Kaggle CLI / 网页 / API）

### 1. 模型库（Code Competition / Models）

```python
kaggle competitions list -s "<keyword>"     # 找类似比赛
kaggle kernels list -s "<keyword>" --sort-by voteCount
kaggle kernels pull <user/notebook> -p _sandbox/kaggle/<notebook>
# 模型/weights 优先查 Kaggle 网页、HuggingFace、timm/transformers
```

**抄作业流程**：
1. `kaggle competitions list -s` 找 ≤3 个相似 task 的比赛
2. `kaggle kernels list` 按 votes / relevance 找 top notebook
3. `kaggle kernels pull` 下载本地
4. 看 model + augmentation + loss + ensemble 套路
5. 改成自己 task 的 input shape → 嫁接到 train.py

### 2. 算法库（Discussion / Solution writeup）

```python
# Kaggle CLI 对 discussion 覆盖弱，优先用网页搜索:
# site:kaggle.com/competitions/<comp>/discussion "solution"
# site:kaggle.com/competitions/<comp>/discussion "writeup"
# site:kaggle.com "<keyword>" "what worked" "kaggle"
```

**金矿位置**：top 5-10 队的 solution writeup，里面写：
- 用了什么 backbone / 为啥（vs 论文 SOTA）
- 什么 augmentation / 哪个 loss / 哪种 ensemble
- 失败方向（救你跳坑）
- 调参 trick + 算力消耗

**铁律**：top 1 写最少（怕泄漏），top 3-10 写最详细，**优先读 4-8 名**。

### 3. 知识库（Discussion + Comments）

```python
# 用 Kaggle competition discussion 页面 + 浏览器搜索:
# "leakage" / "data issue" / "shake" / "what worked" / "what didn't"
```

**用法**：
- 怀疑 leakage → search "leakage" / "data leak" / "shake" → 看 host 怎么说
- 数据 quirk → search "data issue" / "noise" / "outlier"
- 调参直觉 → search "what worked" / "what didn't"

### 4. 领域数据库（Datasets）

```python
kaggle datasets list -s "<keyword>" --sort-by votes
kaggle datasets files <user/name>
kaggle datasets download <user/name> -p _data/raw/kaggle/<slug>
kaggle competitions download -c <competition> -p _data/raw/kaggle/<competition>
```

**用法**：
- domain 数据稀少 → Kaggle 找类似数据预训练 / 数据扩充
- 找 baseline benchmark 数据集
- 验证你的方法在多 domain 都 work（防 overfitting 到一个数据集）

## 抄作业 vs 自研的判断

| 情境 | 推荐 |
|---|---|
| 完全新 domain / 第一周 | 直接抄 top kernel，改 input |
| baseline 已有，加方向 | 抄 top 5-10 writeup 找 trick |
| 已超过历届 best | 自研 + 论文找 SOTA |
| 论文比赛（独创性要求）| 看 Kaggle 但不抄完整 pipeline |
| 工业部署 | 抄 + 简化（Kaggle 常 over-engineer）|

## 跟试错 / autoresearch loop 配合

**最佳工作流**：

```
新项目 →
1. Kaggle 4 库扫 1 小时 → 拉 top kernel + top writeup
2. 嫁接到 train.py 当 baseline (Mode C 起步)
3. 进入 Karpathy loop Mode A 高频改进
4. 卡住 → 回 Kaggle discussion 找新 angle
5. 仍卡 → 学术检索技能 `share-nature-academic-search`（可选，本包未包含） + arXiv/CrossRef/PubMed API
6. 综合 → 回 Mode A
```

## 反模式

- 🔴 不查 Kaggle 直接自己撸 → 重新发明轮子
- 🔴 只抄 top 1 → 信息密度低（防泄漏）
- 🔴 抄 pipeline 但不读 discussion → 错过关键 trick
- 🔴 嫁接 Kaggle 代码不改 input shape → crash
- 🔴 信任 Kaggle 数据集"干净" → 仍要 EDA / leakage 检查

## Kaggle 之外的同类资源

| 平台 | 何时用 |
|---|---|
| Kaggle | 工业 ML / 表格 / vision / NLP / 时序 |
| HuggingFace | NLP / vision / 多模态 weights & datasets |
| paperswithcode | 论文 SOTA + benchmark + 代码链接 |
| arxiv-sanity | 最新论文流 |
| timm / transformers | 现成 backbone 库 |
| MLflow / W&B public | benchmark 实验日志 |

## 常用 prompt 模板

```
我做 <domain> task，metric=<metric>，数据 <description>。
帮我:
1. 用 Kaggle CLI / 网页找 3 个相似比赛
2. 各拉 top 3 kernel 的 description / approach 摘要
3. 各找 top 5-10 writeup 的关键 trick
4. 综合成一个 baseline 方案 + 5 个改进方向
```

把 Kaggle 当作"前人 100 万小时累积的 prior"，不查 = 起跑线后退 1 年。
