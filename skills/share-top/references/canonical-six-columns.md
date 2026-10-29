# 六列定义（唯一版本）

这是“六合一”的唯一定义；其它文档（包括 [six-in-one-philosophy.md](six-in-one-philosophy.md)）只解释为什么，不另立一套“六”。“唯一真源”不是一列，而是贯穿六列的不变量。

## 最小可行版本

| 级别 | 部分 | 规则 |
|---|---|---|
| 必需 | `AGENTS.md`（Claude/Codex 共读） | ≤60 行；身份、不变量、真源指针、验证命令；不写当前状态 |
| 必需 | `_wiki-methodology/_top/_task_plan.md` + `_questions/` | 问答格式（默认）：目标、现在、问答目录（镜像），每个问题一份工作本；旧的目录格式/Active Work 格式仍可读写；只经 `plan` 命令改（[qa-plan.md](qa-plan.md)） |
| 必需 | `_wiki-methodology/_top/_logs/` | plan 自动日志、note、`plan archive`/`plan compact` 移出的历史、复盘与交接 |
| 可选 | `_wiki-methodology/_top/_decisions/` | 可复用的决策理由与教训（旧 `_findings/` 里可复用的结论也归这里） |
| 可选 | `_codemap.md` | 一页纸：用途与入口，≤5KB，入口变了才更新；不写当前状态、不抄结构（结构交给 CodeGraph） |
| 可选 | `_meta/_registry.yml` / `_meta/_data_registry.yml` | 代码/工具登记；数据资产登记 |
| 可选 | `_wiki-methodology/_wiki/` | 领域知识（写法见 [wiki-writing-method.md](wiki-writing-method.md)） |
| 可选 | `_wiki-methodology/_tests/` | gate 清单与覆盖；软件项目的 trace/SSDO 读法 |
| 可选 | `_pipelines/` | 固化流程（`verify-pipeline` 盖章） |
| 可选（派生导航） | `_meta/_doc_tree.yml` + `_meta/_doc_summaries.yml` → `TREE.md`、`_tree/`、`CATALOG.md` | 知识树：跨列按主题导航；不是第七列，节点和逐份文档的归属/摘要各有一个中心登记，导航页全是派生物（[knowledge-tree.md](knowledge-tree.md)） |
| 退役 | `_codebook/` | 2026-09-24 起不再新建、不再盖章；已有的当普通文档只读 |
| 按需 | whole picture | 不属于 TOP；只在用户明确要网页/HTML 时生成 |

不再默认生成：roadmap、`_phases/`、`_six_dim_contract.md`、`_external_reviews/`、`_capabilities.yml`、`_naming.md`。已有项目里的这些文件继续可读，工具不要求补齐也不要求删除。

## 六列

| 列 | 真源（启用时） | 管什么 | 不管什么 |
|---|---|---|---|
| 1 Wiki | `_wiki-methodology/_wiki/` | 稳定的领域知识、方法、来源 | 当前任务、代码清单 |
| 2 Top | `_wiki-methodology/_top/`（计划、日志必需；决策可选） | 当前任务、时间线、可复用决策 | 代码/数据登记、长方法论 |
| 3 Tests | 任务上的 `gate=` + 项目测试；可选 `_wiki-methodology/_tests/` | 验收标准、测试入口、证据 | 空泛的“有测试” |
| 4 Code | CodeGraph（结构，实时、零维护）+ 可选 `_codemap.md`（用途与入口）+ 决策记忆（理由，`record for-file`）+ 可选 `_meta/_registry.yml` | 代码结构、入口、为什么这样写、工具登记 | 当前阶段、下一步；手写的结构副本 |
| 5 Lifecycle | 可选 `_meta/_data_registry.yml` + `_sandbox/ _tmp/ _legacy/ _outputs/` | 数据资产、临时物与归档落点 | 根目录散落文件 |
| 6 Whole Picture | 按需 `_whole_picture/` | 给人看的派生网页 | 任何真源 |

## 不变量

- 一个事实类型只有一个 owner；其它地方只链接或派生，不复制正文。
- 当前状态只在问答计划的工作本（问题状态、答案、尝试）或旧格式的步骤里；`## 现在`、问题摘要、Current Coordinate/stamp 都是 CLI 镜像。
- 没有结构化任务的计划是轻量模式，工具不对它提维护要求。
- Git 是版本骨架：提交/trailer/tag 记“发生了什么”，TOP 只记意图、当前坐标、决策理由（[git-version-lifecycle.md](git-version-lifecycle.md)）。
- 跨列引用用 owner 原生 key（`code:<id>`、`data:<id>`、`test:<id>`、`decision:<id>`），反向引用只派生不手写。
- 派生视图必须标明是派生的；可逐字节复现的派生页（如知识树的导航页）由工具清单管理，手改无效，清理只动带派生标记的文件。
- 说“缺能力/做不了”前，若项目有 `_meta/_capabilities.yml` 先查它（见 [capability-inventory.md](capability-inventory.md)）；新项目不默认创建。

## 验证

```bash
python3 ~/.claude/skills/share-top/scripts/sixone-cli.py plan validate <项目>
python3 ~/.claude/skills/share-top/scripts/sixone-cli.py doctor <项目>        # 死链、登记路径、plan validate、未记录改动
python3 ~/.claude/skills/share-top/scripts/sixone-cli.py doctor <项目> --full # 可选：旧版全量体检
```
