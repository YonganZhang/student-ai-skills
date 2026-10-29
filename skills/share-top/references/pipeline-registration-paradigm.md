# Pipeline 注册范式 (Pipeline Registration Paradigm) — 通用 · 扣子与线

> 跨项目通用（research + dev/software）。**扩展**而非重写 `registry-architecture-philosophy.md`（15 原则=扣子/卡片层）。本文只加"**线/pipeline**"层。COL-4 的 pipeline 维度。

## 1. 一句话
**一切皆 pipeline。** 不分预/后处理——2 函数是 pipeline，22 步也是。每条都**必注册 + 必注释**（有名字、有"干啥"），才能被一句话命令、被 AI 低 token 看懂、跑起来零遗漏。

## 2. 模型：registry 管扣子，manifest 管线（**两个真源,各管一半,不重叠**）
| | 真源 | 内容 |
|---|---|---|
| **扣子 step** | 项目的函数/步骤注册表（v4 = `_meta/_registry.yml`；无 v4 = `_pipelines/_steps.yml`，**一个项目只一份**） | id / desc / 入口(`fn`\|`cmd`\|`composite`\|`manual`) / status / 接线证据 / 唯一标识（沿用 15 原则 schema） |
| **线 pipeline** | `_pipelines/<name>.yml` manifest | 引用扣子(`ref`) / 依赖 / 参数覆盖 / 条件 / 产物断言 |
| 派生视图 | `_usage.md` / `<name>.map.md`（机器生成,不进 git 当真源） | 全景 DAG + 数据进出维护文档 + 复用反向索引 |

- 扣子载体**四选一**：`fn`(`module:func`,research/algo) \| `cmd`(CLI argv 数组,dev/工具) \| `composite`(包已有 orchestrator) \| `manual`(人工/AI 产出,**不由 executor 自动生成**)。
  - `manual` 可验证条件 = manifest/registry 声明的人工产物路径 + resume 判定(产物存在且过校验则视为完成)。`llm`/AI 创作只是 `manual` 的执行提示(`hint:`),**不是独立自动执行类型**——执行器对 manual 扣子只"提示+查产物+续跑",绝不假装自动产出。
- **复用 = 多条线 `ref` 同一扣子**。**全量方案 = 官方推荐的主产物路径**(覆盖主流程必需扣子;不硬塞 experimental/deprecated/manual-only)。

## 3. 三铁律（违反则混乱复发）
**A · 必注册 + 必注释** — 每条 manifest 顶部 `pipeline:`(id,用户喊它命令你)+ `desc:`(一行:给谁/产出啥)。无注释 = 不知叫啥干啥 → 无法命令 + AI 每次重读全代码费 token。
**B · 不得双真源** — 扣子真源归 registry,线真源归 manifest。**manifest 里禁止复制 step 描述/入口**,只 `ref` 引用 registry key;复制 = 第二真源 = 漂移。
**C · 范式不日记** — 注册项是 SPEC（契约）不是流水账（"我这次干了啥"）。维护文档/全景图全自动派生,不手写。

## 4. Step 引用规范
manifest 内 step 用本地 `id`(别名) + `ref`(指向 registry 唯一键,如 `module.path:func` 或 `cmd:script_id`)。本地 id **不冒充** registry identity。registry 已 archived 的扣子不许被 active 线引用。

## 5. Pipeline manifest schema
```yaml
pipeline: <snake_case_id>           # 必填:用户命令名
desc: "一行:给谁用、产出什么"        # 必填注释
domain: <freeform_tag>              # research/dev/data/ml/ops... 仅检索标签
status: active|wip|deprecated|archived
entry_role: pre|main|post|aux       # 仅入口分类;pre/post 仍是独立 pipeline
verified_at: <YYYY-MM-DD|null>             # 人读: 上次核验日期
verification_method: validate|dry_run|full_run|manual
verified_steps_hash: <sha256|absent>      # 机器印记: sixone-cli verify-pipeline 唯一盖,手填=伪造
verified_at_commit: <git-sha|absent>       # 盖章那刻的 HEAD(affected 快路径 diff 基线)
params_schema: { <param>: {type: str, required: true, desc: "..."} }
steps:
  - id: <local_alias>
    ref: <registry_primary_key>
    needs: [<local_alias>...]       # DAG 依赖(无则按列序)
    optional: false
    condition: <expr_or_null>
    params: { <k>: <v> }            # 该线对扣子的接口覆盖(别建扣子变体,在线传参)
    success: { outputs_exist: [<相对产物>] }
```
> 只需 `needs/optional/condition/params/success` 五个执行字段。别上完整调度引擎(Airflow)。

## 6. Validator / executor 契约
**`validate_pipeline.py` 最少查**(挂 pre-commit):
- 每个 `ref` 在 registry 存在且未 archived
- `needs` 无环;`optional/condition` 不破坏必需产物
- 扣子物理入口可验证(`fn` import 得到 / `cmd` 脚本存在 / `composite` 入口在 / `manual` 声明产物路径 + resume 判定)
- `success.outputs_exist` 可解析
- pipeline `status` 与 `verified_at/method` 证据一致

**`run_pipeline.py`（I/O 契约稳定后再建）**：读 manifest 按拓扑跑 → 跑完校验 `success` → blocking 短路 → 写 `pipeline_run.json`(防篡改:step/resolved-entry/exit/duration/sha256/outputs 命中)。`manual` 扣子(含 llm/AI 产出)=暂停-续跑(产物存在则秒跳=幂等),**执行器不假装自动创作**。

## 7. 印记自动失效(复用 CodeBook hash-trust)

**痛点**:`verified_at` 是裸日期,改了 step 代码不会自动失效,只能等下次 doctor 撞见。
**机制**(复用 CodeBook 的 `_node_hash`/`codebook_trust` 同款引擎,无 hook 无调度):
- `verify-pipeline <name>` = 唯一合法盖印记口:校验每个 step 的 `ref` 在 registry 可解析 + 代码文件存在 → 盖 `verified_steps_hash`(= 契约子集 `id/ref/needs/params/success` + 各 step 代码文件**内容** 的 sha256)+ `verified_at_commit`。手填印记一律剥除(防伪)。
- `doctor`/`brief` 实时重算比对:**step 代码或接线一改 → hash 变 → 自动 `stale`**(`stale` 进 doctor verdict,gate 住"完成";`broken`=ref 解析不了→warn;`unverified`=没盖过→不计,不破坏没 opt-in 的线)。
- 降噪:契约 hash **不含** `desc`/`verified_*`/注释 → 改说明不误判;只有 identity/接线/step 代码变才失效。
- `affected --since <commit>`:git diff → 反查命中哪些 CodeBook 节点(`tracked_paths_hint`)+ pipeline(step 代码)→ 给"该回写哪些 owner"清单;codegraph 仅在索引对齐 HEAD 时当 impact 放大器(顾问,非硬闸)。

> 一句话:`verified_at` 给人看,`verified_steps_hash` 给机器判;代码变即失效,不靠 AI 记得。

## 7. 5 分钟落地（任何新项目）
1. 在项目 step 注册表登记 3 类扣子:主入口 / 关键中间处理 / 最终产物检查。
2. 新建 `_pipelines/full.yml`,只 `ref` 引用扣子,不复制入口。
3. `validate_pipeline.py _pipelines/full.yml` — 先保证引用/DAG/入口/outputs 可验证。
4. `gen_pipeline_map.py` 出 `full.map.md` + `_usage.md`。
5. `_codemap.md` **只链接** `_pipelines/_usage.md`,不复制步骤表。

## 8. 与 15 原则的映射（本文不重定义,只继承）
| 15 原则 | pipeline 层怎么继承 |
|---|---|
| 单一真源 | 扣子不复制,manifest 只 `ref` |
| 接线证据 | run evidence / outputs / 可达性 反写为派生证据 |
| 状态机 | pipeline 也有 status,转移证据来自 validator/run |
| 唯一标识 | 扣子用 registry primary key,pipeline 用 snake_case id |
| 物理对齐 | `fn/cmd/composite/manual` 入口均须可验证 |
| 证据新鲜度 | `verified_at` / `verification_method` |
| 三阶段可达性 | `entry_role` 仅入口分类,不否定 pre/post 也是 pipeline |
| 卡片化/渐进披露 | manifest 一行 desc + 派生 map,AI 按需读不啃全代码 |

> 🔴 pipeline 层**不得重定义** registry 的 status/identity/verification/deprecation 语义,只消费 + 把 run 证据反写为派生。

**Why 通用**：把"项目特定流程描述"统一成"registry 扣子 + manifest 线",任何项目(科研/开发)套同一范式 → AI 进项目读 `_usage.md` + `<全量>.map.md` 即懂全局、可被一句话命令、跑起来零遗漏。

## 9. 写时标记 — 扣子身份在写代码当下声明(不靠事后扫描猜)

**病根**:register.py 事后扫每个 `def` 反推哪个是扣子 → 噪音/死代码混入/重要的没标出来。
**解法**:写函数当下在 docstring 打标记,registry 由"写时声明"派生。扩 pipeline 维度:

| 标记 | 值 | 含义 |
|---|---|---|
| `@role:` | `step`/`entry`/`helper` | step=线上扣子;entry=线主入口;helper=内部工具(非扣子) |
| `@pipeline:` | `<name>` 或 `<name>.<stage>` | 属于哪条线 |
| `@needs:` | `a.csv, b.csv` | 依赖输入(逗号分隔) |
| `@produces:` | `x.png` | 产出(逗号分隔) |

canonical 带冒号 `@role: step`(跟 `@status:` 一致);register.py 解析容忍省略冒号。
**载体不锁死 docstring**:docstring 标记是低摩擦默认(研究脚本友好);软件项目可用 **decorator**(`@pipeline_step(role="step", needs=[...])`, import 时即校验、IDE/lint 接得上)或 manifest 显式声明作等价更强形式。规则绑定的是"**写时声明角色**", 不是"必须 docstring"。
**写时纪律**:进**主流程 / public / 可复用**的函数,写的当下必须声明 `@role:`(+ 适用的 `@pipeline/@needs/@produces`);内部一次性 helper 不强制(标 `@role: helper` 或不标)。本条是项目级纪律,真源就是本节,全局规则不复制(share-arch「边界」:软件项目的重流程规则放项目级)。

## 10. 线执行器 run_pipeline.py(本范式承诺过、现已交付模板)

`templates/registry-architecture/run_pipeline.py`:读 manifest → 按序跑 → 三件事:
- **fail-loud needs 检查**:每步先查 needs 文件存在,缺了停(不静默跳过)→ 防"无记忆 AI 乱序跑碎片"的护栏。
- **LOCK 写保护**:manifest 声明 `lock_dirs:` 的目录,任何步骤改写即中止;`--allow-locked-write` 才放行。
- **产物新鲜度**:success.outputs_exist 校验"本次新生成"(mtime≥step 开始),不靠仓库已有同名旧文件假阳性。
- **定位 = cmd-runner**:执行器只跑 step 入口脚本(`python <module>`),按 manifest **声明顺序**跑;`needs:` 在 manifest/`@needs:` 里一律指**输入文件**(不是 DAG step-id, 避免与 §5 语义撞——真要 step 级依赖图用 `after:` 或直接上 Snakemake)。
- **不自建 DAG 引擎**:无拓扑排序 / 无缓存 / 无 partial re-run。研究者要"只重跑第 N 步 + 自动判新鲜度 + 并行" → **升级路径 = Snakemake**(本 runner 只做"有序 + fail-loud + LOCK 护栏 + trace"的轻量层)。

## 11. 定稿:完整 inventory + 扣子默认视图(硬边界)

registry 持**完整 inventory**(每个函数 + status + 可达性 → 保可发现性 + 死代码检测, 不丢 15 原则能力),但 **`role` 是一等公民, 所有默认视图只消费扣子子视图 `role∈{entry,step}`**:
- `query_registry.py --report`(cc 进项目)、`_codemap.md` 摘要、`run_pipeline` → **默认只看扣子**。
- 完整 inventory 只能显式 `--all` / `--inventory` 进入(去重 / 影响面 / dead-code 分析时)。

🔴 **硬边界是命门**:默认视图必须只吐扣子;一旦默认报告又回到"列全部函数", 必腐烂回噪音。可发现性靠 inventory 显式查 + 文件系统/LSP, 不靠默认糊一脸。

> 项目可以选更严格的"未标记不登记"作为收紧特例(在项目 AGENTS.md 或 registry 头部声明);跨项目默认仍走"完整 inventory + 扣子默认视图"。
