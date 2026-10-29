# 多智能体协作矩阵 — Verifier / Strategist / Sub / Main

> 当前 provider 映射：Strategist 默认使用隔离子智能体 + WebSearch/academic-search；需要 Gemini 跨模型视角时只走 外援审查技能（可选，本包未包含；公开版见 https://github.com/YonganZhang/external-review-skill ） 的 tmux wrapper。

## 4 角色分工（每 round 必备）

### 角色 1：Main（决策整合）
**用谁**：Claude 主会话（你）

**职责**：
- 读用户需求 / 拍板决策
- 启动 / 协调其他 agent
- 沙盒实测代码（不外包给 Sub-agent，因为复杂决策需要主观判断）
- 整合 raw report + 标可信度
- 维护知识库（六合一架构 / explorations INDEX）

**关键纪律**：
- 不诱导 Verifier（不传结论文档）
- 不过度委派（沙盒实测自己跑，结果 own 由你解释）
- 标分级可信度（实测/估计/leaky/猜测）

---

### 角色 2：Sub-agent（数据 + 评测）
**用谁**：Claude subagent（general-purpose 或专用）

**职责**：
- 数据特异性深挖（per-cell EDA、distribution shift、failure modes）
- 评测层诊断（残差白噪、worst samples、SNR）
- per-station 级实测（不需要外部资源的本地分析）
- 互补 Strategist 设计零重叠方向

**触发条件**：
- Round 启动时 + Strategist 同时启动
- 主 Claude 上下文太重需要分担时
- 多并行实测任务（每子 agent 1 个独立任务）

**Prompt 模板**：
```
任务背景: <round_id> 数据特异性深挖 — 互补 <Strategist agent 名>（已并行启动）

已知:
- 项目根: <path>
- 上轮成果: <key findings 列表>
- Strategist 在做: <他们的 5 个方向>

你做（与 Strategist 不重叠）:
方向 1: <数据层>
方向 2: <评测层>
方向 3: <统计诊断>
方向 4: <per-station 实测>
方向 5: <自由发散>

输出:
- 报告写到项目 `_reports/<round>/sub.md`（或当前会话目录；不写系统临时目录）
- 每方向带 python + 数字
- 最后给"配置矩阵"或"failure mode 表"

预算 ≤90 分钟。不要问用户问题，直接做完。
```

---

### 角色 3：Strategist（宏观策略 + 文献）
**用谁**：Gemini CLI（外援审查技能（可选，本包未包含；公开版见 https://github.com/YonganZhang/external-review-skill ））

**职责**：
- 文献综述 / 跨方向梳理
- Kaggle 抄作业 / 现成模型调研
- 宏观策略层（lag set / persistence 边界 / NWP 主导）
- 自由发散

**触发条件**：
- Round 启动时（与 Sub-agent 同时）
- 需要外部知识 / 论文链接

**关键纪律**：
- Gemini 写报告**有"包装"倾向**，把现象包装成机制
- 必须 Verifier 交叉验证机制类断言
- 不让 Gemini 跑 EDA（实测会卡 datetime 对齐）

**Prompt 模板** 同 Sub-agent，注意标"宏观策略层 / 不重叠数据层"。

---

### 角色 4：Verifier（独立验证）
**用谁**：Codex CLI（`codex exec --skip-git-repo-check`）

**职责**：
- **不诱导独立验证**累积 finding
- 实测代码 + 沙盒架构 ablation
- 跨智能体交叉确认（验证 Strategist / Sub 的机制断言）
- 第二意见

**触发条件**：
- 累积 50+ finding 后
- 用户质疑准确性
- 关键决策前（架构切换 / 主 pipeline 改动）
- 论文 reviewer 风险预演

**关键纪律**：
- **不读其他 agent 的结论文档**（防一致性偏差）
- prompt 中"中性陈述，不要被影响"
- 数字可信度 > 机制可信度

详见 [independent-verification.md](independent-verification.md)。

---

## 协作模式（每 round 标准流程）

```
Round N 启动:
├── [并行] Sub-agent  → _reports/N/sub.md (数据/评测层 5 方向)
├── [并行] Strategist → _reports/N/strategist.md  (策略/文献层 5 方向)
└── [串行] Verifier   → _reports/N/verify.md  (独立验证 + 沙盒实测)
            ↓ (Sub + Strategist 完成后)
        Main 整合:
        - 读 3 份 raw report
        - 归档 raw-llm-reports/
        - 整合到 master list / findings / INDEX
        - 标分级可信度
        - 决定 round N+1 方向
```

## 模型设计团队：假设台账与裁决

适用：让分析员、结构/训练专家、检查员、结果分析员为一个模型提出并迭代改动（不限 LLM，可为程序角色）。项目可另有约束（例如"本会话自己做完、不跨窗口派活"），以项目规则为准。

- **台账**：每轮每个提案按 `assets/hypothesis-trace.schema.json` 记一条（假设、理由、所针对的错误类型、预期效应与证伪条件、配置、实验格、结果、裁决、父节点），追加写 JSONL，放项目结果目录。台账是 DAG：新提案指向它基于的旧提案与当前最好结果（吸收自 RD-Agent 的 Trace，见 [上游卡片](upstream/rd-agent.md)）。
- **提案格式**：先分析场景与历史，列不超过 5 个挑战；每个提案按对齐、影响、新颖、可行、风险收益五项打分，写证伪条件。候选只能来自已实现并通过逐格故障检查的选项。
- **裁决分两类**：实现失败（某层体检或逐格检查没过）→ 修好再试；方向失败（各层都过、对称重调后仍无益）→ 写入失败台账，后续同类提案先查台账。两类不混写。
- **反馈边界**：团队只看 select 段数字与诊断，不看评测/测试分数；排序以实际执行结果为准，不以模型自评为准。
- **值不值得**：某个决策交给团队前，先按 [职责与理想决策](agent-value-oracle.md) 算"全选对能涨多少"。

## 实战经验（多站光伏预测项目 R7-R11）

### R7-R10：3 路并行（Codex + Gemini + Sub）
- 4 轮共挖 130+ finding
- Codex R7-R9 quota 限 → 仅 Gemini + Sub
- 仍维持每 round 互补 5+5 方向

### R11：Verifier 介入
- Codex 不诱导验证 8 条核心 → 找出 1 错 5 疑
- 同时 Codex 跑架构 PK → 国网 +0.103
- Sub-agent 跑数据特异性
- Gemini 跑特征/策略
- → 单 round 4 路并行最高效

### 关键 lesson
- **Verifier 必须独立**，不能 fed Claude 结论
- **Sub vs Strategist 互补设计**，零重叠（一个数据层一个策略层）
- **Codex quota 是常态瓶颈**（5:26 AM 重置），需备选 Gemini

## 典型反模式

🔴 **"让 Codex 重新跑一遍 Claude 的发现"** → 已诱导
🔴 **"Sub 和 Strategist 都做 EDA"** → 重叠
🔴 **"Gemini 报告说 +0.05 就当真"** → 没 Verifier 交叉
🔴 **"主 Claude 不跑沙盒，全外包子 agent"** → 决策权下放，结果难解释

## 工具速查

| 工具 | 用途 |
|---|---|
| `Agent` (general-purpose) | Sub-agent 启动 |
| `gemini-ask.sh --prompt-file <file>` | 跨模型 Strategist（Gemini tmux wrapper） |
| `codex exec --skip-git-repo-check "..."` | Verifier / 工程实施 |
| `WebSearch` / `WebFetch` | Strategist 外部知识 |
| 学术检索技能 `share-nature-academic-search`（可选，本包未包含） / WebSearch | 论文数据库与 SOTA |
| Kaggle CLI / Kaggle 网页 | Kaggle 抄作业 |

详见外援审查技能（可选，本包未包含；公开版见 https://github.com/YonganZhang/external-review-skill ）。
