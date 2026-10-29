# 软件项目架构文档 · 怎么写指南

> **三个受众三种图**(任何 software 开发项目都该有这份):
> - 老板看 → L1 能力图(mindmap)
> - 测试看 → L2 用户旅程(journey)
> - 开发看 → L3 接口架构(flowchart)
>
> 全在一份文件里 · 单一真源防漂移(篇幅以一次能读完为界,细节链接出去)
>
> **触发词(大白话)**:**项目架构图 / 软件架构 / 给老板看的图 / 给开发看的图 / 主干分支枝叶 / 项目骨架 / 业务流程图 / 模块图 / 接口图 / 系统蓝图 / 整体架构 / 架构梳理 / 模块关系 / 服务关系 / 数据流 / 调用链 / 系统设计 / 怎么画架构图**
> **同义(术语派)**:system arch / SYSTEM-ARCH / arc42 / C4 / L1 L2 L3 / 能力图 / 用户旅程 / 设计文档
>
> **直接 cp 用** → [`arch-doc-template.md`](arch-doc-template.md)(骨架 · 改 `<占位>` 即可)

## 0. 三条哲学(违反 = 删 · 砍冗余符合 AI 直觉)

1. **一劳永逸**:加东西前问"3 个月后还有用吗?"· 否 = 不加
2. **直击根源**:症状修补 = 反模式 · 解到根因才停手
3. **AI 直觉 / 砍冗余**:同一信息 ≥ 2 次 = 砍 · 三宗罪 = 冗余 / 混淆 / 漂移

## 1. 推荐组合(为什么这套)

| 部件 | 推荐 | 不推荐 · 理由 |
|---|---|---|
| 骨架 | arc42 单文件 6 节 | 完整 12 章 / Backstage 平台:小团队过重 |
| 分层 | C4 思路 L1/L2 | 4+1 View / Wardley:C4 官方"多数团队不需 4 层" |
| L1 | Mermaid `mindmap` | PlantUML / Visio:外部依赖 |
| L2 | Mermaid `journey` | User Story Map 工具:平台依赖 |
| L3 | Mermaid `flowchart TB + subgraph` | Mermaid C4 beta(兼容差)/ Structurizr(过重) |
| 隔离 | 逻辑隔离(文档分域 · 代码不强拆) | 目录/微服务隔离:小团队改造成本高,逻辑隔离已能拿到主要收益 |

## 2. 6 节骨架

→ **真源 = [`arch-doc-template.md`](arch-doc-template.md)**(cp 即用 · 不在本文重复)

## 3. 单一真源(防漂移核心)

| 内容 | 真源 | 本文档处理 |
|---|---|---|
| 系统状态 / 当前进展 | `_wiki-methodology/_top/_task_plan.md` | 不提 |
| ADR | `_wiki-methodology/_top/_decisions/` | §5 一行链接 |
| 风险 / 路线 | `_wiki-methodology/_top/` 下的路线文档 | §6 一行链接 |
| 技术细节 | `_wiki-methodology/_wiki/` | 一行链接 |
| 用户旅程清单 | `{项目根}/_wiki-methodology/_tests/trunk-recording/` | 一行链接 |
| 维护铁律 | 本文 §5 | skeleton 一行链接(不重复) |

**核心承诺**:改一处只在一处改 · 重复 = 漂移 = 砍。

## 4. 图节点限(启发式 · 非硬规则)

灵感 Miller 1956 短期记忆 chunk 限 · **业界图论实践常用 5-9**:
- L1 mindmap:每根 5-9 节点 · 超 11 拆 root
- L2 journey:section ≤ 5 · 每 section 步 ≤ 5
- L3 flowchart:每 subgraph 节点 ≤ 5 · 跨图引用标 [详 §X]

## 5. 维护铁律(违反 = 退回 · skeleton 末尾只链接 · 不重复)

1. 每图 ≤ 启发式 5-9 节点 · 超 11 拆子图
2. 每箭头指代码 / API endpoint / 表名(没指 = 删)
3. PR 改接口/表/流程 → 同步 L2/L3 图
4. ADR / 风险 / 系统状态 永远不在 SYSTEM-ARCH 重复(只链接)
5. 用户旅程不占位(等真做再画)
6. 总文档保持一次能读完;写不下说明在抄真源,改成链接 · 反模式(下方反例之一)= 退回

**反例**:
- 🔴 把 ADR/风险/技术细节抄进 SYSTEM-ARCH(违反铁律 4)
- 🔴 placeholder 占位(违反铁律 5)
- 🔴 mindmap 单根 >11 节点(违反铁律 1)
- 🔴 Mermaid C4 beta(退 flowchart)
- 🔴 同件事 5 文件改(漂移)
- 🔴 小团队上 Backstage / Structurizr(违反推荐组合)

## 6. 链接

- arc42:https://github.com/NetworkedAssets/arc42-in-markdown-template
- C4 Model:https://c4model.com
- 配套测试三层:`test-trunk-branch-leaves.md`(测试分层 ⟂ 系统分层 · 正交)
