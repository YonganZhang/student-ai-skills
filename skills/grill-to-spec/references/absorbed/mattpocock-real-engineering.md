<!--
来源: mattpocock/skills（MIT, Copyright (c) 2026 Matt Pocock）
文件: skills/engineering/prototype/SKILL.md, tdd/SKILL.md（+ tests.md）
吸收时间: 2026-06-14；2026-10-07 按上游 4588b32 同步 TDD，Debug 与 Architecture 迁出为指针
吸收者: 本技能包维护者
方式: 语义吸收；不机械复制上游文本。
-->

# Real Engineering Checkpoints

## Prototype
触发：状态机、数据流、UI 方向说不清，但直接进主线成本高。
要点：先写问题 | 可丢弃 | 一个运行命令 | 默认不持久化 | 暴露关键状态。
检查：结束时删除原型，或把 verdict 写入 spec / ADR / issue / TOP 真源。

## Debug
完整流程已迁出本技能（本地适配版本包未包含）；需要时读上游 https://github.com/mattpocock/skills 的 `skills/engineering/diagnosing-bugs/`。

## TDD
触发：用户点名 TDD、风险高功能、修 bug 需要锁行为。
要点：公共接口 | 可见行为 | 测试接缝先和用户约定，只在约定的接缝写测试 | 一个测试一片实现（红 → 绿）| 重构放到审查阶段，不在红绿循环里做。
检查：不要水平切片批量写想象测试；不要把测试绑到私有实现或绕过接口查库验证；期望值来自独立来源（已知字面量、手算例子、spec），不要用和实现相同的算法算期望值（同义反复测试永远通过）。

## Architecture
深模块词汇、删除测试、接缝与依赖分类、设计两次：见上游 https://github.com/mattpocock/skills 的 `skills/engineering/codebase-design/`（本地适配版本包未包含）。
检查：架构建议要指向真实摩擦和测试收益，先看最近反复改动的热点；不要为了概念漂亮重构。
