# AI 检查点：让另一个模型在错误变贵之前提出反例

AI 检查的价值不是“多一个模型说好”，而是**换一个没有沉没成本的上下文，拿原始证据找反例**。检查点要有触发、输入、输出和关闭条件；否则就是随机聊天。

## 1. 角色，不是代理数量

| 角色 | 任务 | 边界 |
|---|---|---|
| **Scout** | 找论文/比赛方案/失败切片/候选 trick | 不宣布“一定有用” |
| **Builder** | 实现、训练、接线、跑实验 | 不批准自己的结论 |
| **Reviewer** | 审计数据/指标/曲线，或做红队/统计 | 只读，不改业务文件 |
| **Owner** | 决定继续/关闭 finding/承担结果 | 不用“AI 通过”代替证据 |

小任务可以一人多角，但**提出问题和批准关闭不能是同一个上下文**。换模型不是必须；换上下文、给原始证据、要求可复现反例才是。

## 2. 七个检查点

按风险选，不必全跑。每个检查点只回答少量问题；输出必须能落到文件/命令/数字。

| 检查点 | 触发 | 只问 | 输出 | 不通过时 |
|---|---|---|---|---|
| **C0 问题定义** | 新任务/新指标/换部署单元 | 任务和评价器一致吗？数据单位是什么？baseline 是谁？最可能死在哪层？ | problem frame + 3 个水下假设 | 不开始长训练 |
| **C1 数据/指标** | 改数据、split、标签、评价器、预处理 | 空真值/空预测/ignore/阈值边界按适配器定义是什么？同病人/视频/位置跨 split 吗？统计量只来自 fit 吗？ | 检查命令 + 证据路径 | 不做正式比较 |
| **C2 基线/稳定性** | 第一次长训练、换栈、改 loss/优化器 | train-eval/val 曲线可比吗？记忆探针/学习信号如何？优化器成员、AMP、梯度、主预算轴对吗？ | baseline 曲线 + 稳定性结论 | 不用不稳定训练比较结构 |
| **C3 模块/idea** | 加模块、换结构、改 loss 融合、移植论文 | 机制/原生位置是什么？三种比较怎么分？通道/尺度/语义/初始化对齐吗？只改了一个科学变量吗？ | 内联结构判断 + 接线证据 + 对照计划 | 不直接全量训练 |
| **C4 第一次信号** | 首个可解释验证窗口、预算节点、异常曲线 | 曲线支持哪种解释？效应 vs 优化噪声/抽样误差？只在一个 split/seed 有效吗？成本可接受吗？ | 继续/扩大/停止/限界记录 | 不扩大预算、不写最终结论 |
| **C5 冻结/test** | checkpoint/阈值/融合/评价器冻结后，跑最终 test 前 | 选择是否只来自 select？manifest/hash/seed/预算全吗？相关 P0/P1 关了吗？评价器与 baseline 同版本吗？ | release/hold + 缺项 + 精确 test 命令 | 不跑 test、不写最终结果 |
| **C6 负结果/事故** | 负结果、复现失败、事故、trick 拟入默认流程 | 实现失败/方向失败/不可判？同类事故能变回归吗？影响哪些历史结论？ | issue + 边界 + 回归（仅 bug） | 不关闭方向、不采纳 trick |

### 关键边界

- **C1 的“空预测/微扰”不是通用不变量**：Dice/F1 对空真值可定义为 1、忽略或未定义；回归空输出不能记零；阈值附近微扰本来就会改变离散匹配。按指标适配器写期望值或合法状态。
- **C2 不做“1 batch 必须过拟合”的绝对判断**：强增强、软标签、冻结大部分参数、随机任务不保证 loss 接近零。分记忆探针（固定样本/增强/可达标签）和学习信号探针（真实增强下相对初始下降）。
- **C3 的三种比较分开**：step 0 同权重/buffers/eval/RNG 等价（仅函数保持接口）；训练后同 checkpoint on/off（贡献，不是父模型）；独立训练 baseline（净增益）。
- **C5 只阻塞相关动作**：finding 不相关就不 hold；统计不显著可以报“无差异”，不能因此伪造通过。test 放行后可以也应该跑，跑完不得回头改模型再报同一 test。
- **C6 普通负结果不是软件 bug**：只有已证实缺陷才要求“旧反例失败/新例通过”的回归；方向性负结果写边界和重开条件即可。

## 3. 触发矩阵

| 事件 | 检查 |
|---|---|
| 改数据/split/标签/评价器 | C1，必要时 C0 |
| 改 loss/优化器/AMP/归一化 | C2；指标口径变了再加 C1 |
| 改 backbone/neck/head/融合/模块 | C3 |
| 第一次长训练/换栈 | C2 |
| 首个可解释验证窗口/预算节点 | C4，无论涨没涨 |
| 冻结、跑 test、对外提交 | C5 |
| 负结果/事故/复现失败 | C6 |
| trick 拟进默认流程 | C6 + 回归/触发检查 |
| 只改日志/文档 | 无 |

高风险动作（test、数据边界、对外提交、删数据）加 `--gate` 级审查；普通实现审查用 fast 档。不要把所有事升级成重审。

## 4. 监督闭环

```text
Builder 写 proposal / 实验记录
        ↓
Reviewer 只读：原始证据 + 反例
        ↓
findings：P0/P1/P2 + blocks_action + 关闭证据
        ↓
Builder 逐条响应：接受/反驳/补实验
        ↓
定向复审：只查上轮相关 P0/P1 是否关闭
        ↓
关闭 → 才允许对应动作（扩大预算/冻结/test/写结论）
```

finding 最小字段：

```yaml
id: R-001
severity: P0 | P1 | P2
claim: ""
evidence:
  - path: ""
    line: ""
    fact: ""
counterexample: ""
blocks_action: "scale | freeze | test | claim | none"
close_evidence: ""
owner: ""
```

- **P0**：结论不可用/数据或 test 边界被破坏 → 停相关动作。
- **P1**：结论需限定/关键证据缺失 → 修完再继续相关动作。
- **P2**：改进项/文档/未来工作 → 记录，不阻塞。
- `blocks_action` 不相关就不 hold；Reviewer 不能用一个 P1 卡住整个项目。
- 复审只回答“上轮相关项是否关闭”，不重新发散；新问题另开一轮。
- 审查预算最多一次初审 + 一次定向复核；超出只因新证据。

## 5. 用 Codex 做独立审查

Codex 适合代码/实验审查，不适合替你决定科学方向。给它：

- 用户请求、本轮目标、基线/已有证据；
- 改动范围（文件/commit）、已跑测试；
- 3–5 个具体问题；
- 明确不查什么；
- 输出格式：P0/P1/P2 + 文件/行 + 反例 + 最小修复。

### 最小命令

```bash
# 1) 生成只读审查包（不调用模型）
#    用外援审查技能（可选，本包未包含；公开版见 https://github.com/YonganZhang/external-review-skill ）的打包脚本，
#    或手工整理：审查请求（只找 P0/P1/P2，给文件/行证据）+ 本轮目标和已验证结果 + 相关文件 → /tmp/review-context.md

# 2) 点名 Codex 才调用；按风险选审查深度
codex exec --skip-git-repo-check "$(cat /tmp/review-context.md)"   # 或外援技能的 wrapper；未安装外部模型时用独立上下文的子智能体
```

审查包只放相关文件；命令和结果写进 `findings.md`/`verdict.md`。Codex 说“通过”只是审查完成，不是科学结论。

## 6. 落盘位置

一次检查一个目录：

```text
_reports/ai-checks/<YYYYMMDD-HHMM>__<scope>/
  request.md       # 任务与范围
  scope.txt        # 文件/commit/配置
  findings.md      # P0/P1/P2 + 证据
  response.md      # Builder 逐条响应
  verdict.md       # pass/conditional/fail + 未覆盖项
```

项目已有 `_reports/_foreign_aid/` 时保留 wrapper 原始报告，另在 `ai-checks` 放汇总；没有 `_reports` 的用 `runs/reviews/`。issue 关闭前跑 `python scripts/issue_ledger_check.py <ledger.yml> --strict`；示例见 [issue-ledger.example.yml](../assets/issue-ledger.example.yml)。

## 7. 防止“AI 检查”变成表演

- 不要问“你觉得怎么样”；问“这三个假设哪个最可能错，反例是什么”。
- 不要只给摘要；给文件/行/配置/数字。
- 不要让 Reviewer 给一堆泛泛建议；要求按 P0/P1/P2 和最小修复排序。
- 不要用“Codex 说没问题”代替测试；测试和证据才是判据。
- 不要无限复审；相关 P0/P1 关闭即结束，新想法进 backlog。
- 检查本身要有已知反例、通过样例、误报记录、执行成本和维护者；没有反例的检查可能只是另一种“看起来安全”。

## 8. 提示词模板

- [Scout：找 idea / 找水下问题](../assets/check-prompts/scout.md)
- [Red Team：结果与实验反例](../assets/check-prompts/red-team.md)
- [Training review：loss/曲线/梯度/接线](../assets/check-prompts/training-review.md)
- [Pre-freeze：冻结/test 前检查](../assets/check-prompts/pre-freeze.md)
- [Postmortem：负结果复盘](../assets/check-prompts/postmortem.md)

## 相关

- 问题固化：[incident-to-pipeline.md](incident-to-pipeline.md)
- 训练判断：[training-core.md](training-core.md)
- 论文/比赛 idea：[idea-sourcing.md](idea-sourcing.md)
- 选择卫生：[selection-hygiene.md](selection-hygiene.md)
