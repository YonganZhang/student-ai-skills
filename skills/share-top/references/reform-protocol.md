# Reform Protocol — v4 架构定期瘦身 / 整理 / 校准

> 何时触发: AI 在更新 v4 TOP 时发现臃肿 → 提议 reform → 跟用户对齐 →
> 走 5 Phase 流程(P0 snapshot + P1 瘦身 + P2 索引校准 + P3+ 自定义).
>
> 触发关键词: "项目臃肿 / AI 看不清 / 目录混乱 / v4 TOP 不清晰 / 整理目录 /
> 死代码再处理 / 我们的 pipeline 是不是太臃肿 / 你能一眼看清吗".
>
> 反例: 单次"加 finding / 写 task_plan / 改 anchor 数字" 不触发 reform.

## 1. AI 自评信号(每次更新 v4 TOP 时主动跑)

8 项 binary check, **7/8 ✅ = OK**, **4-6 = 小修**, **≤3 = 启动 reform**.

| # | 检查项 | 通过条件 | 不通过迹象 |
|---|---|---|---|
| 1 | AGENTS.md(旧项目 CLAUDE.md) 行数 | ≤80 行 | >80 行 / ⭐ 入口 > 8 个 |
| 2 | CATALOG.md 版本号 | 匹配当前 active 版本 | 落后 1+ 阶段, 反映旧状态 |
| 3 | 顶级目录数 | ≤12 个 | 顶级 ≥15 个或不清楚谁 active |
| 4 | output 归档 | 当前 baseline + 1-2 个对比, 其他归档 | 同级 ≥5 个版本号变体 (如 `<name>_v8/_v11/_v12/_v15g/...`) |
| 5 | 五大 index 一致 | CATALOG/wiki/top/code/tests/manifest 互相校准, 没死链 | 索引指向 not-exist 路径 |
| 6 | 死链 CI 测 | 存在 + pass | 不存在或 fail |
| 7 | finding 收敛 | V<N-2> 及更早进 `_absorbed/` 子目录 | active 跟 absorbed 混 |
| 8 | active 红线 manifest | 存在 + 列绝不能动的核心文件 | 不存在 → AI 续命可能误动 |

**自评后行为**:
- ✅ 7-8 项过 → 一句话回答 "v4 TOP 状态健康, 无需 reform"
- ⚠️ 4-6 项过 → 列具体哪条不过 + 提议小修(不走完整 5 Phase, 一次性补一两个 manifest 即可)
- 🔴 ≤3 项过 → 提议**启动 reform protocol**, 给用户看 5 Phase 计划, 等用户拍板

## 2. Reform 5 Phase 通用模板

任何项目都按这个骨架, 内容按项目自定义.

### P0 — 保全实际内容与依赖（必做）

Git tag只指向已有提交，不保存工作区/index/untracked/ignored内容。不得把tag称作脏工作区完整回退点。先按[Git与实验生命周期](git-version-lifecycle.md)确认实际工作树、HEAD、修改归属与输入范围。

- 清洁且已提交的内容可用提交/tag定位；标签不替代外部资产保全。
- 未提交内容先保存明确范围的可恢复副本，外部大资产保留存储与校验值；范围遗漏明确说明。`version capture`只是显式范围快照，不是全仓备份或原子快照。
- 数据、冻结代码和仍被使用的实验列入do_not_move清单；移动前生成old→new、原因、真实引用者与恢复方案。
- 已获授权且有完整基线时才建立整理分支/worktree；不得从过期HEAD隔离后误称包含未提交工作，不stash/reset用户内容。
- 恢复以保全副本及具名路径为单位先dry-run；不生成会覆盖未知用户改动的一键破坏性回滚。

### P1 — 瘦身(2-3h, 低风险优先)

**P1.0 必做**: Pre-move inventory + dependency graph
- grep 全代码引用图, 输出 `fs/p1_move_manifest.yml`
- 每个待移动文件: `old_path → new_path → reason → 已 grep 引用者 list`
- **任何 move 前必须先有这个 manifest**

**P1 主任务清单(按 ROI 排序)**:
| ID | 任务 | 风险 | 时长 |
|---|---|---|---|
| P1.1 | 顶层 instruction 瘦身（有效指令合并到 AGENTS.md，退役旧 CLAUDE.md） | 低 | 30 min |
| P1.2 | 多套并行系统关系侦察 (双 pipeline / 双 lib) | 中(只标记不改代码) | 1-2h |
| P1.3 | output / build artifact 归档 | 低 | 30 min |
| P1.4 | legacy / 老 experiments 集中标记 | 低 | 30 min |
| P1.5 | finding / decision 收敛 → `_absorbed/` | 低 | 30 min |
| P1.6 | 双副本 module 决策(merge / archive 一份 / LEGACY 标记) | 中 | 30 min |
| P1.7 | 项目根 README 加快速索引 | 低 | 20 min |

### P2 — 索引校准(1-2h, incremental 不是全 after P1)

**关键**: P2 不是 P1 完整结束后才做. P2.0 skeleton 前置, P1 移动同步改索引, P1 结束后 P2 final sync.

```
P2.0 索引 skeleton (前置)         skeleton 框架画好, P1 边移边填
P2.1 CATALOG.md 重写             单一定位入口, 见 §4 9 段结构
P2.2 wiki-index 校准             方法论实体 + V<x> 入口
P2.3 top-index 校准              当前重点 + absorbed 提醒
P2.4 code-index 校准             active 核心 + legacy 区分
P2.5 tests-index 校准            测试套件 + 守护内容
P2.6 manifest.yml 校准           routes + V<x> active 资源
P2.7 version_change_index 更新   V<n>→V<n+1> changelog
P2.8 CI 死链测试                 tests/test_indices_no_dead_links.py
```

### P3+ — 自定义工作(reform 后的实际项目动作)

reform 完目录干净了, 才好做实际工作:
- 跑 baseline 验证
- 新功能开发
- 数据校准
- 论文产出

## 3. 8 条跨 phase 通用纪律(铁律)

1. **Immutable snapshot before reform** — P0 必须完整, 再动任何文件
2. **Move manifest 而非裸 mv** — 每个文件移动: `old → new → reason → ref list`
3. **No delete, only archive** — 移到 `_legacy/<UTC>/` 或 `_absorbed/<version>/`, **P5 GO 才考虑真清**
4. **Reproducibility artifact** — 每个 generated output 写 config: git hash + 工具版本 + 输入数据 checksum + date
5. **Decision records** — 重大决策(架构选型 / API 变更 / 校准方法) 写正式 memo 到 `_wiki-methodology/_top/_decisions/`, 不埋 finding
6. **Lookback** — 每 phase 完结主动问 "上 phase 漏什么". 漏了回头补, 本计划文档更新 "P2 中发现 P1 漏 X, 已补"
7. **Index 同步原子操作** — 物理改 + 索引改 = 同一 commit. **不能让索引文件指向 not-exist 路径**
8. **P0/P1/P2 不动 active 代码** — 只整理目录 / 改 index / 标 active. P3+ 才动代码 + 加单元测

## 4. CATALOG.md 9 段通用结构

任何项目 v4 入口走这个骨架:

```markdown
# v4 TOP · AI 单一定位入口

## 1. 项目身份(0 阅读门槛)
- 目标 / 方法创新 / 当前 active 版本 / 主线 pipeline / 不变约束 / rollback 入口

## 2. "AI 定位不到" 索引(用户原话触发表)
| 用户原话 | 真正答案在 | 触发词补充 |
^^ 关键 — AI 续命第一站就是这表

## 3. 方法论实体(wiki/entities/)
表格: 实体 / 状态 / 触发词

## 4. 方法规范(_wiki-methodology/_wiki/_methods/)
表格: 文档 / 状态 / 触发词

## 5. 主线代码模块
- active 核心(红线)
- pipeline steps
- legacy (不动)

## 6. 测试
- 测试套件 / 路径 / 守护内容

## 7. 数据
- active baseline
- 原始数据(已 gitignore)

## 8. AI 接手 checklist(来项目第一件事)
□ 读 AGENTS.md(旧项目 CLAUDE.md)
□ 读 CATALOG.md
□ 读 active_pipeline_<version>.yml (红线)
□ 读 master_plan (当前)
□ 读 data_checksums (baseline)
□ 读 version_change_index
□ 跑 pytest <核心 tests>
□ 出问题: bash rollback_<reform>.sh --dry-run

## 9. 文档维护规则
- 新增实体 / 模块 / 警报 / 版本 都怎么登记
- 触发词原则(用户原话)

## 10. 版本简史
- V<x> ... V<x-3> 简短一行
```

## 5. 通用经验 / 反模式

### ✅ 通用经验
1. **不要大物理移动** — `.gitignore` + 文档索引 + LEGACY 标记 比 `mv` 安全得多(不断引用、可回退)
2. **active red-line manifest** 显式列绝不能动的核心文件 — AI 续命的安全网
3. **死链 CI 测** 守护索引一致性 — reform 后必加
4. **incremental P2** — index skeleton 前置, 不是 P1 完后才扫
5. **每个 generated output 带 reproducibility lock** — config / hash / git commit
6. **AGENTS.md 单一入口收敛**（退役旧 CLAUDE.md）— 不堆多个 ⭐ 入口, 单一指向 CATALOG.md, 其他 lazy-load
7. **Reform branch + tag 隔离** — 别在 master 上直接 reform

### 🔴 反模式
1. **裸 `mv` / `rm` 大批文件** → 无回滚, 引用断, v4 入口死链
2. **直接重写 CATALOG.md** 不先做 audit → 漏关键入口, 用户原话触发表不全
3. **P1 完了再 P2** → P1 已经把文件移走, P2 重头扫一遍找路径
4. **finding / decision 埋在 logs/** → AI 续命找不到重要决策
5. **改方法学不写 decision memo** → 论文 reviewer 喷 cherry-pick
6. **active 代码跟 legacy 混在同目录** → grep 命中大量噪音
7. **顶级目录 >15 个无索引** → AI 续命第一步就迷路

## 6. 触发 reform 的对话模板

用户说 "项目是不是太臃肿 / AI 看不清 / 整理一下 v4 TOP":

AI 主动跑 audit, 回答:

```
跑了 v4 audit (8 项):
✅ X 项: <清单>
⚠️ Y 项: <清单>
🔴 Z 项: <清单>

verdict: <OK / 小修 / 启动 reform>

如果 reform:
建议走 5 Phase: P0 snapshot (20 min) + P1 瘦身 (2-3h) + P2 索引 (1-2h) + P3+ (自定义).
要不要我列详细 todo 给你看?
```

用户确认 → 计划写进 TOP(`sixone-cli.py plan add` 登记各 phase 任务,详细方案作为 `_wiki-methodology/_top/` 下的计划文档链接).

## 7. 跟其他 share-top reference 关系

- `references/col4-lifecycle.md` — 死代码处理(audit-rot + purge-to-legacy)是 P1 的工具子集
- `references/upstream-sync-codemap-first.md` — 上游合并是另一种触发 reform 的场景
- `references/fs/research-phase-protocol.md` — 科研 phase stamp 是 P3+ 的内容组织
- 本 reform-protocol — 整体 reform 流程的总骨架

reform 跑的时候按 P0-P2 顺序走 reform-protocol, P3+ 走对应 reference 子流程.
