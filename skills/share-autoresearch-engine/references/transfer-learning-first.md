# Transfer Learning First — 通用迁移学习优先

## 核心原则
做 domain task 时，**先尝试已有的 pretrained / foundation model + 下游 head/adapter**，再考虑 from-scratch domain-specific 模型。这是**所有 DL 模态**的通用启发式（vision / NLP / audio / 时序 / 多模态 / 表格 / 图）。

## Why（普适机制）
- 通用 pretrained 见过的数据多 100~10000×
- 学到的低层特征 / representation 跨 domain 通用率高
- frozen 时无过拟合风险
- 数据稀少时（< 100k）效果常碾压 from-scratch
- 实施成本极低（一行代码 load weights）

## 各模态 foundation model 速查

| 模态 | 推荐 frozen backbone | 备选 |
|---|---|---|
| Vision (image) | DINOv2 / CLIP / timm ConvNeXt | SAM / ResNet50 |
| Vision (video) | VideoMAE / V-JEPA | TimeSformer |
| NLP | BERT / RoBERTa / sentence-transformers | LLM embedding |
| Audio / Speech | Wav2Vec2 / Whisper encoder | HuBERT |
| 时序 | TimesFM / Chronos / Lag-Llama | N-BEATS pretrained |
| 多模态（图+文）| CLIP / SigLIP | BLIP-2 |
| 表格 | TabPFN / TabTransformer | XGBoost+pretrained embedding |
| 图（graph）| GraphGPS pretrained | GIN |
| 代码 | CodeBERT / StarCoder embedding | — |
| 蛋白质 / 生物 | ESM-2 / AlphaFold features | ProtTrans |

## 通用 cookbook

```python
# 1. Load frozen backbone（任意模态）
backbone = load_pretrained(name='<model>')
backbone.eval()

# 2. 抽特征
with torch.no_grad():
    features = backbone(inputs)  # batch × D

# 3. 降维（若 D 大）
from sklearn.decomposition import PCA
features_pca = PCA(n_components=128).fit_transform(features)

# 4. 拼接 baseline 特征 → 喂下游模型（LGB / linear / small NN）
X = np.hstack([baseline_features, features_pca])
```

**通用关键点**：
1. **frozen vs fine-tune**：数据 < 100k → frozen，> 1M → fine-tune，中间 → adapter / LoRA
2. **降维**：embedding 维度大（>512）时 PCA 到 128/256 防过拟合
3. **多 backbone 集成**：不同 backbone 各 PCA 后 concat
4. **输入对齐**：分辨率 / 序列长度 / 采样率必须匹配 backbone 预训练时
5. **下游 head**：小数据 → linear / LGB；大数据 → small MLP

## 决策树

```
domain task →
├── 已有公开 weights 的 domain pretrained?
│   ├── 是 → 同时试 frozen domain 和 frozen general
│   └── 否 → 直接 frozen general foundation
├── 数据量?
│   ├── < 10k → frozen + linear/LGB head
│   ├── 10k-100k → frozen + GBDT / small MLP
│   ├── 100k-1M → frozen + adapter / fine-tune top layers
│   └── > 1M → 考虑 fine-tune full
└── 时间预算?
    ├── < 1h → frozen + LGB（最快 baseline）
    └── > 1d → 多 backbone ablation + ensemble
```

## 何时不用 transfer-learning-first

- **数据极大（> 10M）+ 算力充足**：from-scratch 可能更好
- **domain 与所有公开 pretrained 都严重 distribution shift**（某些医学影像 / 极端工业信号）
- **任务需要的是模型结构本身而非特征**（某些 segmentation / RL policy）
- **延迟 / 部署约束**：foundation model 太大不能上

## 反模式

🔴 "我的 domain 太特殊，通用 pretrained 肯定不行" → 先试再说
🔴 直接 fine-tune 全模型 → 小数据集必过拟合
🔴 不降维直接 2048-d 喂下游 → 过拟合 / 慢
🔴 输入 size 不对齐 backbone → 性能崩
🔴 只试 1 个 backbone → 集成往往再 +0.005~0.02

## 跟 Karpathy autoresearch loop 配合

在 `train.py` 里把 **backbone 选择 + freeze/finetune 比例** 当作 hyperparameter，每个 5min 实验试一种组合。`results.tsv` 记录"哪个 backbone × frozen ratio × head"在你的 metric 下最优。
