# 注册架构 v8.16 beta — 5 分钟上手版 (跨项目 0 真用户, 真用前等社区反馈)

> AI 自动维护代码"函数图书馆", 防 AI 反复造轮子 / 漏接线 / 留死代码.
> 不靠 yaml, 靠**代码 docstring 内联注释** — AI Read 文件就懂.

## 1 行装好

```bash
bash ~/.claude/skills/share-top/templates/registry-architecture/init.sh /path/to/project
```

装 5 件: schema + CLI + register.py + pre-commit hook + AGENTS.md hint（Claude/Codex 共读的项目说明唯一真源）。

## 写新函数 — 只填 3 字段

```python
def validate_patch(patch, state):
    """防 AI 让承诺保护的 NPC 死亡.
    
    @status: active
    @consumed_by: world_state_overlay.py:55
    """
    ...
```

强制 3 个: `@why` (docstring 第一行) / `@status` / `@consumed_by`
可选 3 个: `@introduced_in` (自动填本 phase) / `@wired_up_in` (commit hash) / `@tags`

**就这样**. AI Read 文件直接看到 docstring, 不用查 yaml/CLI.

## 状态机 (5 档)

```
stub      占位, 还没真实现
wip       实现中, 没接入主流程  
active    有 @consumed_by 就自动 active (v8.14 Codex R17 自动 promote)
deprecated 功能弃用, 留兼容
archived  归档不删 (跑 query --prune 标)
```

## 3 个查询命令 (想查时用)

```bash
python3 _code/_query_registry.py --report          # 30s 健康总览
python3 _code/_query_registry.py --orphans         # 列可疑 (active 但无证据)
python3 _code/_query_registry.py --prune --dry-run # 列 dead 候选 (不动 yaml)
```

不查也行 — pre-commit hook 推 1 行健康状态到 stdout, AI commit 时看到.

## 自动化 (你不用做的事)

```
commit 时 pre-commit hook 偷偷:
1. 扫 staged 代码新 +def
2. 跑 register.py --scan 读 docstring @marker
3. 填 yaml + git add 进同次 commit
4. print 1 行健康总览 (推 AI 看)
```

## 跨项目要点

| 项目类型 | 注意 |
|---|---|
| 科研 | 数据资产 > 函数, 跟 `_data_registry.yml` 配套用 |
| 软件开发 | PR# 比 commit hash 自然, `@wired_up_in: #123` |
| 多人协作 | `.git/hooks/pre-commit` 不进 git, 装 `.husky/` 替代 |
| Linux/Mac only | Windows 用 WSL (`realpath` / bash heredoc 依赖) |

## 反讽教训 (踩过的坑)

- ❌ v8.4: 14 原则规范 → 实战 5 个就够
- ❌ v8.10: yaml 加 why 字段 → AI 不主动查 yaml
- ❌ v8.11: post-commit hook 改文件留 dirty 工作区
- ✅ v8.13: 翻转 — docstring 真源, yaml 派生, AI Read 即用
- ✅ v8.14: 字段 5→3 强制, active 自动 promote (不靠关键词)

## 完整 14 原则备查

砍掉的 9 个 (实战零用): 渐进披露 / 单源多视图 / 废除路径 / Boy Scout / DoD 真证据 / 反哺架构 / 自举验证 / 唯一标识 / 物理对齐. 见 `references/registry-architecture-philosophy.md`.

5 核心保留: 卡片化 / 接线证据 / 状态机 / 可索引 / **自动补 > 手填**.
