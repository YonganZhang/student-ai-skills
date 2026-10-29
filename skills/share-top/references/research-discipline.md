# 科研模式思维规范 — 从软件手册吸收的 3 条

> **适用**: research profile (`share-top/profiles/research-universal.md`)
> **不适用**: 完整软件工作流 — 科研有自己节奏, 本文件只吸收 3 条"通用思维 + 工具" 层规范, 不搬全套
> **跟论文写作技能关系**: 论文撰写走专门的论文写作技能(`share-sci-write`,本包未包含). **本文件管的是"实验设计 / DL 代码架构 / 数据 pipeline / debug" 阶段的思维纪律**, 不管"论文写作" 阶段
> **来源**: 从软件模式手册 (`dev-mode-handbook.md`) 挑出跨用且需科研术语适配的 3 条改写 (来由见 `changelog.md`)

---

## 总则

3 条核心思维, 都按 **触发-判定-动作-验收** 四件套写, 让"下次该怎么办" 可执行. 不日记, 不流水账.

## 跟现有 v4 科研基础设施关系

research 模式 v4 已经有:
- `_meta/_registry.yml` 代码/工具/主流程入口 registry (method/tests/phases 只做指针)
- `_meta/_data_registry.yml` 数据资产 registry
- `_meta/_runs.yml` 实验/运行记录
- `_code/register.py` 可选 AST 扫码 helper
- `_code/lint.py` CI 校验
- `_code/sync_wiki.py` 可选 wiki 生成区投影 helper

本文件**扩展**:
- **RC-1** 把科研产物按类型注册到 owner 表,再用 registry 指针串联代码/数据/实验/图/公式
- **RC-2** 在 debug 时把单点修升级到 wiki 方法论 (反推一类通解)
- **RC-3** 给"实验设计 / DL 代码架构" 显式划骨架 vs 血肉边界

---

## RC-1. 科研产物分列注册 — 不把所有东西塞进代码 registry

**核心思想**: 科研项目的产物**不止代码**。代码、数据、实验、图表、公式、文献各有 owner 表; 它们通过 id / path / bibkey 互相链接。否则 reviewer 问"这个 figure 怎么来的" / "这个数字从哪个实验出" → 找不到 = 不可审计复现。

### 触发
- 新提一个**假设** (hypothesis)
- 跑完一个**实验** (含 hyperparam / dataset / seed / result)
- 加入一个**数据集** (raw 或 processed)
- 画出一张**主图 / 子图 / ED / Supplementary**
- 写一个**关键公式** (自推 / 引用)
- 引一篇**新文献** 进 paper

### 判定
- 产物是否会被"论文 / 报告 / 下一阶段 / reviewer" 消费? **是** → 必须进对应 owner 表; **否** (纯探索) → 入 `_sandbox/`
- 介质形式不限: yml / bib / 表格 / 目录 manifest 任一. 关键是**单一真源 + 可 grep + 每一跳都有显式 id / 路径, 能直接反查到源头**

### 动作
按产物类别进对应 owner 介质 (科研 v4 扩展):

| 产物类 | 单一真源介质 (推荐) | 必带字段 |
|---|---|---|
| 假设 | `_meta/_hypotheses.yml` | id / 提出时间 / 测试方法 / 状态 (pending/confirmed/refuted) / 对应实验 id |
| 实验 | `_meta/_experiments.yml` 或 `_outputs/v<NN>/_meta.yml` | id / 触发假设 id / dataset / model / hyperparam hash / result metric / log path / seed |
| 数据集 | `_meta/_data_registry.yml` | name / source URL / version / sha256 或 provenance / processing pipeline (step ids) |
| 图表 | `_meta/_figures_index.yml` | name (`Fig1` / `ED3a` / `S2`) / 由哪个 script 产生 / 由哪个实验 id 喂数 / 进论文哪 section |
| 公式 | `_meta/_equations.yml` | id / latex / 出处 (引文 bibkey / 自推 / 教科书) / 在哪 section 用 |
| 文献 | `_paper/references.bib` (事实标准) | bibkey / type / 作者 / year / 摘要一句话 / 在哪 section 引 |

**大批量同构的诚实判断**: 100 个 hyperparam grid 用**父目录通配规则**注册 1 条 (`_outputs/v05_grid_*/`), 不为讨好凑数逐条独立注册 (会变维护噩梦).

### 验收
- 跑 `_code/lint.py` (现有工具) **扩展校验项**: 每条代码 registry entry 在 runtime 真消费 ≥ 1 次; 数据/实验/图表 owner 表的 orphan 单独检查
- 死实验检查: `_meta/_experiments.yml` 里**不在任何 figure / hypothesis 引用**的 entry → 确认无消费者、结论已记录后, 归档 `_legacy/experiments-archived-<date>/` 或重定向到 wiki finding
- 反查测试: 论文里任一数字, 都能沿 owner 表逐跳追到 (figure id → experiment id → log path → seed → data hash), 中间任何一跳需要靠搜索或猜 = 不合格

---

## RC-2. 顶层范式 vs 局部 — 改 bug 时反推一类方向通解

**核心思想**: 改 bug 不要总解决单点. 站到顶层看"这 bug 属于哪一类", 反推**算法层抽象** 覆盖所有同类 case, **一网打尽**, 写进 wiki 方法论. 不在代码里堆叠 if-else 黑名单.

### 触发
- 改**数据预处理** bug (e.g. NaN / 单位 / 时区 / 编码 / shape mismatch)
- 改**数据后处理** bug (e.g. 量纲转换 / 边界裁剪 / 异常值过滤)
- 改**算法实现** bug (e.g. 数值不稳 / 梯度爆炸 / loss 收敛异常 / dataloader 顺序)
- **关键升级信号**: 同类 bug 已在不同 dataset / 不同 pipeline / 不同 model 出现 **≥2 次**

### 判定
- 单 dataset 边界情况 / 一次性偶发错 → 局部修, 加注释, 收工
- **同类 bug 已重复 ≥2 次** = 这是**整类问题**的局部表现, 必须升级到顶层
- 自问: "这 bug 属于哪一类?" — 数据格式假设错? 缺失值处理范式错? 输入域 / 输出域定义错? 物理意义违反? 数值精度边界? 这就是**类别名**

### 动作
1. **不为单 bug 加 if-else / try-except 黑名单** — 那是症状治疗
2. **反推可覆盖所有同类 case 的算法层抽象** — e.g.
   - 单点: "纬度 90.001 越界, clip 到 90" → 顶层: "所有地理坐标输入走统一 `validate_coords()`, 越界用 `nan` + log warning, 不静默 clip"
   - 单点: "feature X 在 dataset B 有 NaN 但 dataset A 没有, 加 fillna(0)" → 顶层: "所有数据加载后过 `_validate_features()`, NaN 处理策略 (drop/impute/keep) 由 dataset config 显式声明, 不在算法侧静默"
3. **写到 `_wiki/_methodology/<topic>.md`** 升级为方法论. 写"凡 X 类情况, 用 Y 解, 因为 Z" 元规则, 不写"具体 case A B C 怎么修" 黑名单
4. **写完到 `_wiki/_methodology/` 后**, 跑全部历史 bug case (regression set) 验证同类 bug 1 次解决

### 验收
- `_wiki/_methodology/` 新增 / 更新 1 篇方法论文档, 元规则形式 (X→Y because Z), 不是 case 列表
- 代码层: grep 无堆叠特例 if-else (5 个特例 if-else → 1 个统一 validator 函数)
- regression set: 历史同类 bug case 全部 1 次过 (不是逐个 patch)
- `_meta/_registry.yml` 函数 entry 的 `method` 字段链到刚写的方法论页

**反例**:
- 🔴 `data_preprocess.py` 里 5 个 `if dataset_name == "X": fix_xxx()` 分支 = 黑名单, 必须重写为统一 validator + config 驱动
- 🔴 改 bug 后只 commit 代码不更新 wiki = 知识漂移, 下次同类 bug 再踩
- 🔴 元规则写成"碰到 case A 这样办, 碰到 case B 那样办" = 还是黑名单不是范式

---

## RC-3. 实验 / DL 代码架构骨架先做, 调优细节落 todo

**核心思想**: 设计新实验 pipeline / 搭 DL 模型 / 写实验 framework 时, 先把**端到端主干跑通 1 batch**, 性能优化 / 超参微调 / 边界处理一律入 `_top/_experiment_todos.md`, **不当场做**. 防止"主干没通就掉进 mixed precision / DDP 细节" 浪费 1 天.

⚠️ **本规则不适用论文撰写阶段** — 论文骨架先做走论文写作技能(本包未包含).

### 触发
- 设计**新实验 pipeline** (新 dataset / 新 model / 新 ablation)
- 写**DL 模型代码** (新 architecture / 新 loss / 新 optimizer)
- 搭**实验 framework** (新 sweep / 新 evaluation harness)
- 加**新 ablation 实验** (改一个变量重跑 baseline)

### 判定
当前要做的是 "主干跑通 + 接口齐整" 还是 "性能优化 / 超参微调 / 边界处理"?
- **主干** (data loader / model forward / loss compute / optimizer step / eval metric 5 件套) → 立即做
- **血肉** (mixed precision / DDP / 数据增强细节 / 超参网格 / lr scheduler / early stopping / 学习曲线绘制) → **一律入 todo, 主干通了再回头**

### 动作

**主干顺序** (每个完成 + 跑 1 batch sanity check 才下一个):
1. **data loader** → 输出 shape / dtype 正确, 跑 1 个 batch 不报错
2. **model forward** → 接收 loader 输出, 出 shape 正确 logits, 跑 1 个 batch 不报错
3. **loss compute** → 出标量 loss, `.backward()` 不报错 (梯度有数)
4. **optimizer step** → step 1 次后参数真更新 (用 hash 验证 weight diff)
5. **eval metric** → 接 1 个最小 metric (accuracy / MAE / 1 个 sample 的 perplexity), 出数字

**端到端跑 1 个 batch → 1 个 epoch 跑通 → 才允许加血肉**.

**血肉入 todo** (写到 `_top/_experiment_todos.md`):
- "TD-001 mixed precision (AMP) 接入, 测速度 / 精度 trade-off"
- "TD-002 学习率 schedule (cosine + warmup) 接入"
- "TD-003 DDP 多卡, 测 scaling efficiency"
- "TD-004 数据增强 (RandAugment / mixup), 测对 ID/OOD acc 影响"
- "TD-005 early stopping 接入"

每条带 (编号 / 触发条件 / 影响范围 / 回收阶段).

### 验收
- 主干 pipeline 能**端到端跑通 1 epoch** + 出最小 metric 数字 (哪怕 metric 烂)
- `_top/_experiment_todos.md` 列出本轮推迟的全部血肉细节 (数量以实际为准, 不为显得周全凑条目)
- 主干 commit history 不带 "fix XYZ mixed precision 优化" 的 noise — grep commit log 无优化类 commit 在主干阶段
- 跟用户汇报时 "我做了 X 主干 / 我**没做** Y 血肉细节 (入 todo)" (CC-1 反讨好 + QF-1 不夸大同源)

**反例**:
- 🔴 还没把 forward pass 跑通就开始接 DDP — 主干没通就调优 = 浪费
- 🔴 一上来写 50 行 lr scheduler 但 loader 还没出 shape 正确 batch
- 🔴 主干都没出 metric 数字就开始网格搜索超参 — 搜了也不知道意义

---

## 9. 引用 / 溯源

- **吸收来源**: `share-top/references/dev-mode-handbook.md` (v2, 软件模式手册)
- **对应规则**: CC-2 Universal Registry → RC-1 / CC-5 顶层 vs 局部 → RC-2 / SW-1 骨架先 → RC-3
- **跨模式天然适用 (本文件不重复)**:
  - CC-1 反讨好 / CC-3 whole picture / CC-4 引用验证法
  - WF-1 plan mode 节奏 / WF-2 三路检查 / WF-3 收件箱 / WF-4 切片 sub-agent / WF-5 报告 schema / WF-6 元反思
  - QF-1 不夸大 / QF-3 凭证 NEVER / QF-6 消费方判定
  - IP-1~8 全部交互协议
  - AR-2 append-only event sourcing (科研 reproducibility 死命要求)
  - AR-4 信息架构单一真源
  - → cc 接科研项目时直接读软件手册对应条目即可, **不需要在本文件再写**
- **跟 research v4 工具链关系**:
  - `_meta/_registry.yml` / `_meta/_data_registry.yml` / `_meta/_runs.yml` / `lint.py` 既有, RC-1 负责跨 owner 指针,不把所有产物塞进单一 registry
  - `_wiki/_methodology/` 既有, RC-2 升级用
  - `_top/_experiment_todos.md` 新增 (类比 `_future_todos.md`), RC-3 用
- **跟论文写作技能关系**: 论文撰写 / outline / rebuttal 走论文写作技能(本包未包含), 本文件不涉
- **产物路径**: `~/.claude/skills/share-top/references/research-discipline.md`
