# 知识树（可选派生导航）

知识树把项目里分散在各列的文档（知识、决策、发现、规格、测试）按主题串成一棵树，生成可以从上往下点的导航页。它是**可选的派生导航**，不是第七列：文档不搬、不改，节点和逐份文档的登记各在一个中心文件里，导航页全部由 `doctree` 生成。项目没有 `_meta/_doc_tree.yml` 时，所有工具当它不存在，行为与以前完全一样。

〔试点示例〕是首个试点项目的具体情况，只作参照，不是别的项目的门槛。

## 什么时候启用

- **条件**：文档多到平铺索引加 `rg` 已经不好找（〔试点示例〕扫描范围约 600 份），而且同一主题的资料散在多列里。
- **做法**：维护者在项目根建 `_meta/_doc_tree.yml`，先写十来个按主题分的节点，再逐步给文档写登记。
- **为什么**：小项目的手写索引加 `rg` 够用，多一层导航只是多一份维护。
- **边界**：不自动启用、不批量建树；推广到别的项目前，先用同语料、同摘要做一次独立导航对照（见文末）。

## 文件与主人：一个字段一个主人

| 文件 | 只管什么 | 谁写 |
|---|---|---|
| `_meta/_doc_tree.yml` | 节点（id、父节点、标题、一句话、别名）、扫描范围、`coverage`、整组挂载、列的显示名、输出路径、`place` 判定线 | 维护者；新节点经维护者审核 |
| `_meta/_doc_summaries.yml` | 逐份文档的 `topics`（第一个为主归属）、`summary`、`source`、`reviewed_sha` | 写或改文档的人 / AI |
| 文档本身 | 正文；自己头部的 `status:`、`superseded_by:` 在导航页上原样引用 | 作者 |
| `TREE.md`、`_tree/<节点>.md`、`CATALOG.md` | 派生页，首行带 `<!-- doctree:generated` 标记 | 只由 `doctree build` 生成 |

- 文档头部的 `topics:` / `summary:` **不读也不写**：同一个字段不在两处维护，也就不存在"头部和中心表谁优先"。
- 整组挂载（`mounts`）给同质目录一次挂到一个节点（〔试点示例〕60 份上游衔接点登记）。某份需要跨主题时，在中心表里给它写完整的 `topics`（包含挂载节点），中心表的条目优先于挂载规则。

```yaml
# _meta/_doc_tree.yml（version 1；未知键报 CONFIG_UNKNOWN_KEY，项目扩展用 x- 开头的键）
version: 1
root: proj
summaries: _meta/_doc_summaries.yml            # 默认值
output: {tree: _wiki-methodology/TREE.md, node_dir: _wiki-methodology/_tree, catalog: _wiki-methodology/CATALOG.md}
scan: {include: ["_wiki-methodology/**/*.md", "docs/**/*.md"], exclude: ["_wiki-methodology/_wiki/_sources/**"]}
coverage: ["_wiki-methodology/_top/_decisions/*.md"]  # 这里的文档必须挂上树，否则 ORPHAN
mounts: [{glob: "_wiki-methodology/_top/_decisions/adr-*.md", topics: [decisions]}]
columns: [{label: 决策, glob: ["_wiki-methodology/_top/_decisions/**"]}]
place: {variant: knn, min_score: 0.05, min_margin: 0.25}   # 校准并冻结后才写
nodes:
  - {id: proj, title: 项目}
  - {id: auth, parent: proj, title: 账号与登录, one_line: 登录页、口令、角色权限, aliases: [登录, 口令]}
  - {id: ui, parent: proj, title: 界面与主题, one_line: 页面、设计 token、明暗主题, aliases: [界面, 主题]}
  - {id: decisions, parent: proj, title: 决策, one_line: 可复用的架构决策与理由, place: rule-only}
```

```yaml
# _meta/_doc_summaries.yml
version: 1
docs:
  _wiki-methodology/_wiki/_entities/login.md:
    topics: [auth, ui]
    summary: 登录页阴影改用设计 token，明暗两套主题下不再发灰；口令提交方式不变。
    source: reviewed
    reviewed_sha: 0123456789ab
```

两段示例可以照抄运行（有测试抽出来实跑）。节点 id 只能是简单名字（字母、数字、`_ . -`），它就是节点页的文件名；输出路径必须在项目内、互不重名，也不能放进 `node_dir`，否则是配置错误（退出 2）。配置里的路径相对项目根；生成物和计划结构区（`_task_plan*`、`_plan_details.md`、`_questions/`、`_logs/`，旧布局的 `top/task_plan.md`）自动排除，不用写进 `exclude`。`output.catalog: false` 可以不生成平铺目录。

## 摘要：写法、来源与过期

**写法**（导航全靠它，也是成本大头）：
- 一到两句，结论在前，写清对象和用途，能和同一节点下的邻居区分开。
- 写**用户会怎么描述这个问题**的症状词：界面名、看到的现象、报错的说法，不只写内部术语。〔试点示例〕"回答里的图片为什么显示不出来"走到了正确节点，但那篇契约决策的摘要里没有"图片""裂图"，机械走法就错过了。
- 症状词必须是原文支持的；不为了好搜写原文没有的结论。
- 不写会变的东西：状态、计数、日期、提交号、"本批从…继续"。状态由导航页从文档的 `status:` 单独引用。

**来源**：`source: reviewed` 表示人或 AI 读过原文后写下或确认；`auto` 是没审过的草稿（比如 LLM 批量起草），不写 `source` 也按 `auto` 算。没有条目的文档，导航页取机械摘录（"一句话"类小节，否则第一段）。草稿和机械摘录在页面上都标 `〔自动摘录，未审〕`。〔试点示例〕抽样 15 份文档的首段，只有约 6 份看得出主题。

**过期**：
- **谁改了文档，谁在同一次提交里更新它的条目**：结论变了就改 `summary`；确认摘要仍然成立后盖章 `doctree summaries stamp <文档> --write`，写入当前正文的 `reviewed_sha` 并置 `source: reviewed`。
- 哈希只是"该复核了"的信号，不判断语义；复核后摘要可以不改。
- 改名或删除文档，同一次提交里改键名或删条目，否则 `ENTRY_DEAD`。
- `stamp` 默认只预览。写入时只改目标条目的 `source` 和 `reviewed_sha` 两个值，其他条目（包括写坏的）、注释、引号和顺序原样保留；流式写法（`{…}`）或写坏的目标条目拒绝盖章（退出 1），请手改。
- 写摘要表的工具（目前只有 `summaries stamp`）共用一把锁，锁按摘要表的路径区分；`build` 只写生成页，不加这把锁。锁内重读再改，改完重新解析一遍确认只动了目标条目，写之前发现表被别处改过就整次放弃、退出 3。编辑器直接改文件不受这把锁保护，重读检查能挡住大部分但不是全部。
- **摘要表的写法**：它是工具管理的文件，值只用普通标量或带引号的标量（`summary: 一句话`、`summary: "带: 冒号"`），列表用 `[a, b]` 或 `- a`。不用块标量（`|`、`>`）、锚点（`&`）和别名（`*`）：读到就是配置错误（退出 2），`stamp` 也拒绝、不写盘。

## 生成物清单与清理

- `build` 和 `check` 用同一份清单：`TREE.md`、从根可达的每个节点一页、`CATALOG.md`（配置了才有）。`check` 把每个文件和一次重新渲染逐字节比较，不一致就 `STALE`。
- 输出确定：排序固定、无时间戳、相对链接；同样的输入、同样的相对布局（输出文件之间、输出与文档之间的相对位置）在不同 `PYTHONHASHSEED` 下逐字节一致。输出目录换了深度，相对链接随之变化，可用 `check --out <目录>` 确认链接都可达。
- `build` 只写内容有变化的文件；只删除 `node_dir` 里带标记、但已不在清单里的页面。没有标记的文件不覆盖、不删除：目标路径上是手写文件时整次拒绝（`OUTPUT_UNMANAGED`，什么也不写），`node_dir` 里混入的手写文件保留并提醒。
- 写入前先做结构校验，结构错误时拒绝生成。

## 命令

入口：`python3 <share-top>/scripts/doctree.py [--project 路径] [--tree 文件] [--summaries 文件] <命令>`（`<share-top>` 是本技能目录；不安装短命令）。命令行上的路径相对当前目录；项目根按 topic-brief 的规则从 `--project`（默认当前目录）向上找。

| 命令 | 作用 | 写盘 |
|---|---|---|
| `build [--out DIR]` | 按清单生成导航页；`--out` 写到验证目录 | 是 |
| `check [--format text\|tsv\|json] [-v] [--out DIR]` | 体检，见下表 | 否 |
| `place 文件 \| --title T [--summary S]` | 给前三个候选节点、得分、依据词 | 否 |
| `show [节点] [--doc 文档]` | 大纲、单个节点，或一份文档的归属和每个字段的来源、复核状态 | 否 |
| `summaries stamp 文档… [--write]` | 复核后盖章；默认只预览 | 加 `--write` 才写中心表 |

- **机器输出**：各命令 `--format json`（或 `--json`）；结果对象带 `schema_version`（`doctree-check/v1`、`doctree-build/v1`、`doctree-place/v1`、`doctree-show/v1`、`doctree-summaries/v1`）和 `enabled`。出错时 stdout 是 `doctree-error/v1`（`error.kind` 为 usage / config / not-enabled / runtime / conflict，`error.exit` 为退出码；配置读不出、类型不对、不是 UTF-8 都是 config），诊断文字一律写 stderr。
- **未启用**：`check` / `show` 退出 0，JSON 为 `{"enabled": false, "verdict": "ok", "issues": []}`；`build` / `place` / `stamp` 退出 2，`error.kind=not-enabled`。
- **退出码**：

| 码 | 含义 |
|---|---|
| 0 | 成功，可以有提醒 |
| 1 | 被项目状态挡住：`check` 有阻断项；`build` 遇到结构错误或手写文件拒绝写；`stamp` 有输入不能盖章（整批不写） |
| 2 | 用法或配置错误：参数不对、配置读不了或不合法、`--tree` 指定的文件不存在、未启用时调用写命令 |
| 3 | 运行环境出错或写入冲突：读写失败、缺 PyYAML、`stamp` 等锁超时或发现表被别处改过（什么也不写）。`build` 可能已写了一部分，JSON 的 `written` / `failed` 列出明细 |

1 和 sixone `doctor` 的"阻断退出 1"一致，所以运行环境错误单独用 3，脚本可以分清"文档有问题"和"工具没跑成"。

## check 码

| 码 | `doctree check` | topic-doctor | 处理 |
|---|---|---|---|
| `DUP_ID`、`ROOT_MISSING`、`PARENT_MISSING`、`PARENT_CYCLE`、`EXTRA_ROOT`、`TOPIC_INVALID` | 阻断 | 阻断 | 修节点或登记 |
| `STALE`、`DEAD_LINK`、`OUTPUT_UNMANAGED`、`ENTRY_DEAD`、`ENTRY_INVALID` | 阻断 | 提醒 | `build`；修链接、条目或输出路径 |
| `SUMMARY_STALE` | 提醒 | 提醒 | 复核摘要后 `stamp` |
| `ORPHAN`、`ENTRY_OUT_OF_SCOPE`、`MOUNT_EMPTY`、`NODE_EMPTY`、`UNMANAGED_IN_OUTPUT`、`CONFIG_UNKNOWN_KEY` | 提醒 | 提醒 | 按提示补登记或改配置 |
| `SUMMARY_MISSING`、`SUMMARY_AUTO` | 提醒 | 信息（按码合并计数） | 渐进补齐，不拦无关提交 |
| `COVERAGE`、`SUMMARY_SOURCES` | 信息 | 信息 | 计数 |

`doctree check` 适合当合并关卡；通用的 topic-doctor 只在项目启用后才多出 `TREE_*` 码，同码多条合并成一行。

## 写新文档：用 place 给候选，归属由写文档的人定

1. 写好草稿后 `doctree place 草稿.md`：路径命中整组挂载规则时直接报告；否则按节点描述和已挂文档打分（中文双字切分与英文词分开处理、TF-IDF），给前三个候选和依据词。
2. 读一遍 `TREE.md` 的大纲（十几行），从候选里挑；`place` 不写盘。
3. 最高分低于判定线时答"不确定，可能需要新节点"并建议父节点；新节点由维护者审核后写进 `_doc_tree.yml`。没有校准过判定线时一律答"不确定"。
4. 在中心表加条目（`topics` + `summary`），`build` 后 `check`。

**判定线**：先在校准集上按事先写好的规则选定并冻结，再到留出集上只评一次；冻结记录要绑定评分代码、文档正文、摘要和配置的哈希，换了任何一项就重新冻结。留一法评估时，被评文档要同时从节点画像和文档频率里拿掉。〔试点示例〕留出 52 份：主归属 top-1 34/52、top-3 45/52；严格判定线下 22/52 答"不确定"，给出建议的 30 份里主归属对 24 份（算上备选归属 26 份）；5 份真实新主题都标了"可能需要新节点"，样本小。

## 与原有索引的关系

- **手写 `INDEX.md` 原样保留**，`TREE.md` 只是新增入口。手写索引还管着树不扫描的东西：代码入口、规则、上游镜像、URL，以及按关键词找路径的触发词。
- 要用生成版替换手写索引，是另一项决定：先有对比工具证明"有效的旧入口（路径、关键词、外部入口）减去明确批准退役的部分"全都在新入口里，替换前的手写版移进 `_legacy/`。
- Wiki 列的 `_index.md` 怎么处理，见 [wiki-writing-method.md](wiki-writing-method.md)「启用知识树时」。

## 接入 brief 与 doctor

- topic-brief：只在启用时多打印 `tree: on nodes=N entry=<output.tree> built=yes|no` 和一行 `docs -> <output.tree>`，路径取自配置；JSON 只在启用时多一个 `tree` 字段。只读配置文件，不扫描文档。
- topic-doctor（含 `sixone-cli.py doctor`）：只在启用时运行 `doctree` 的规则，按上表定级。

## 推广前的独立导航对照

〔试点示例〕试点的找资料测试（10 题）：机械走法 5/10 在 3 跳内到证据；平铺目录按关键词排序 5/10 进前 3、8/10 进前 6；"人工走法 9/10"是熟悉这批文档的设计者自己走的，偏乐观，只有文字路径记录；手写 INDEX 0/10 只测了关键词行里是否直接出现证据路径，没有沿内链继续走。这些只说明值得继续试，不证明树优于同等摘要质量的平铺目录。

推广到别的项目前：问题在选材之前写好；同一语料、同一批摘要，比较"树"和"平铺目录"两条路线；由不熟悉文档的执行者只沿链接打开文件，逐跳记录打开的文件和字节数；区分决策 / 测试证据和一般介绍文档；同时记录写摘要花的时间。
