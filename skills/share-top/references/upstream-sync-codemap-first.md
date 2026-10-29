---
name: upstream-sync-codemap-first
tags: [share, top, col4, upstream, sync, codemap, multi-pass]
description: "上游兼容 / 合并 / 升级 / 同步外部仓库 / ingest 任务的标准工作流。codemap-first 强制 + Multi-Pass 0 新问题收敛 + 失败切整模块复制 + 权威源复制优先 ≠ Rule of Three。所有项目通用。"
---

# Upstream Sync · codemap-first 工作流

> v4 TOP COL 4 子协议 · 通用版(任何 downstream 接 upstream 任务都用)
> 由跨项目反复出现的"漏扫 N 轮才理解上游全貌"问题催生 · 用规则钉死流程

## 0 · 触发条件(任一命中就走本协议)

cc 看到下列任一信号 · **立即走本协议** · 不要当普通编码任务:

- 用户说:**兼容 / 合并 / 升级 / 同步 / 移植 / 接入 / 对接 / 吸收 / sync / merge / upstream / ingest / port** + 项目名/仓库/外部源
- 用户说:**100% 以 X 为权威 / 把 Y 兼容回来 / 让我们项目支持 Z 的最新代码**
- 用户说:**扫一下 X 项目 / 看看 X 仓库 / X 那边有什么 / 我们差距在哪**
- cc 自检:任务涉及"把外部仓库的 N 个模块挪进当前项目"
- cc 自检:用户连说 ≥2 次"你还在漏 / 没扫到 / 漏了"→ 当前在散文件 grep · 切回本协议

🔴 **绝对禁止**:触发后**不查/不生成 codemap 就开始 grep / find / Read 散文件**。这等同让用户连说 N 轮"你还在漏扫"。

## 1 · 第一动作 · codemap 优先(强制 · 无例外)

按顺序执行 · **不能跳**:

### Step 1.1 · 找现有 codemap
```bash
ls _wiki-methodology/_top/_codemaps/*codemap*.md  _wiki-methodology/_top/_codemaps/*sync-gap*.md  2>/dev/null
```

| 状态 | 行动 |
|---|---|
| 找到 + codemap 记录的上游 commit/日期与当前上游一致 | **Read 它就够** · 直接进 Step 1.4 决策 |
| 找到 + 上游已有新提交(或 codemap 没记上游版本) | 跑 § 8 重扫命令更新统计 → 再 Read |
| 找不到 | 进 Step 1.2 生成 |

### Step 1.2 · 生成 codemap(8 章节模板 · 落 `_wiki-methodology/_top/_codemaps/<upstream-name>-codemap.md`)

**8 章节(每节都要 · 缺一不可)**:

1. **上游 N 大仓库顶层目录全图**(不只看你以为相关的子目录 · `ls -d <upstream>/*/` 看全)
2. **我们项目对应结构**
3. **子模块差距矩阵**:upstream 真有 vs downstream 已接 · 接入度 % · 优先级 · 表格
4. **upstream CLAUDE.md / README 升级时间线**(找日期标记 · 看脱节多久)
5. **顶层目录差距**(逐个目录看用途 + downstream 应否接)
6. **工具链 / CLI 差距**(若 upstream 含 N+ 工具)
7. **优先级建议**(立即 / 中 / 可选)
8. **重扫命令**(5-10 行 bash · upstream 升级时一跑就更新统计)

无独立模板文件:直接按本节 8 章节结构写(`scripts/gen-upstream-codemap.sh` 生成骨架)。

### Step 1.3 · 加 AGENTS.md 指针
项目 AGENTS.md 顶部加"⚡ 差距地图(必读)"区块 + Read 指令 · 让任何未来 cc/Codex 第一时间看到。

### Step 1.4 · 决策(基于 codemap · 不再瞎扫)
- 缺口只是少量独立补丁、模块边界和引用关系都清楚 → 走选择性接入
- 缺整子模块 / 引用关系不清 / 已漏扫过同类内容 → 走整模块复制(判据表见 § 3)
- 用户明确"100% 权威" → **直接默认整模块复制**(不要先尝试零碎接入)

## 2 · 收敛判定(Multi-Pass 严苛版 · 比 share-architecture-design § 5 更严)

| Pass N 状态 | 行动 |
|---|---|
| Pass N 新增问题数 == 0 | ✅ 收敛 · 可宣称完成 |
| Pass N 新增问题数 > 0 | ⚠ 未收敛 · **必须继续 Pass N+1** · 不许假装做完 |
| Pass ≥ 3 仍有新问题 | 🔴 **失败信号 1** · 切策略(§ 3) |
| Pass ≥ 5 仍有新问题 | 🔴 **失败信号 2** · 强制切策略 |
| 新增问题从局部 bug 扩到新模块/新项目/新资产库 | 🔴 **失败信号 3** · 系统边界没理解 · 立刻切 |

**关键原则**:**只要扫到 1 个新问题 = 还没收敛 = 不许宣称完成**。

跟 `share-architecture-design § 5` 区别:§ 5 允许 ↓ 就停太松 · 本协议要求 == 0。

## 3 · 失败 → 整模块复制(不是逐文件复制粘贴)

触发任一失败信号后 · **优先级**(从高到低):

1. **整目录 vendor / import**(`shutil.copytree` / `rsync -a`)
2. **git submodule** 指向 upstream(repo 内不膨胀)
3. **symlink** 到本机 mirror(dev 环境零成本)
4. **双源 lazy read**(运行时从 mirror 读 · prod fallback)
5. **manifest + thin wrapper**(repo 只放索引 · 不放重资产)
6. **最后才是选择性复制**

🔴 禁止失败信号后继续逐文件 grep / 猜测 — 这制造更多遗漏。

### 整模块 vs 选择性 判定

| 整模块复制 | 选择性复制 |
|---|---|
| upstream 模块有自己入口 / 脚本 / 配置 / assets / exports | 单文件工具函数 |
| 模块内引用关系不清楚 | 明确无依赖的小资产 |
| 用户要求"100% 权威" | upstream 本身是 examples/snippets |
| 已经漏扫过同类内容 | downstream 只需稳定 API |
| 是真实产物(用户/客户/历史)非样例 | |

### 大体积 upstream 处理

不能盲目全提交进 git(GitHub 单 repo 推荐 < 1GB)· 按优先级:
1. git submodule
2. 本机 mirror + symlink
3. vendor 只放 manifest + README + thin wrapper
4. 双源 lazy read(prod fallback)
5. 只提交索引 / hash manifest / codemap

## 4 · 权威源复制优先(≠ Rule of Three)

upstream 是**老师/客户/生产系统/官方 repo/历史真实产物**时 · 默认 = **复用原物 · 不重写**。

优先级:1. 直接引原目录 → 2. 整模块复制 → 3. thin adapter 包一层 → 4. 选择性复制 → 5. 重写

仅当下列情况才重写:
- upstream 明确不可运行
- 许可证 / 隐私禁止复制
- downstream 平台完全不兼容
- 用户明说重写

**与 Rule of Three 关系**:
- "downstream 自有重复逻辑要不要抽象" → 走 Rule of Three(重复需求成立后再抽象)
- "upstream 已有真实产物 · downstream 要不要复用" → 走本协议 § 4

## 5 · Origin 记录(强制)

所有 upstream 来源文件 / 模块必须在 codemap 记录:
- upstream repo / path
- upstream commit / date
- downstream path
- sync mode: `copied` / `symlink` / `submodule` / `lazy-read` / `adapted`
- local modifications(若有)
- do-not-edit policy

复制文件顶部建议加:
```python
# Derived from <upstream-repo>:<path> @ <commit/date>
# Treat upstream as authority; local edits require sync note in codemap.
```

## 6 · Codex 第二意见触发(高风险才触发 · 不全局强制)

必须请 Codex 复核(走外援审查技能（可选，本包未包含；公开版见 https://github.com/YonganZhang/external-review-skill ）的 CLI wrapper;未安装时请用户另找一个模型复核):
- upstream sync / 权威源兼容任务(本协议触发即触发)
- Pass ≥ 3 仍发现新问题
- 准备宣称"100% 覆盖"
- 准备删除 / 替换 upstream 产物
- 体积大需决定 submodule / symlink / lazy / vendor 策略

Codex 复核范围:codemap 主要目录/模块/资产是否齐 · downstream 缺口可信度 · 是否应整模块复制 · 是否有明显遗漏方向。

## 7 · v4 横切

upstream 不是独立列 · 是横切维度 · 映射到 5 列:

| 列 | upstream 内容 |
|---|---|
| **wiki** | upstream 背景 / 同步 ADR / 决策 |
| **top** | upstream 入口 / 运行方式 / 集成入口 |
| **tests** | upstream parity tests / smoke tests |
| **code** | upstream **codemap** + 模块映射 + adapter 代码(本文件归这里)|
| **fs** | upstream mirror / assets / exports / vendor / submodule / symlink |

codemap 路径推荐:
- `_wiki-methodology/_top/_codemaps/<upstream-name>-codemap.md`(主图 · 必有)
- `_wiki-methodology/_top/_codemaps/<upstream-name>-sync-gap.md`(差距清单 · 可合并进 codemap)
- `_wiki-methodology/_top/_codemaps/<upstream-name>-origin-manifest.md`(origin 索引 · 大量文件时)

重大策略 → 额外 ADR 到 wiki 列。

## 8 · 重扫命令模板(每个项目落 codemap § 8)

```bash
# 通用模板 · cc 基于实际 upstream 路径替换变量
UP=<upstream-root>
DN=<downstream-root>

# 8.1 upstream 顶层目录变化
ls -d "$UP"/*/

# 8.2 关键子模块脚本数变化
find "$UP" -name "*.py" -path "*/<scripts-or-src>/*" | awk -F/ '{print $(NF-1)}' | sort | uniq -c

# 8.3 downstream 已接清单
grep -rohE "<upstream-keyword>/[a-z_-]+/[a-z_-]+\.py" "$DN/" | sort -u

# 8.4 upstream CLAUDE.md / README 最新章节
grep -nE "20[0-9]{2}-[0-9]{2}-[0-9]{2}" "$UP/CLAUDE.md" | tail -5

# 8.5 接入度统计(项目级)
# 跑项目 pytest 矩阵看 v3/upstream 命中率
```

## 9 · 反例 + 正例

### 反例(真踩坑)
| 错误 | 后果 | 正确做法 |
|---|---|---|
| 用户说"兼容 X 项目" · cc 直接 grep X 几个子目录就开干 | N 轮被催"还在漏扫" · 真大漏后期才浮出 | 第一动作 = 生成完整 codemap · 看全顶层目录/子模块/工具 |
| 用户说"100% 权威" · cc 还在逐文件选择性复制 | repo 不断膨胀 + 仍漏 | 默认整模块复制(双源 lazy / submodule)|
| Pass 1 发现 5 问题 · cc 修完就 commit | Pass 2 又发现 8 个 · 用户失去耐心 | 收敛到 0 新问题才停 |
| Round N 才想起 codemap | 前 N-1 轮全废 | Round 0 就生成 |

### 正例(同类任务该这么做)
1. 用户:"把 Linus 的 kernel 某模块兼容到我们 OS"
   → cc 第一动作:生成 `_wiki-methodology/_top/_codemaps/linux-kernel-codemap.md` · 8 章节
2. 用户:"我们项目要支持 OpenSSL 3.0"
   → 不要先 grep OpenSSL API · 先生成 codemap 看全 vs 已接
3. 用户:"把这个学生 / 同事的项目 fork 进来一起开发"
   → 先 codemap 看全 · 再决定 submodule / 整 vendor / 选择性接

## 10 · 自检(任务结束前必过)

- [ ] codemap 是否在 `_wiki-methodology/_top/_codemaps/` 落盘?
- [ ] 项目 AGENTS.md 顶部是否有 codemap 指针(让未来会话秒读)?
- [ ] 最后一 Pass 新增问题是否 == 0?
- [ ] 整模块复制部分是否记 origin?
- [ ] 重扫命令是否在 codemap § 8 写清楚(下次升级一跑就更新)?
- [ ] 失败信号若触发是否真切了策略 / 没硬撑?
- [ ] 是否过 Codex 复核(本协议触发即触发)?

任一 No · 任务**没完成** · 别 commit 别 push 别宣称收尾。

## Why · 协议诞生原因

跨项目反复出现"漏扫 N 轮才理解 upstream 全貌"事件。根因 4 条:

1. **触发条件不清** · cc 把"兼容上游"当普通编码任务 · 没识别该走 codemap-first
2. **收敛判定太松** · `share-architecture-design § 5` 允许 ↓ 就停 · 不要求 == 0 新问题
3. **没有失败 → 整模块复制 切换协议**
4. **没区分"权威源场景 ≠ Rule of Three"** · cc 默认 R3 走"先最小不抽象" · 在权威源场景错了

本协议把 4 根因钉死。下次任何项目说"兼容/合并/升级/同步 X" · **第一动作必为 codemap · 没有第二条路**。
