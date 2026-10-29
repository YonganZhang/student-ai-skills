---
name: research-universal
description: "通用研究项目目录架构 (v4) — 适用 LLM agent / 小型 DL / 算法建模 / 仿真 / 优化 / 实证 等单人 PhD 研究. 触发: 新建研究项目 / 初始化目录架构 / migrate 旧项目到 v4 / 应用 _ 开头规则 / 落地命名宪法 / 设置代码注册账本 / 联动 codemap 跟方法论"
---

# Research Universal Profile (v4 架构)

通用研究项目模板。**1 套架构覆盖所有研究类型**(开闭原则:对扩展开放,对修改半封闭)。

## 4 个设计准则(按重要性)

1. **简单不复杂化**(最重要)— 能用 50 行轻量代码达到的不上重型 framework
2. **可审计复现** — 任意一个数字能 30 秒反查源头
3. **AI 直觉友好** — 1 文件 1 概念,grep 友好,跨对话恢复
4. **节省 token** — 不让 cc 每次 load 全部元数据

## 11 个 `_` 开头顶级目录

```
project/
├── _codemap.md          # COL4 代码地图 / 注册路由；current 只链接 task_plan
├── AGENTS.md            # Claude/Codex 共读的唯一项目说明
├── _wiki-methodology/   # COL 1/2/3: 知识、进展、测试覆盖文档
│
├── _pipelines/          # 主流程(每个 pipeline 一章, step_NN_verb_noun.py)
├── _code/               # 代码(通用工具 + 领域工具, cc 按需建子目录)
├── _data/               # 数据(大文件 gitignore, 只 commit SHA256)
├── _outputs/            # 实验结果(v01..v108 全留)
├── _paper/              # 论文(扁平, reviews/ 放审稿)
├── _figures/            # 图(脚本 + 小图同源)
├── _refs/               # 参考资料(PDF/网页/任意杂物, 不分类)
├── _sandbox/            # 探索性代码(试错性工作)
├── _tmp/                # 临时(30 天提示归档)
├── _legacy/             # 老代码归档
└── _meta/               # 元数据 + 系统账本
```

## 命名宪法(强制)

详见模板里的 `_meta/_naming.md`:

1. **架构内目录/文件全 `_` 开头**(例外: `AGENTS.md` / `README.md` / `.git` / `.claude` / `.codex` / `.vscode`)
2. **函数 snake_case + 6 个动词起头**(`compute_*` / `load_*` / `save_*` / `validate_*` / `build_*` / `run_*`)
3. **step 文件**:`step_NN_verb_noun.py`(NN 2 位数)
4. **类 PascalCase + 单一名词**
5. **不在文件名加 `_v1/_final/_backup`**(Git 管历史)

## 单一真源 + 可选 helper

- **`_meta/_registry.yml`** = 代码/工具资产的结构化注册表,不登记数据集、当前状态和长知识正文
- 数据集、外部资产和运行产物另走 `_meta/_data_registry.yml` / `_meta/_runs.yml`
- registry 条目可带 3 个指针字段,但只做 link,不复制正文:
  - `method`: 指向 `_wiki-methodology/_wiki/` 的方法论/实体页
  - `tests`: 指向 `_wiki-methodology/_tests/` 或项目测试目录
  - `phases`: 指向 `_wiki-methodology/_top/` 的 phase/finding/decision
- `_code/register.py` / `_code/sync_wiki.py` 只能作为项目明确启用后的 helper; 没有脚本、没有 hook、没有测试证明时,不得写成默认自动化。

## 3 个核心工具

| 工具 | 干啥 |
|---|---|
| `_code/register.py` | 可选 AST 扫描 helper,用于 refresh `_registry.yml` |
| `_code/lint.py` | CI 校验(命名 + registry 一致性 + 文件名版本号) |
| `_code/sync_wiki.py` | 可选投影 helper; 只在项目文档声明生成区和 hook 后使用 |

## 跟六合一架构的分工

| `_codemap.md`(项目根) | `_wiki-methodology/_top/` / `_wiki-methodology/_wiki/` |
|---|---|
| COL4 代码地图 + 注册路由 + 测试指针 | 当前计划 / finding / decision / 方法论 / 公式推导 |
| 不承载 current | 不承载代码注册表正文 |

## 初始化新项目

```bash
bash ~/.claude/skills/share-top/scripts/init-research.sh <project_dir>
```

会自动:
1. 建必需部分:`AGENTS.md` + `_wiki-methodology/_top/_task_plan.md` + `_logs/`
2. 写 research `.gitignore` 基线
3. 建常用目录 `_code _data _outputs _figures _paper _refs _sandbox _tmp _legacy _meta`,每个带五问 `_readme.md`(已有的不覆盖)
4. 跑一次 `plan validate`,输出"下一步"指引

`_codemap.md`、`_meta/_registry.yml` 等用 `--with` 按需补。

## 旧项目升级

旧项目升级不是本 profile 的职责。用户明确要升级旧 TOP 时，读 `references/sub-skills/share-top-upgrade-old/REFERENCE.md`。

## 跟其他 skill 联动

- **死代码清理** → 跟 `share-top` 的 audit-rot.sh / purge-to-legacy.sh 共享 `_registry.yml` 事实源,1+1>2
- **六合一架构** → `_wiki-methodology/` 是方法论 / 知识 / 进展 / 测试覆盖层,本 profile 只管工程骨架
- **跨对话记忆** → 4 文件入口:`_codemap.md` + `AGENTS.md` + `_meta/_registry.yml` + `_meta/_runs.yml`

## 适用范围

| 项目类型 | 适用 |
|---|---|
| LLM agent / 多智能体 | ✅ 完美 |
| 小-中 DL 预测 | ✅ 适用 |
| 算法 / 数学建模 | ✅ 适用 |
| 仿真 / 优化 | ✅ 适用 |
| 实证 / 计量 | ✅ 适用 |
| 大规模分布式训练 | ⚠️ 部分(需附加 wandb) |
| 多人协同 (>3 人) | ⚠️ 部分(git merge .md 比 Excel 友好但仍需协调) |
| 高频探索 (每天 50 次试错) | ❌ 不适用 |

## 模板位置

完整模板在 `~/.claude/skills/share-top/templates/v4-architecture/`,可直接 cp 到新项目。
