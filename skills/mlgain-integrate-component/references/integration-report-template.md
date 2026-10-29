# 组件集成报告模板（Method Card）

集成完成、Wiring Gate 全绿之后填写，作为 `controlled-comparison.md` 单变量对比的支撑材料。没填完这份表就直接去跑消融，等于跳过了本 skill 存在的意义——没写下来的等于没做过。

```markdown
## 组件集成报告：<组件名>

- **来源**：<论文标题/arXiv链接/官方代码仓库地址>
- **论文声称的作用**：<一句话>

### 宿主 pipeline 来源（见 borrow-existing-pipeline.md；自建则写"自建 + 理由"）
- 包/版本或commit SHA/许可：
- 取用方式：pip install / vendor到 `_vendor/<pkg>/`（改动文件逐条列）：
- swap机制类型与精确位置：<A子类/B构造注入/C registry/D文件名/E配置字段> + <类名.方法名 或 文件:行号>：
- 数据适配器路径 + 三条断言结果（结构/往返/对齐）：
- **Golden run**：B1原装闭环指标=；B2换数据后指标vs平凡基线=；B3过拟合单batch终态loss=；B4a ceiling_gap=MSE_base/MSE_前移=（正确接线应>>1，≈1即泄漏，⚠️不要只跑B4b/B4c就下"无泄漏"结论）；B4b后移R²=vs base R²=（只看单调，不当泄漏判据）；B4c打乱R²=vs平凡基线=；B5反变换量纲=；artifact路径=
- **环境指纹**（两个arm若在不同指纹下测得，比较已不再是单变量，baseline必须重跑而不是复用）：torch/CUDA版本=；框架版本=；repo commit SHA=
- **冒名顶替测试**：通过（与golden run差异<数字>）/ 不通过

### 分类卡（module-taxonomy.md）
A-E五轴取值 + 多标签tag + 血缘（归档进分类体系的载体）：

### 惯例来源（framework-placement-conventions.md）
采纳了哪个框架的哪个插槽契约/默认放置表；哪些地方偏离了惯例及理由：

### 实际读到的接口契约（extract-interface-contract.md）
- 输入输出形状/dtype：
- 归一化假设：
- 序列长度假设：
- 是否需要预训练/warmup：
- 原pipeline插入位置：
- load-bearing超参：

### 理论placement判断（architecture-placement-theory.md）
- 这个模块的核心假设（限制性/偏好性、具体假设了数据的什么结构）：
- 你的数据/任务是否符合这个假设，不符合的地方怎么处理：
- 选择这个插入位置的理论理由：

### 数据/特征合理性（feature-and-data-reasonableness.md）
- 新模块期望的输入分布 vs 你实际喂给它的数据分布：
- 相关特征的理论意义：

### 兼容性检查结论（compatibility-check.md）
- 通用五条：兼容/需要适配层，说明：
- 族专属兼容标记（batch统计依赖/KV-cache/因果mask/改变下游channel数）：
- 构造期assert内容：

### 做了什么适配
跟原始组件代码相比，为了接进你的模型做了哪些改动，逐条列：

### Wiring Gate 结果（integration-sanity-checks.md）
- P0/P1/P2/P10 具体数字：
- 三条断言测试通过状态：
- Identity/no-op退化测试：`allclose`的实际最大误差：
- 输出分布检查：

### 集成方式（function-preserving-socket-protocol.md / residual-gating-safe-integration.md）
- Socket mode：baseline / replace / residual
- 若residual：初始化方案（ReZero零标量 / LayerScale小epsilon / 其他）及理由：
- 解锁后梯度模式是否符合预期：

### 机理诊断记录（mechanistic-diagnosis.md，未达预期时必填）
跑了哪些探针、每个探针的数字（含baseline对照值）、三段式判定、做了什么修复、修复后重测数字：

### 受控比较结果（controlled-comparison.md）
- 声明的科学变量 / nuisance超参（两arm各自重调结果）/ fixed及caveat：
- Baseline多seed方差带：
- 核心指标delta + 输出空间delta + 分类别/分桶指标：
- 采纳门是否通过：
- 误差棒口径：

### 成本 delta
训练时长、推理时延、显存、参数量（质量delta与成本delta并列）：

### 组合关系
与已采纳改动的交互（正则类叠加边际递减；某些平均类方法互斥），是否已单独消融过：

### 结论的 caveat
所有fixed超参、误差棒口径、覆盖了哪些探针、未覆盖什么：

### Attribution
原论文/官方实现链接：
```
