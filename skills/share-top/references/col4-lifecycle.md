AppliesTo: claude
# COL 4 生命周期 · 入口指针（默认 dormant）

> 本规则**默认休眠**。只在用户表达"知识栈维护意图"时激活，避免每次会话都跑 mental checklist。

## 何时唤醒

**只有**当用户说"清理死代码 / tidy / 更新六合一 / 刷 COL4 / 扫死代码"，且语境是"维护知识栈"时 → 按本文件的约束和下方工具入口执行。

**任何其他场景**（包括普通改代码 / 改 typo / debug / 加功能 / 普通"更新 TOP" / 普通问答）→ 当本规则不存在。**不要**读 COL4.md，**不要**主动跑 audit-rot，**不要**列 6 类检查。

## 一句话约束（永远生效）

- 🔴 死代码处置 = `purge-to-legacy.sh` 移到 `_legacy/<UTC>/`，**永不** `rm`
- 🔴 不嵌套 `code/legacy/` 或 `_code/_legacy/`（污染 codemap）

## 分层 codemap = 扫描沉淀的缓存（升级框架）

> COL4 的 codemap 已升级为「代码理解缓存」,不是文档堆。真源永远是**源码 + codegraph live 查询**;Markdown 分层(L0 `_codemap.md` /(大仓)L1 `_codemaps/<域>.md`)只是**派生导航**,带 freshness 戳,stale 时不可作事实依据。机器缓存 = codegraph 图索引(增量更新)。
> 产出/增量/stale-gate 的**完整操作规范**归代码索引工具自身的文档(扫描模式只在用户明确说「扫描模式 / 语义扫描」时触发,由代码语义扫描技能执行,该技能本包未包含);本处只登记 COL4 拥有 codemap 结构这一事实,不重复正文。
> ⚠️ 区分:「扫描」= 工具层建/刷分层 codemap;「扫死代码 / 刷 COL4」= 本文件的知识栈维护动作。

## 工具入口（懒加载，不背全套）

```
audit-rot                # 扫死代码
purge-to-legacy -r "..." # 移到 _legacy/<UTC>/
```
（旧 `gen-col4`（Serena 风 `_COL4.md` 生成器）已退役，未随本包发布；COL4 代码图现走 codegraph。）

完整用法 → `scripts/audit-rot.sh`、`scripts/purge-to-legacy.sh` 文件头注释。
