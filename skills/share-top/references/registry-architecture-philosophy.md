# 注册架构元思维规范 v1.1 (Registry Architecture Philosophy)

> 问题: AI 面对问题时不查注册表, 而是 grep 或凭印象重造 —— 这不是态度问题, 是注册架构本身不可查、不可信。
> 本规范把这类失败抽象成 15 条元思维原则, 跨项目复用。原则来自真实项目的反复踩坑; 来由与版本演化见 `changelog.md`。

---

## 第 0 节 — 类比: 图书馆学 (核心比喻)

注册表本质是**代码资产的图书馆目录**.

| 图书馆 | 代码注册架构 |
|---|---|
| 书名 | `name` |
| 索书号 | `module:line` |
| 主题分类 | `tags` |
| 出版状态 (在架/借出/修复中/报废) | `status` (stub/wip/active/deprecated/archived) |
| 借阅记录 (谁借过, 哪天还的) | `consumed_by` + `last_verified` |
| 入馆时间 + 来源 | `introduced_in` + `wired_up_in` |
| 馆藏目录 | `_codemap.md` |
| 主题索引 + 著者索引 + ISBN | query CLI (按 status / tag / module 多维查) |
| 闭架书 | `superseded_by` / `deprecated_at` (不删, 标已废) |
| 馆员维护规则 | `_consistency_contract` 硬约束 |

**核心洞察**: **没有索引体系, 1500 本书跟 0 本没区别**. cc 不查 registry 不是态度, 是结构问题 — 当前 registry 像"全部书堆地上, 让你 grep". 升级后像"按主题摆架 + 查询窗口 + 借阅卡".

---

## 第 1 节 — 元思维原则(1–15)

### 原则 1: 卡片化 (Card-based)

每个 entry 是**自包含卡片**, LLM/cc 5 秒看完能用. 不只是 "name+module+line" 标签, 是含 motivation + 接线证据 + 风险评估的小型 markdown 卡.

```yaml
# ❌ 反例 — 不可读卡片 (示例)
- name: validate_units
  module: _code/io/unit_validator.py
  line: 73
  description: "validate units"  # docstring 一行, 没说为什么

# ✅ 正例 — 可读卡片 (示例)
- name: validate_units
  type: function
  module: _code/io/unit_validator.py
  line: 73
  why: "防止混用单位的输入静默进入下游计算"  # 一句话 motivation
  status: active
  wired_up_in: "<commit>"
  consumed_by_manual:
    - {path: "_pipelines/step_02_load.py:55", reason: "加载主路径统一校验"}
  affects_when_broken: ["单位混用的数据进入模型 → 结果数量级错误但不报错"]
```

### 原则 2: 渐进披露 (Progressive Disclosure)

cc 进项目**不读全 1500 行 registry**. 通过 CLI / index / 标签 / 派生视图渐进发现.

类比 RAG 渐进披露: 先只暴露 name + description, 需要时才取完整条目. registry 同理.

```bash
# 不是这样 (读全 YAML 浪费 token)
cat _meta/_registry.yml | head -2000

# 是这样 (CLI 按需查)
query_registry.py --by-status active --module <module>
query_registry.py --orphans                    # 列无 caller 的可疑函数
query_registry.py --report                     # 给 cc 看的人读 markdown
```

### 原则 3: 接线证据驱动 (Wiring-evidence-driven)

`status=active` 不是"我觉得它活着", 是**有 caller + commit hash + lint 通过**.

```yaml
# 严格 active 定义:
status_evidence:
  active:
    requires:
      - consumed_by_auto: non_empty        # ast.parse 找到 caller
      - wired_up_in: non_null              # commit hash 接入主流程
      - last_verified: within_<N>_days     # 最近核验过; N 按项目变更频率设定并写进 schema
    or_one_of:
      - introduced_in: this_phase          # 当 phase 内的不强制 verify (太严会阻塞开发)
      - tagged: experimental               # 标签豁免
```

配套原则: 状态有 owner, 变更有协议, view 是派生.

### 原则 4: 状态机严格 (Strict state machine)

status enum 严格定义, 转移有协议. 不允许"半成品"状态模糊.

```
stub      → wip                 (开始实施)
wip       → active              (接入主流程 + 测试过)
wip       → archived            (放弃)
active    → deprecated          (功能弃用, 留兼容)
active    → wip                 (大改造)
deprecated → archived           (清理周期)
archived  → (永不回 active)     (不删除, 标已废, 留历史)
```

**关键加 wip** — 这是"代码写一半还没接入主流程"的状态. schema 没有 wip 时, 半成品只能被标成 active 或不登记, 于是"写了逻辑但没接数据""只写不读"这类死代码反复出现.

### 原则 5: 可索引 (Indexability)

注册表用**倒排索引 + 多维查询 + 标签**, 不只是 "yaml 文件 + grep".

```yaml
# 派生倒排索引 (机器生成, 不进 git 当 cache)
_registry_index.yml:
  by_status:
    active: [func_a, func_b, ...]
    wip: [func_c, ...]
    archived: [...]
  by_tag:
    io: [load_raw, validate_units, ...]
    report: [render_html, export_table, ...]
  by_module:
    "_code/report/": [render_html, export_table, ...]
  orphans: [...]              # 无 caller 的可疑函数
```

CLI 查询用倒排索引 O(1) lookup, 不扫全文件.

### 原则 6: 单一真源 + 多派生视图 (Single source, multi view)

源数据 cc 写, 机器派生, 人读派生, 各取所需:

```
_meta/
  _registry.yml              # 源 (cc 写, 8 字段精简)
  _registry_resolved.yml     # 派生 (机器: auto+manual 合并 + verification)
  _registry_index.yml        # 派生 (机器: 倒排索引)
  _registry_report.md        # 派生 (人读: 按 status 分组的 markdown 报告)
```

避免多处维护 drift.

### 原则 7: 废除路径强制 (Mandatory disposal)

加新功能必须答"啥时该被删/合并". 没废除路径不准上线.

```yaml
# 加新 entry 时强制问 (lint 检查):
- name: <新函数>
  status: stub
  introduced_in: <phase>
  expected_lifecycle:
    - "v9: stub → wip (实施)"
    - "v10: wip → active (接入主流程)"
    - "v12: 如 LLM 模型升级到能直接 X, 本函数 deprecated"
  superseded_by_candidate: null  # 未来可能被谁替代
```

防技术债无限累积: 没写废除路径的"以后再接"占位代码, 往往永远没人接也没人删.

**硬约束**: status 转为 `deprecated` 时必须填 `superseded_by`(继任者)或 `retire_reason`(无继任时的退役理由), 否则 lint 报错.

### 原则 8: Boy Scout Rule (历史增量)

**不一次清洗历史**, 碰到旧函数顺手修. 不停下业务做全量人肉清洗 (易填假账).

```yaml
# 历史存量函数处理:
strategy: incremental
auto_label_default:
  has_caller: status=unknown_active        # 自动暂标, 不算保证
  no_caller: status=orphan                 # 待用户 review
  has_TODO_phase_b: status=stub
  
new_function_enforcement:                  # 新加函数必须填全 8 字段 (lint 拦)
  required: [name, type, module, line, why, status, introduced_in]
  required_when_status_active: [wired_up_in, consumed_by_manual]
```

### 原则 9: DoD 真证据 (Definition of Done with evidence)

未更新 Registry 至 active 视为未完成. status + wired_up_in + tests 真过才算 DoD.

```yaml
# 不变约束: 加进 Claude/Codex 共读的 AGENTS.md
project_dod_definition:
  - 代码完成 (function 写完, lint 过) ≠ 完成
  - 测试过 ≠ 完成
  - 必须满足: registry 内 status=active + wired_up_in=<commit> + 
              consumed_by 非空 + last_verified=今天 才算完成
```

配套原则: 接入某条路径的提交, 必须验证两端真的连上; 这里把它升级到 DoD 级别强制.

### 原则 11: 自举验证 (Self-bootstrapping verification)

**新 schema / lint / CLI 上线必须先用到自己身上跑通才算完**, 否则永远停在 doc layer.

**典型失败**: schema 新字段全定义齐了, 但主写入脚本不知道新字段存在, 存量条目的新字段填充率为零 —— 规范写好了, 实施时又踩同一个坑.

**自举验证 protocol**:
- 加新 schema 字段 → 用真实 entry(覆盖主要类型)填全这些字段 + commit, 并确认主写入路径会写它
- 加新 lint rule → 跑一次真实数据集, 看 false_positive/negative 接受度
- 加新 CLI 模式 → 用项目本身数据真跑, 文档贴输出
- **新代码进 registry 时强制走自己定义的卡片模板** (不豁免自己)

```bash
# 自举验证示例:
# 1. 加完 --verify-active 后, 立刻在本项目跑它, 看误报
# 2. 误报当场补白名单或修判据, 不留到下回合
python3 _code/_query_registry.py --verify-active
```

### 原则 12: 唯一标识 (Unique identity)

**registry primary key = `module + ':' + name`, 不只 `name`**.

**原因**: 多 module 都可能有 `main` / `run` / `parse` 等通用名. 只用 `name` 当 key → 后来的 entry 覆盖先来的, 历史丢失.

**实施**:
- schema 顶部声明 `primary_key: "module + ':' + name"`
- register.py 检查唯一性时用 module:name 复合键
- query CLI 输出含 module 前缀消歧义

### 原则 13: 物理对齐 (Physical alignment)

**registry 字段值必须对应代码真实存在, 不只 schema 合法**.

**反例**: `wired_up_in: "<commit>"` 这个 commit 真在 git log 吗? `consumed_by_manual: <file>:<line>` 这一行真有调用吗? 字段填了不代表物理对齐.

**实施**:
- `_code/_query_registry.py --verify-active` 真去 git log + grep 验证
- 加 `wired_up_in_physical: bool` 派生字段 (lint hook 物理读代码后填)
- weekly CI 跑全量物理对齐扫描
- false_positive 清单进 `_registry_resolved.yml.verification.wired_up_physical`

### 原则 14: 证据新鲜度 (Evidence freshness)

**注册字段值有时间衰减**. `wired_up_in` 今天是真的, 三周后可能已断.

**实施**:
- 派生字段加 `verified_at` (日期) + `verified_by` (enum: ast_parse/grep/manual/ci_hook/test_run) + `verification_method` (具体描述)
- query CLI 加 `--stale <days>` 列超过 N 天没 verify 的 entry
- weekly CI 跑 `--verify-active` 自动更新 verified_at

### 原则 15: 三阶段可达性判活死 (Phase-reachability liveness)

**这是原则 3 (接线证据) 的机器可证版**: 不靠人填 `wired_up_in`, 靠**调用图可达性**自动判活死。

**根因 pattern**: registry 每条 entry 都有 `entry:` (怎么单跑) → "能单跑" 被误当 "已接入主流程" → 登记了却没人调用的死代码混进去。常见的检查盲区: 只查 staged 文件 / 有 `__main__` 就豁免 / 用名字 grep 代替可达性。**症结: registry 记了"有哪些模块", 没记"谁调用谁"——缺 pipeline 调用图模型**。

**修法 — registry 顶部按生命周期声明三阶段入口 (每类可多个)**:
```yaml
pre_processing:  [...]   # 接入主 pipeline 之前 (改输入/预处理/注入提示词)
pipeline:        [...]   # 主流程入口 (核心多 stage 流水线)
post_processing: [...]   # 主 pipeline 跑完之后 (导出/渲染/发布/产物后处理)
```
`_meta/scan_reachability.py` 从三类入口顺 import+subprocess 调用闭包 → 走得到=活, 三类都走不到=**死代码** → pre-commit 阻断。**"其他都不用" — 不在三阶段调用链里的就是死代码**。

**关键设计 (避免重复造轮子)**: 可达性是 status 的**机器证据**, 不另起炉灶 ——
可达 → 应 `active`; 声明了阶段入口但走不到 → `wip` (未接线债); 啥都不是又走不到 → dead。
register.py 可读 `scan_reachability.py --json` 自动派生 status, 统一原则 3/4/15。

**为什么三阶段而非抽象 entrypoints**: 生命周期 (前/主/后) 比抽象"入口"更直观 ——
人一眼知道每个模块该在哪个阶段被调; 死代码 = "哪个阶段都不属于"。

**模板**: `share-top/templates/registry-architecture/scan_reachability.py` + scaffold
`_meta/_registry.yml` 已含三阶段空声明。装: `init.sh` 自动 cp + 接 pre-commit。

### 原则 10: 反哺架构 (Architectural feedback loop)

注册表不只是查询工具, 是项目自身的镜子. registry status 应该反向驱动**所有 facade**:

```
_meta/_registry.yml (单一真源)
  ↓ 派生
  ├─→ _codemap.md "系统完成度看板" 自动同步
  ├─→ 演示 / 报告里的系统清单自动同步 (不再 hardcode)
  ├─→ 项目一致性约束清单 (缓存、契约等) 自动核验
  └─→ pre-commit hook 强制 lint
```

避免人工二处维护 (手写的系统清单一定会和 registry 漂移).

---

## 第 2 节 — 模板与接入

- 跨项目模板: `share-top/templates/registry-architecture/`(schema、`register.py`、`query_registry.py`、`scan_reachability.py`、`run_pipeline.py`、pre-commit、`init.sh`)。
- 新项目用该目录下的 `init.sh` 接入(用法见同目录 `README.md`), 从第一天就有卡片 schema + 查询 CLI + 可达性检查。
- 与 v4 的关系: v4 不只是 "`_` 前缀目录", 还包括本规范的注册原则; pipeline 层见 `pipeline-registration-paradigm.md`。
- 项目自己的落地步骤、踩坑清单和取舍, 记在该项目 `_wiki-methodology/_top/`(findings / decisions), 不回写到本规范。
