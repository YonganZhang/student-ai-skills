# 多轮深挖框架 — Round-Based Exploration

## 核心理念
**单 round 挖不透**。多 round 累积是必然，每 round 设计互补方向。

## Round 设计原则

### 1. 互补不重叠
每 round 3 路 agent 跑互补方向（数据层 vs 策略层 vs 验证层），零重叠。

### 2. 渐进深化
- R1-R3：通用 bug 扫面（EDA / 数据完整性 / 时间对齐）
- R4-R7：方向性深挖（特定数据集 / 特征 / horizon）
- R8-R10：跨向交叉（spatial / 仪器 / 物理特征）
- R11+：转向（"通用"→"per-cell"，"机制"→"实测验证"）

### 3. 每 round 必出物
- 5+5+? 个方向各带 python + 数字
- raw report 归档到 `raw-llm-reports/<date>-<agent>-round<N>.md`
- master list / explorations INDEX 加新 finding 行
- 至少 1 个"红色发现"或新 evidence 不然这轮等于浪费

## Round 触发器

| 触发 | 启动 round? |
|---|---|
| 累积 ≥ 30 finding 但还没"震撼发现" | ✅ |
| 用户问 "查的够不够" | ✅ |
| baseline > 1 周不动 | ✅ |
| 实验失败 ≥ 3 次同类 | ✅ |
| 用户提出新角度（"试试 X？"）| ✅ |
| 单纯想刷 finding 数 | 🔴 不要 |

## 标准 Round 模板

```
Round N 主题: <一句话>

启动条件: <为什么这轮要启动>
互补设计:
- Sub-agent 5 方向: <数据/评测层>
- Strategist 5 方向: <策略/特征层>
- Verifier 任务: <独立验证 / 沙盒实测>

预期产出:
- N 条新 finding
- M 个"红色发现"
- K 个 explorations INDEX 升级

成功标准:
- ≥ 1 个 +0.005 实测涨幅 OR
- ≥ 1 个红色发现暴露之前盲点 OR
- ≥ 1 个机制断言被 falsify
```

## 实战例：多站光伏预测项目 R7-R11

| Round | 主题 | 关键发现 |
|---|---|---|
| R7 | 国网 8 站数据到位（Nature paper）| 容量分布 50/130/30/130/110/35/30/30 MW |
| R8 | 8 站 EDA + 风电场 | TSI > GHI / k 值漂移 / 仪器换型 |
| R9 | Site 8 对齐 + GHI 欠刻度 | site 4/6/8 GHI underscale / GFS lead-aware +0.56 |
| R10 | Folsom + 夜间负值 + 蒙特卡洛 | site 2 phantom / Site 3 缺数据（后被验证为错）/ +4 pt 估计 |
| R11 | 数据特异性 + 架构 PK + 图像 | 4 架构 PK +0.103 / SKIPPD 图像 +0.011 / Codex 验证 1 错 5 疑 |

**R11 收获最大**，因为：
- 首次启用 Verifier 独立验证
- 首次跑沙盒架构 PK
- 首次验证图像通用 backbone

## 反模式

🔴 **每 round 都查 EDA**：第 3 round 后 EDA 已无新东西
🔴 **3 agent 跑同类任务**：浪费，必须互补
🔴 **不归档 raw report**：下次会话接手时材料丢了
🔴 **机制断言不验证**：埋雷，论文 reviewer 会击垮
🔴 **finding 不入 master list**：发现 → 落盘 → 升级 是闭环

## 何时停止 round 模式

- 连续 2 round 无红色发现 → 切实施模式
- baseline 已迭代到物理上限 ±0.005 → 切论文写作
- 用户明确说 "够了" → 切实施模式
