# Phase 4: 执行（Apply）

## 输入
- Phase 3 确认的合并计划

## 步骤

### 4.1 备份
合并前备份所有将被修改的文件：
```
cp -r target-skill/ absorb-workspace/backup/target-skill-{timestamp}/
```

### 4.2 逐条执行

**严格逐条**，每条完成后等用户确认再做下一条。

对每条合并计划：

#### Step A: 展示即将执行的变更
```
## 即将执行：合并计划 #{n}
- 来源: {外部skill} ({repo})
- 目标: {现有skill}
- 变更内容:
  - [新建] references/absorbed/kdense-xxx.md (52行)
  - [修改] SKILL.md 第15行后追加1行索引
  - [不变] 其余所有文件
确认执行？(y/n)
```

#### Step B: 执行变更
1. 创建 `references/absorbed/` 子目录（如不存在）
2. 写入新 reference 文件，文件头部添加溯源块：
   ```
   <!-- 
   来源: {repo_name}/{file_path}
   吸收时间: {YYYY-MM-DD}
   吸收者: share-skill-absorber
   -->
   ```
3. 在目标 SKILL.md 的路由表/索引中添加一行指向新 reference
4. 如有脚本，放入 `scripts/` 并确保可执行
5. 在目标 skill 根目录的 `UPSTREAM.json` 新增或更新一项 source（格式见 `../../upstream-tracking.md`），然后跑 `python3 ~/.claude/skills/share-skill-creator/scripts/upstream_watch.py --lint`


#### Step C: 生成 post-merge diff
展示实际变更的 diff：
```diff
--- a/my-sci-plot/SKILL.md
+++ b/my-sci-plot/SKILL.md
@@ -25,6 +25,7 @@
 | SHAP 分析 | 特征重要性图 | `references/shap-plots.md` |
+| LIME 局部解释 | 局部可解释性图 | `references/absorbed/kdense-lime.md` |
```

#### Step D: Codex 审查 post-merge diff
将 diff 提交 Codex：
- 变更是否符合合并计划
- 是否引入了不期望的内容
- 索引-引用分离是否正确
- 溯源标注是否完整

Codex 审查结果汇报给用户。

#### Step E: 记录吸收日志
追加到 `absorb-workspace/absorb-log.md`：
```
| {date} | {外部skill} | {repo} | {动作} | {目标skill} | {新文件列表} |
```

### 4.3 回滚机制
如果用户对某条执行结果不满意：
```
cp -r absorb-workspace/backup/target-skill-{timestamp}/ target-skill/
```
恢复到执行前状态，该条标记为 rejected。

## 门控
所有确认的合并计划执行完毕后，进入 Phase 5。
