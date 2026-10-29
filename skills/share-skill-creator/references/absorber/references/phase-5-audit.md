# Phase 5: 去重审计（Deduplication Audit）

## 输入
- Phase 4 完成的所有合并结果

## 步骤

### 5.1 全局扫描
遍历 `~/.claude/skills/*/SKILL.md` 与 `~/.agents/skills/*/SKILL.md`（以及当前项目 `.claude/skills/`、`.agents/skills/`），检查：

1. **场景重叠** — 两个 skill 的触发词/场景描述是否有交集
2. **reference 重复** — 不同 skill 的 references/ 下是否有内容高度相似的文件
3. **索引悬空** — SKILL.md 中引用的 reference 文件是否实际存在
4. **孤立文件** — references/ 中是否有未被任何 SKILL.md 索引的文件

### 5.2 生成审计报告

```
## 去重审计报告

### 场景重叠（需关注）
| Skill A | Skill B | 重叠场景 | 建议 |
|---------|---------|----------|------|
| my-sci-plot | my-sci-write | "图表描述" | 明确边界：绘图→plot, 文字描述→write |

### reference 相似度
| 文件 A | 文件 B | 相似度 | 建议 |
|--------|--------|--------|------|
| (无重复则显示 "全部通过") |

### 索引完整性
- 悬空索引: {n} 个（列出）
- 孤立文件: {n} 个（列出）

### 本次吸收统计
- 吸收来源: {repo_name}
- 处理 skill 数: {total}
- 合并: {merge_count}
- 新建: {create_count}
- 拒绝: {reject_count}
- 新增 reference 文件: {file_count}
- 新增总行数: {line_count}
```

### 5.3 用户最终确认
- 用户确认审计报告无问题
- 如有需要修复的项目，回到 Phase 4 处理
- 全部完成后，清理 `absorb-workspace/backup/`（用户确认后）

## 完成
吸收流程结束。`absorb-workspace/absorb-log.md` 保留为永久记录。
