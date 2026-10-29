# Lint Armor — v4 TOP 一劳永逸防漂线

> 目标: 让 registry / wiki / 代码三者的对齐可机械验证, 死代码 / 死方法论自动暴露. 来由与版本演化见 `changelog.md`.

## 痛点 (为什么需要 lint armor)

v4 TOP (wiki / 进展 / 测试 / 代码注册 / 文件生命周期) 是声明性单一真源, 但**声明跟实际容易漂移**:

- registry 写 "v4 已合", 实际反向 `sys.path.insert(<旧代码目录>)` 调老 lib (假合)
- wiki entity 写了 `[[_xxx]]`, 实际代码 0 函数引用 (死方法论)
- pending_migration 标 `status: complete`, 但 target 文件根本不存在 (假声明)
- 这些问题**自己不会暴露**, 直到下一次审计发现 → 修一处漏十处

## 解决方案: 8 道门 lint armor (项目级)

| # | 门 | 严格度 | 检测内容 |
|---|---|---|---|
| L1 | 根目录命名 | block | 顶级文件/目录 `_` 开头白名单 (gitignored 自动跳) |
| L2 | 函数命名 | block | snake_case + 6 个动词起头 (compute/load/save/validate/build/run) |
| L3 | 文件名禁版本号 | block | 禁 `_v1.py / _final.py / _backup.py` (Git 管历史) |
| L4 | registry ↔ code 双向 | warn | missing (代码有 registry 无) / orphan (registry 有代码无) |
| L5 | phantom_function | block | registry 引用的 module 文件 + AST 找得到该函数 |
| L5b | stub_only_function | warn | 函数体仅 `pass`/`NotImplementedError`/空 return → 真合了吗? |
| L6 | phantom_method | block | registry method `[[_xxx]]` → wiki entity 真存在 |
| L8 | false_migration_claim | block | pending_migration `status=complete` 必须跑 `archival_gate_check` 通过 |
| L9 | reverse_legacy_import | block | 禁 v4 代码反向导入旧代码目录 (`sys.path.insert(<旧目录>)` / `from <旧目录>.` / `import <旧目录>.`; 模板里的旧目录名是占位, 按项目改) |

**砍掉的 2 道门 (平衡性, 避免矫枉过正)**:
- L7 dead_methodology (wiki 0 函数引用): 纯概念类 entity 本来就没有函数实现, 会高噪音误报
- L10 hardcoded_legacy_path: 跟 L9 大部分重叠, L9 抓 import 已足够

## archival_gate_check 白名单 (v2.1 安全设计)

任意 bash 跑有注入风险 + 跨平台脆弱. 改纯 Python 白名单:

```yaml
pending_migration:
- old_path: <旧代码目录>/lib/client.py      # 示例
  estimated_target: _code/<域>/client.py
  migration_status: not_started  # 4 档: not_started / stub_only / partial / complete
  archival_gate_check: target_exists  # 枚举值, 非任意 bash
```

支持的 check 枚举:
- `target_exists` — `estimated_target` 文件/目录真存在
- `no_reverse_import` — v4 目录无反向 `sys.path/import <旧目录>.`
- `no_todo_marker` — target 文件无项目约定的 stub 标记 (如 `TODO` + "未接真实实现" 类注释; 正则按项目改)

新增 check 在 `lint.py:GATE_CHECKERS` 里加纯 Python 函数, 不开放任意 bash.

## migration_status 4 档枚举

| 状态 | 含义 |
|---|---|
| `not_started` | target 文件不存在 |
| `stub_only` | target 存在但仅 import / re-export, 无实质实现 |
| `partial` | 部分函数 migrate 完, 其他 thin call 老 lib |
| `complete` | 老代码可 rm/mv _legacy, V4 无反向引用 |

非枚举值 (拼写错) → L8 报错 `L8_BAD_STATUS`.

## pre-commit hook 一键装

```bash
# 新项目初始化时 (或 clone 后):
bash _scripts/_install_hooks.sh

# 内部做的事:
#   git config core.hooksPath _scripts/_git_hooks  # 跟代码版控 + 跨 worktree
#   ln -s ../_pre_commit_lint.sh _scripts/_git_hooks/pre-commit
```

`--no-verify` 旁路: 紧急 fix 用, 但**主干上长期违反 = lint 失效**. 建议未来在 CI 里强制跑 lint.

## 模板文件

`~/.claude/skills/share-top/templates/lint-armor/` 含 6 文件 (新项目 copy 即用):
- `lint.py.template` — 8 道门核心 (~20K, Python stdlib only)
- `register.py.template` — AST 半自动扫 registry (`--scan` / `--add` / `--list`)
- `_scripts/_pre_commit_lint.sh` — pre-commit hook
- `_scripts/_install_hooks.sh` — 一键装 (设 core.hooksPath + symlink)
- `_meta_schema/_registry_entry.yml` — function + pending_migration schema
- `_meta_schema/_wiki_entity.yml` — wiki entity 反链 section schema

复制方式:
```bash
# 新项目根:
mkdir -p _code _scripts _meta/_schema
cp ~/.claude/skills/share-top/templates/lint-armor/lint.py.template _code/lint.py
cp ~/.claude/skills/share-top/templates/lint-armor/register.py.template _code/register.py
cp ~/.claude/skills/share-top/templates/lint-armor/_scripts/* _scripts/
cp ~/.claude/skills/share-top/templates/lint-armor/_meta_schema/* _meta/_schema/
bash _scripts/_install_hooks.sh
```

**适配点**: lint.py 顶部常量按项目调整:
- `ALLOWED_VERBS` — 项目命名宪法的动词白名单
- `ROOT_WHITELIST` — 顶级目录白名单 (历史遗留中文目录等)
- `CI_TOOL_FILES` / `CI_TOOL_DIRS` — 项目内自身 meta 工具 (lint / register 等), 不强制业务命名
- `WIKI_ENTITY_DIR` — v4 wiki 实体目录 (默认 `_wiki-methodology/_wiki/_entities/`)

## 已知边界 (v2.1, 留给未来)

- **动态路径反向 import**: L9 regex 不抓变量拼接 (如 `str(_OLD)` 指向旧目录)
- **thin wrapper-to-legacy**: L5b 不检 `def f(*a, **k): from old import g; return g(*a, **k)` 模式
- **registry schema 漂移**: 现 `yaml.safe_load` 无强校验, 未来加 Pydantic
- **pre-commit 易被 --no-verify 绕过**: 项目无 CI 时 lint 仅道德建议. 建议加 GitHub Actions / GitLab CI

## 决策点 (项目接入时给用户选)

1. **死代码处理时机** — ① 立刻删 ② 自动 mv `_legacy/` 等用户复核 ③ 仅报告不动 → 推荐 ②
2. **lint 范围** — ① 全仓 ② 仅 `_code/_pipelines/` (老代码目录跳过) → 推荐 ② + 老目录标 legacy_quarantine
3. **pre-commit 拦截严格度** — ① 全 block ② 仅 L1/L5/L6/L8/L9 block, L4 warn → 推荐 ②
4. **wiki frontmatter 反链** — entity 是否加 `## 🔗 Implementations` 反链 → 推荐加 (核心 entity 先示范)

版本演化 (v1 → v2.1) 见 `changelog.md`。
