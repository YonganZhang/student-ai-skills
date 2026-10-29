# LLM 14环节项目状态表

复制到项目作为该轮操作检查表；项目Plan仍维护当前进度，运行清单及原始证据维护实际结果。全局模板不填具体项目路径或默认PASS。

对象/路线：SET；模型revision：SET；数据版本：SET；硬件/预算/授权引用：SET；截至时间：SET。

本表对应清单路径：SET_CHECKLIST_PATH；清单Git修订：SET_CHECKLIST_REVISION；清单SHA256：SET_CHECKLIST_SHA256。复制时绑定实际版本，更新清单后复核对应关系。每个明确对象单独一张完整14行表，tiny/目标模型/生产服务不共用一组状态；对象列写模型、硬件及运行范围，不能只写“已通过”。

分别记录适用性（适用/不适用及理由）、方法是否定义、该对象的执行状态（未开始/进行中/通过/失败/待核/不适用）与证据范围。tiny、目标模型、生产服务分别列对象；不能因tiny通过把整行目标任务改为通过。方法文档存在不等于执行通过。

| 环节 | 对象/运行范围 | 适用性/理由 | 方法已定义？ | 执行状态 | 证据等级 | 证据/未完成项/下一步 |
|---|---|---|---|---|---|---|
| 01 任务与验收定义 | SET_OBJECT | SET | SET | 未开始 | UNVERIFIED | SET |
| 02 数据接收与许可 | SET_OBJECT | SET | SET | 未开始 | UNVERIFIED | SET |
| 03 文档提取与OCR | SET_OBJECT | SET | SET | 未开始 | UNVERIFIED | SET |
| 04 保守清洗与质量筛选 | SET_OBJECT | SET | SET | 未开始 | UNVERIFIED | SET |
| 05 去重、污染与划分 | SET_OBJECT | SET | SET | 未开始 | UNVERIFIED | SET |
| 06 任务化数据与标注 | SET_OBJECT | SET | SET | 未开始 | UNVERIFIED | SET |
| 07 模板、token与监督 | SET_OBJECT | SET | SET | 未开始 | UNVERIFIED | SET |
| 08 原模型基线与训练配方 | SET_OBJECT | SET | SET | 未开始 | UNVERIFIED | SET |
| 09 工程体检与目标硬件小试 | SET_OBJECT | SET | SET | 未开始 | UNVERIFIED | SET |
| 10 有界训练与开发评估 | SET_OBJECT | SET | SET | 未开始 | UNVERIFIED | SET |
| 11 导出、合并与重载 | SET_OBJECT | SET | SET | 未开始 | UNVERIFIED | SET |
| 12 部署量化决策与开发复测 | SET_OBJECT | SET | SET | 未开始 | UNVERIFIED | SET |
| 13 独立确认、冻结与最终测试 | SET_OBJECT | SET | SET | 未开始 | UNVERIFIED | SET |
| 14 部署与运行监测 | SET_OBJECT | SET | SET | 未开始 | UNVERIFIED | SET |

量化子项另写：08训练量化use/skip/defer＋理由；12部署量化use/skip/defer＋理由；defer是待定，不能支持相应量化作业启动。两者是否量化分别判断。

汇报流程沿用01–14编号，先讲当前工作对应哪一环节，再讲子步骤、实证和下一步。只讨论某一环节可明确说“以下仅解释12”；不要用三个方法或九个父阶段替代完整流程。主环节实质变化时附原编号映射，不能静默删并。来源/许可、失败/恢复和成本全程留证。

证据等级：UNVERIFIED / DOCUMENTED / STATIC_CHECKED / SMOKE_TESTED / TARGET_VALIDATED / SERVICE_VALIDATED；只标此行对象有直接证据的等级。就绪验收逐表核对01–14齐全且唯一、字段填写、清单版本/SHA一致、主环节变化附编号映射。llm_preflight.py只检查其声明的运行合同，不校验本Markdown表及14环节覆盖；预检PASS不能替代该逐项复核。
