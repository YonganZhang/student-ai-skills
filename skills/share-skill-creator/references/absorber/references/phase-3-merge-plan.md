# Phase 3: 合并计划（Merge Plan）

## 输入
- Phase 2 确认的分类结果

## 步骤

### 3.1 逐条生成合并计划

对每个标记为 merge/create/split 的 skill：

1. **读取外部 skill 完整内容**
2. **读取目标现有 skill 完整内容**（merge/split 时）
3. **提取可吸收内容**，分为：
   - 场景/触发词补充
   - 新的 reference 文件（代码模板、工作流、示例）
   - 新的脚本
   - 对现有 reference 的补充段落
4. **生成 pre-merge diff**：
   - 目标 SKILL.md 将新增哪些行
   - 将创建哪些新 reference 文件
   - 将修改哪些现有 reference 文件（标注具体段落）

### 3.2 合并计划格式

每条合并计划展示为：

```
## 合并计划 #{n}: {外部skill名} → {目标skill名}

### 来源
- 仓库: {repo_name}
- 文件: {file_path}
- 核心内容: {一句话摘要}

### 目标变更
#### SKILL.md 变更（仅索引行）
+ | 新场景 | 说明 | `references/new-file.md` |

#### 新建 references/
- `references/absorbed/{source}-{topic}.md` — {内容摘要}（{行数}行）

#### 修改现有 references/
- `references/existing-file.md` 第 {n}-{m} 行后追加：{摘要}

### 不吸收的内容（及原因）
- {内容}: {原因}（如：与现有内容重复 / 质量不足 / 不适用）

### 溯源
- 来源: {repo}/{path}
- 吸收时间: {date}
```

### 3.3 Codex 审查

将合并计划提交 Codex 检查：
- 是否有遗漏的重叠
- 吸收内容质量是否合格
- 索引-引用分离是否正确（SKILL.md 无超过 3 行的代码块）
- 溯源标注是否完整

Codex 审查通过后，展示给用户最终确认。

### 3.4 内容放置规则

| 内容类型 | 放置位置 | 示例 |
|----------|----------|------|
| 代码模板/脚本 (>3行) | `scripts/` 或 `references/absorbed/` | Python 绘图模板 |
| 工作流说明 | `references/absorbed/` | SHAP 分析流程 |
| 触发词/场景 | 目标 SKILL.md 表格中一行 | "SHAP 可解释性分析" |
| 配置/参数 | `references/absorbed/` | 模型参数推荐 |

所有吸收内容放入 `references/absorbed/` 子目录，文件名格式：
`{来源仓库缩写}-{主题}.md`

例：`kdense-shap-interpretability.md`

## 门控
Codex 审查通过 + 用户确认后，进入 Phase 4。
