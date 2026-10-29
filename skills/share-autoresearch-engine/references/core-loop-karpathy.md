# Core Loop — Karpathy autoresearch 协议（深度学习通用化版）

## 本机执行边界

本页保留早期协议材料；出现无限循环、破坏性 Git 回退、固定单文件、强制改训练框架等指令时，不在本机执行。实际流程遵循 [ARIS 本地合同](aris/README.md)：复用宿主训练器、有界预算、项目接入检查、独立审查和证据核验。原文示例不授予删除用户工作、终止其他窗口或启动远程资源的权限。

## 来源
基于 [karpathy/autoresearch](https://github.com/karpathy/autoresearch)（2026-03-07，66k+ stars）的核心 loop 机制 — 把"single-GPU nanochat LLM 训练 5min"泛化到**任何深度学习任务**。

## Karpathy 原版要点（直接抄，逐条对齐 README + program.md）

1. **single file 改动**：agent 只编辑 `train.py`（含 GPT model + optimizer Muon+AdamW + training loop）。`prepare.py` 严禁碰（含 evaluate_bpb / dataloader / tokenizer / 常量）
2. **fixed time budget**：每次 train 跑固定 wall-clock 时长（原版 5min，不含 startup/compile）。这让"换架构 / 换 batch / 换 model size"对比公平
3. **single metric**：原版 `val_bpb`（lower=好），vocab-size-independent 跨架构可比
4. **git branch loop**：分支 `autoresearch/<tag>`（如 `mar5`）；每实验 1 commit；改进 → advance branch；没改进 → `git reset --hard HEAD~1` 回退；**rewind 极其谨慎**（原文："very very sparingly, if ever"）
5. **TSV log 5 列 schema**：`commit \t val_bpb \t memory_gb \t status \t description`
   - commit hash 7 字符
   - val_bpb 6 位小数；crash 用 `0.000000`
   - memory_gb = peak_vram_mb / 1024，保留 1 位小数；crash 用 `0.0`
   - status: `keep` / `discard` / `crash`
   - **TSV 不进 git**（leave untracked）
6. **never stop**：循环永远跑，不问"should I continue"；用户可能在睡觉。卡了 → think harder（读论文 / 重读 in-scope 文件 / 组合 near-miss / 试 radical 方向）
7. **timeout 处理**：单实验 ≤ 5min + 几秒 startup；**> 10min（2× budget）→ kill 当 crash + revert**
8. **crash 处理**：grep 输出空 = 跑挂 → `tail -n 50 run.log` 看 stack；
   - 小 bug（typo / 缺 import）→ 修了重跑
   - idea 本身不可行 → 记 `crash` skip，next
9. **simplicity criterion**：等收益简单的赢。具体阈值：
   - +0.001 涨 + 加 20 行 hacky 代码 → discard
   - +0.001 涨 + 删代码 → keep（双赢）
   - ~0 涨 + 大幅简化 → keep（净简化）
10. **VRAM 软约束**：可以增长但不能爆。"some increase OK if val_bpb gain meaningful, but should not blow up dramatically"
11. **first run = baseline**：实验循环第一次必须**裸跑 baseline**（不动 train.py），先有锚点再迭代
12. **redirect 不用 tee**：`uv run train.py > run.log 2>&1`。**不要 tee** — 训练日志会污染 agent context
13. **uv 工程栈**：原版用 `uv` 管 Python + `pyproject.toml`，**禁止加新依赖**（scope creep + 实验不可比）

## 通用化改造（覆盖所有 DL 任务，不只是 LLM）

### 通用脚手架（按本协议落项目）

```
<project>/
├── prepare.py        # 数据 / 评测 / 常量（read-only，agent 不动）
├── train.py          # model + loop（agent 唯一可改）
├── program.md        # agent 指令 + 任务约束
├── results.tsv       # 实验日志
├── pyproject.toml    # 依赖（agent 不加新包）
└── run.log           # 最近一次输出
```

**任何 DL 任务**（vision / NLP / 时序 / RL / multi-modal / 表格回归）都按此结构。变化的只是：
- `prepare.py` 内的数据 / 评测函数
- `train.py` 内的 model / loss
- `program.md` 内的 metric 名 / time budget / "什么不能动"

### 替换 metric 表

| 任务 | 原版 metric | 通用替换 |
|---|---|---|
| LLM | val_bpb (lower) | — |
| 分类 | — | val_acc (higher) / val_loss (lower) |
| 回归 / 时序 | — | val_RMSE / val_MAE / 1-RMSE/Cap (higher) |
| 检测 / 分割 | — | val_mAP / val_IoU |
| RL | — | mean_episode_return |
| 排序 / 推荐 | — | NDCG@k / MAP |

**铁律**：
- metric 必须 vocab-size / batch-size / arch independent（跨架构 fair）
- 只有 1 个 primary metric（多 metric 会让"keep 决策"模糊）
- 评测函数在 `prepare.py`，agent 改不到

### 替换 time budget 表

| 计算量 | 推荐 budget | 每小时 ~实验数 |
|---|---|---|
| Karpathy 原版（H100 LLM）| 5 min | 12 |
| 4090 / 5080 单卡训小模型 | 5-10 min | 6-12 |
| CPU + 表格 LGB（1000 trial）| 1-2 min | 30-60 |
| Multi-GPU 大模型 | 30-60 min | 1-2 |
| 涉及预处理重的 vision | 10-15 min | 4-6 |

**铁律**：budget 一旦定就 freeze；改 budget = 之前所有实验失去可比性。

### 替换"什么不能改"

| 原版限制 | 通用化 |
|---|---|
| 不改 prepare.py | 不改"评测函数 + 数据划分 + 常量"所在文件 |
| 不加新包 | 同 — 加包 = scope creep，每次 keep/discard 不可比 |
| 不改 evaluate_bpb | 不改 evaluation harness — 否则 metric 失效 |

可以加一个：**不改 split / cap / 归一化口径** — 改了就是 leakage

## Loop 标准实施（伪代码，对齐原版 program.md "The experiment loop"）

```python
# Setup（只跑一次）
0. 同人确定 tag（如 'mar5'），git checkout -b autoresearch/<tag>
1. 读 README / prepare.py / train.py
2. 验证数据存在（如 ~/.cache/autoresearch/）
3. results.tsv 写 header: commit\tval_metric\tmemory_gb\tstatus\tdescription
4. **First run = bare baseline**：不改 train.py，跑一次记 baseline

# 然后进 LOOP FOREVER（不询问人，run until 手动 stop）
LOOP FOREVER:
    1. git status：看当前 branch + commit
    2. think 1 个 idea（基于 results.tsv + 论文 + 已 keep 实验）
       — 卡了 → "think harder": 读 in-scope 文件 / 论文 / Kaggle / 组合 near-miss / 试 radical 反向
    3. edit train.py（single file，禁止改 prepare.py / pyproject.toml）
    4. git commit -m "exp: <short description>"
    5. uv run train.py > run.log 2>&1   # 不用 tee！context 污染
       — kill if > 2× budget（10min）→ status=crash, revert
    6. grep "^val_bpb:\|^peak_vram_mb:" run.log
       - 空 → crash → tail -n 50 run.log → 小 bug 修了重跑 / 想法不可行 skip
    7. 写 results.tsv 1 行（commit hash 7chars, metric 6位小数, mem .1f, status, desc）
    8. if metric improved:
           keep（branch 已 advance）
       else if equal-or-worse-but-simpler:
           keep（simplicity 双赢）
       else:
           git reset --hard HEAD~1（回到上一 keep）
    9. NEVER ask "should I continue?" — 持续到人 Ctrl-C
```

## 跟我们 R7-R11 沉淀的整合

Karpathy 的 loop = **执行层**（怎么跑、怎么记、怎么 keep/discard）。
我们 R7-R11 沉淀 = **思考层 / 治理层**（idea 哪来、如何防 leakage、如何 evidence trail、多 agent 如何协作）。

**整合关系**：

```
[思考层 — 我们的 10 条方法论]
   ↓ produces idea
[执行层 — Karpathy loop]
   ↓ produces metric
[治理层 — 我们的 evidence trail + leakage check + 标可信度]
   ↓ produces lesson
回到思考层
```

具体映射：

| 阶段 | Karpathy 原版 | 我们的扩展（高级版用）|
|---|---|---|
| Idea 来源 | "think harder, read papers" | academic-search APIs / Kaggle / Sub-agent / Strategist |
| 改 train.py | single agent self-edit | Main + Verifier 复审（关键改动）|
| Run | uv run train.py | 同 + 沙盒目录隔离（如 `exp_<round>_<topic>/`）|
| Keep/discard | val_bpb 跌 / 涨 | val_metric + sanity check（防 leakage）+ apple-to-apple |
| Log | results.tsv | results.tsv + INDEX.md L3 entry + 标可信度 |
| 卡住 | "think harder" | stuck-protocol 5 步 |

## 何时只用 Karpathy 原版（不用我们扩展）

- **小项目 / 玩具实验**：不值得搞 multi-agent，loop 跑就行
- **5-50 个实验快速 sweep**：不必 evidence trail
- **单一 metric 明确的任务**（如 LLM perplexity）：不必标可信度
- **第一周冲分阶段**：先 baseline 跑通，多智能体协作后期再上

## 何时用我们扩展（高级版）

- **冲榜 / 投稿**：需要 evidence trail 写论文 method
- **多 cell / 多任务**（如多站光伏预测项目 9 cells）：需要 per-cell 思维
- **跨 horizon / 跨数据集**：需要 apple-to-apple 防混比
- **怀疑当前架构 / 假设**：需要 4-way ablation + 独立验证
- **机制类断言**：需要 verifier 防包装

## program.md 模板（任意 DL 任务通用）

```markdown
# autoresearch — <project name>

## Setup
1. Confirm tag: <tag>
2. git checkout -b autoresearch/<tag>
3. Read: prepare.py, train.py, README
4. Verify data exists at <path>
5. Init results.tsv with header
6. Confirm and go.

## Primary metric
<val_RMSE / val_acc / val_bpb / ...> — <lower / higher> is better.

## Time budget
<X> minutes wall-clock. Kill if > 2X.

## What you CAN edit
- train.py only.

## What you CANNOT
- prepare.py / evaluate_*.py / split files
- Add new dependencies
- Change cap / normalization / metric

## Simplicity criterion
Same metric + simpler code = keep.

## Loop
[抄上面的 LOOP FOREVER]

## Stop conditions
- 人 Ctrl-C
- 连续 30 次 discard 无 keep（陷入局部）
- crash 率 > 50%
```

## 反模式（Karpathy 原版 + 我们补充）

🔴 改 prepare.py / 评测函数 → metric 失效
🔴 改 budget → 之前实验失可比性
🔴 加新包 → scope creep
🔴 多文件改动 → diff 不可 review
🔴 跑超 2× budget 不 kill → 队列堵死
🔴 metric 涨了不 sanity check → leakage 没发现（我们补的）
🔴 keep 不 evidence trail → 论文 method 章节没料（我们补的）
🔴 ask "should I continue" → 违反 NEVER STOP

## 推荐 fork / 衍生

- `miolini/autoresearch-macos` — Mac 移植
- `trevin-creator/autoresearch-mlx` — MLX (Apple Silicon)
- `jsegov/autoresearch-win-rtx` — Windows RTX
- `andyluo7/autoresearch` — AMD
- `uditgoenka/autoresearch` — Claude Skill 化
- `leo-lilinxiao/codex-autoresearch` — Codex 版

我们的 share-autoresearch-engine = Karpathy loop + R7-R11 治理层 + 多智能体 + DL 通用化。
