> **已退役（2026-09-24）**：CodeBook 不再新建、`deposit` 不再盖章；本文件只用于读懂旧 `_codebook/` 节点。代码结构用 CodeGraph，入口写 `_codemap.md`，理由写决策记录的“涉及代码”。

# CodeBook 节点 schema + deposit_validate 闭集校验契约

> 这一个工件同时是:(1) CodeBook 节点 frontmatter 的 schema,(2) `deposit_validate` 的强制校验清单。
> 二者必须一致(schema 即校验契约)。改一处改两处。对应 sixone-cli-design.md。

## 节点 frontmatter schema

```yaml
---
title: <一句话, 这个系统/模块是什么>          # 必填(AI 写)
user_workflow: <用户视角它怎么被用>            # 必填(AI 写)
owner_refs:                                    # 必填(AI 写), 由 registry/manifest 解析真路径
  - code:<function_id>                         #   → _meta/_registry.yml 的 function id
  - pipeline:<pipeline_id>                      #   → _pipelines/_<id>.yml
  - test:<gate_id>                              #   → _wiki-methodology/_tests/_gates.yml 的 gate id(旧 _tests/_monitor/<id>.py 兼容)
tracked_paths_hint:                            # 必填(AI 写), 该节点描述的源头文件
  - <relative/path.py>
last_verified_hash: <sha256>                   # ⚙️ 只 deposit_validate 写, AI 禁手填
validator_version: <int>                       # ⚙️ 只 deposit_validate 写
---
<正文: 自顶而下分级, 渐进披露, 每节"干嘛 + owner 路径">
```

## deposit_validate 闭集校验(只这 4 条;**明确排除"散文匹配代码"**)

| # | 检查 | 失败 verdict | 失败返回 |
|---|---|---|---|
| a | frontmatter schema 合法(必填字段齐、类型对) | `block` | 缺哪字段 + 标准模板 |
| b | owner_refs 可解析(code→registry / pipeline→manifest / test→gates manifest) | `block` | 哪个 ref 解析不了 |
| c | tracked_paths_hint 每条是相对、不越界、存在的**文件** | `broken` | 哪条路径不合法 |
| d | 正文 markdown 本地链接无断链 | `warn` | 哪个链接断 |

全过 → 计算 `last_verified_hash = sha256(已校验 frontmatter 子集 + 节点正文 + 各 tracked 文件当前工作区内容)`(绑 frontmatter:改 owner_refs/title 同样判 stale),**底层 I/O 注入** frontmatter(不走 Edit 工具,防自触发 PostToolUse),返回 `{verdict: ok, stamped: <hash>}`。
任一失败 → **不盖章 + 剥除手写的 last_verified_hash**,返回 `{verdict, errors:[{check, line, detail}], template}`。

**盖章语义** = "此状态下结构已校验 + 断言",**永不** = "散文内容已对照代码核实"(那是 verify-by-graph 在用时做的)。

## 树协议(单节点 → 多节点怎么长,理念 §1 渐进披露 + TOC-of-TOC)

- **层级 = 目录结构**(不加 parent/children frontmatter —— LLM 维护双向指针必漂):
  `_codebook/<域>.md` 是域根节点;**正文超约一屏** → 裂出 `_codebook/<域>/<子模块>.md`,
  父节点正文留一行链接替代原文。子节点是完整节点,同样走 deposit_validate 盖章。
- **TOC** = `_codebook/_index.md`:纯目录(每节点一行:相对链接 + 一句话),**不带 frontmatter
  不盖章**(导航的导航,低风险)。doctor 双向查它:TOC 指向不存在的节点 → `warn`(死链把 AI
  导进墙);节点存在但 TOC 漏列 → `info`;≥2 节点却没有 _index.md → `info`。
- **单节点项目**:一个 `_codebook/<域>.md` 是合法终态,不强迫长树、不强迫建 TOC。
- **内容边界**(对齐代码检索分工):CodeBook 写**用户可见的系统/模块**(干嘛/怎么用/怎么跑);
  纯结构事实(依赖边/调用图/复杂度)**不落 Markdown**,live query codegraph。

## doctor 派生 trust(不读 frontmatter 的 trust,实时算)
```
for f in tracked_paths_hint:
    if not exists(f):                          -> broken
sha = sha256(正文 + 各 tracked 当前内容)
if sha != last_verified_hash:                  -> stale
if any owner_ref 不可解析:                      -> broken
else:                                          -> fresh
```
