# v4 目录架构 + `_` 前缀命名规则

> 详细文档(主 SKILL.md 简版)。**所有研究项目通用**,跨项目复用。

## 核心规则:`_` 前缀 = 架构内,无 `_` = 临时/外来

### 规则

| 文件/目录 | 含义 | 处置 |
|---|---|---|
| `_<name>` | 架构内,有规则约束 | 正常使用 |
| `<name>` (无 `_`) | 临时 / 外来 / 待归档 | **不在白名单** → 归档 / 改名 / mv / 删 |
| `<name>/` + README | 开发项目的模块目录（`frontend/`、`backend/`、`src/`…），用生态惯例名字 | README 按五问写清边界即视为架构内（模板 `templates/dir-readme.md`） |

### 白名单(永远不改)

```
AGENTS.md          # 唯一项目说明(Claude/Codex 共读)
README.md          # GitHub 渲染默认,保留(v4 主入口是 _codemap.md)
.git/              # git
.gitignore
.gitattributes
.claude/           # Claude agent config
.codex/            # Codex agent config
.obsidian/         # obsidian wiki
.vscode/
wiki-methodology/  # legacy 兼容期保留；新项目用 _wiki-methodology/
```

### v4 顶级入口与 11 个 `_` 工程目录

| 目录 | 用途 |
|---|---|
| `_codemap.md` | COL4 代码地图 / 注册路由; 当前状态只链接 `_wiki-methodology/_top/_task_plan.md` |
| `_wiki-methodology/` | COL 1/2/3: 知识、进展、测试覆盖文档 |
| `_pipelines/` | 主流程(step_NN_verb_noun.py) |
| `_code/` | 代码(通用 + 领域工具) |
| `_data/` | 数据(大文件 gitignore,只 commit SHA256) |
| `_outputs/` | 实验结果(各版本目录全留) |
| `_paper/` | 论文(扁平,reviews/ 放审稿) |
| `_figures/` | 图(脚本 + 小图同源) |
| `_refs/` | 参考资料(PDF/网页/任意杂物,不分类) |
| `_sandbox/` | 探索性代码 |
| `_tmp/` | 临时(30 天提示归档) |
| `_legacy/` | 老代码归档 |
| `_meta/` | 元数据 + 系统账本 |

## 命名宪法(强制)

### 函数命名
- **snake_case**
- **6 个动词起头**:`compute_*` / `load_*` / `save_*` / `validate_*` / `build_*` / `run_*`

### 文件命名
- step 文件:`step_<NN>_<verb>_<noun>.py`
- 工具文件:`<noun>.py` 或 `<noun>_<noun>.py`
- 测试文件:`test_<被测对象>.py`
- **禁止文件名加 `_v1/_v2/_final/_backup`**(Git 管历史)

### 类命名
- **PascalCase + 单一名词**

### 模型 / 数据集命名
- LLM 评委:`<vendor>/<model_family>@<api_version>`
- 数据集:`<source>_<scope>_<version>`

## 单一真源 + 指针联动

```
_meta/_registry.yml (代码/工具资产注册表)
        │
        ├── method → _wiki-methodology/_wiki/...         (方法论/实体指针)
        ├── tests  → _wiki-methodology/_tests/...        (测试指针)
        └── phases → _wiki-methodology/_top/...          (phase/finding/decision 指针)
```

每个 `_registry.yml` 条目可以带 `method` / `tests` / `phases` 指针。`_code/sync_wiki.py` 只在项目明确启用生成区和 hook 后作为投影 helper,不再作为 v4 默认事实。

## 触发清理逻辑(用户说"更新六合一架构"时)

cc 自动:
1. 跑 `~/.claude/skills/share-top/scripts/v4-cleanup.sh`
2. 扫顶级文件/目录,识别不合规:
   - 非 `_` 开头 + 非白名单 → 提议归档/移动/删
3. 输出处置清单
4. 用户确认 → 批量执行

### 处置规则

| 类型 | 默认目的地 |
|---|---|
| 临时下载/上传 | `_tmp/` |
| 外来资料(PDF/网页/截图) | `_refs/` |
| 老代码/数据 | `_legacy/<原名>-<date>/` |
| 应进 v4 主目录 | 提示用户 migrate 到 `_code/` / `_pipelines/` |
| 探索性试错代码 | `_sandbox/<date>_<topic>/` |
| 真无用 | 删(用户明确同意才删) |

## 跨项目应用

### 新项目初始化

```bash
bash ~/.claude/skills/share-top/scripts/init-research.sh /path/to/new/project
```

自动:
- 建 11 个 `_<dir>/`
- copy `_codemap.md` 模板(需要用户改顶部项目名)
- copy `_meta/` 全套(_naming + _schema/ + _registry + _runs + _changelog)
- copy `_code/` 可选 helper(register / lint / sync_wiki,以模板实际存在为准)
- 跑一次 lint; registry scan 仅作为可选初始化提示
- 跑首次 lint.py 校验

### 旧项目 migrate

7 步走(详见 `profiles/research-universal.md` § migrate):
1. 建 11 个 `_<dir>/` 骨架(老代码不动)
2. 逐步把核心代码 mv 到 `_code/` + `_pipelines/`
3. 建立或更新 `_meta/_registry.yml`,登记主流程入口和复用工具
4. 补 method/tests/phases 指针字段
5. 如项目明确启用 `sync_wiki.py`,再投影同步 `_wiki-methodology/` 生成区
6. 跑 lint.py 0 errors
7. 老代码 mv 到 `_legacy/`

**整个过程不一次性切换**:新老并存,直到数字对齐再切。

## 4 个设计准则(按重要性)

1. **简单不复杂化**(最重要)
2. **可审计复现**
3. **AI 直觉友好**
4. **节省 token**

## 跟传统框架对比

| 框架 | v4 vs |
|---|---|
| Kedro | 重型 framework lock-in,违反"一劳永逸" + "简单" |
| DVC | 数据版本专业但学习曲线陡,违反"简单" |
| MLflow | 服务端依赖,违反"一劳永逸" |
| Hydra | 配置组合灵活但 override 复杂,违反"AI 直觉" |
| **v4 自建** | **轻量(~700 行 Python)/ 文件系统即数据库 / AI 友好** |

## 跟六合一 wiki 的分工

- **v4 目录架构** = 工程层(代码 + 实验 + 元数据)
- **六合一 wiki** = 方法论层(算法 + 知识 + findings + tests)
- **联动靠 `_meta/_registry.yml` 的 method/tests/phases 指针; sync_wiki.py 只是可选投影 helper**

## 适用范围

| 项目类型 | 适用 |
|---|---|
| LLM agent / 多智能体 | ✅ 完美 |
| 小-中 DL 预测 | ✅ 适用 |
| 算法 / 数学建模 | ✅ 适用 |
| 仿真 / 优化 | ✅ 适用 |
| 大规模分布式 | ⚠️ 部分(需附加 wandb) |
| 多人协同 (>3 人) | ⚠️ 部分 |
| 高频探索 (每天 50 次) | ❌ 不适用 |
