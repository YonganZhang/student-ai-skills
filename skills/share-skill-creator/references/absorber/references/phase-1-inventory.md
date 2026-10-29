# Phase 1: 盘点（Inventory）

## 输入
- 外部 skill 仓库路径（本地目录或 GitHub URL）

## 步骤

### 1.1 扫描外部仓库
- 递归查找所有 `SKILL.md`、`*.md` skill 文件
- 提取每个 skill 的：名称、描述、场景/触发词、估计行数
- 记录到 `absorb-workspace/inventory.json`

### 1.2 扫描现有 skill 体系
- 读取 `~/.claude/skills/*/SKILL.md` 与 `~/.agents/skills/*/SKILL.md`，以及当前项目 `.claude/skills/`、`.agents/skills/` 下技能的 frontmatter
- 提取每个 skill 的：名称、描述、场景/触发词
- 记录到 `absorb-workspace/existing.json`

### 1.3 按领域分类
将外部 skill 归入领域标签：

| 领域 | 关键词 |
|------|--------|
| ML/AI | machine learning, deep learning, interpretability, SHAP, model, training |
| 科学写作 | writing, paper, review, citation, publication |
| 数据可视化 | plot, chart, figure, visualization |
| 地球科学 | geospatial, remote sensing, GIS, well-log |
| 生物/医学 | genomics, drug, clinical, protein |
| 工程/仿真 | simulation, optimization, engineering |
| 其他 | 不属于以上类别 |

### 1.4 生成盘点报告
输出格式（展示给用户确认）：

```
## 外部仓库盘点：{repo_name}
总计：{n} 个 skill

### 与现有 skill 可能重叠（{m} 个）
| 外部 Skill | 场景摘要 | 匹配到的现有 Skill | 重叠度 |
|------------|----------|-------------------|--------|
| ...        | ...      | ...               | 高/中/低 |

### 新领域（现有体系未覆盖，{k} 个）
| 外部 Skill | 场景摘要 | 领域 |
|------------|----------|------|
| ...        | ...      | ...  |

### 与用户研究方向无关（建议跳过，{j} 个）
| 外部 Skill | 原因 |
|------------|------|
| ...        | ...  |
```

## 门控
用户确认盘点报告后，进入 Phase 2。用户可在此阶段直接标记"不需要"的 skill。
