# Wiki 反链协议

## 核心原则

**FS 是物理真相源，Wiki 是语义真相源**。两者通过反链闭环，避免内容重复。

- FS 回答 "这张图放在哪" → `paper/figures/LEDGER.md` 里有真身路径
- Wiki 回答 "为什么这样画" → `wiki-methodology/wiki/figures/choropleth.md` 里有方法论
- LEDGER 条目通过 `[[wiki/...]]` 反链连接两者

## 三条反链规则

### R1 — 新建 asset 目录 → 必须建对应 wiki 页

新增顶级资产目录（如 `paper/equations/`、`paper/data-refs/`）时：

1. 立即在 `wiki-methodology/wiki/` 下建对应 topic 页（如 `wiki/topics/equations.md`）
2. 页面至少包含：
   - 这类资产的用途 / 方法论 / reference 出处
   - 反向链接："物理路径见 [[fs/directory-map]]"

### R2 — LEDGER 每条必须含 wiki 反链

每条 LEDGER 条目**必须**有 `方法论:` 或 `概念:` 字段，值为 `[[wiki/...]]` 形式。

✅ 合格示例：
```markdown
- `Fig1_global_map.png` → `archive/2026-04-13_..._v3.png`
  - 方法论：[[wiki/figures/choropleth]]
```

❌ 不合格：
```markdown
- `Fig1_global_map.png` → `archive/..._v3.png`
  - 脚本：plot_fig1.py
  # 缺 wiki 反链 → lint-fs.py 会报 FAIL
```

### R3 — fs/directory-map.md 每个目录旁有"用途 + wiki 页"

`directory-map.md` 是项目所有顶级目录的一句话清单，每行格式：

```markdown
- `paper/figures/` — 论文图片治理目录，三件套启用 → [[wiki/topics/figures-governance]]
- `paper/equations/` — 关键公式片段 → [[wiki/topics/equations]]
- `src/analysis/` — 分析脚本 → [[wiki/topics/analysis-pipeline]]
- `data/raw/` — 原始数据（不套三件套，只读）→ [[wiki/topics/data-sources]]
```

没有 wiki 反链的目录行 = 不合格，lint 会报。

## Wiki 页粒度建议

- **不要给每个文件建 wiki 页**（太细，会爆）
- **按主题 / 方法论 / 资产类别建**：一个 topic 覆盖一批文件
- 示例合理粒度：
  - `wiki/figures/choropleth.md` — 所有 choropleth 类图共享
  - `wiki/figures/boxplot.md` — 所有箱线图共享
  - `wiki/data/reservoir-merged.md` — 合并水库数据的描述

## 何时允许没有反链

**只有 `_scratch/` 下的临时产物**不要求反链。一旦晋升到 current/ → 必须反链。
