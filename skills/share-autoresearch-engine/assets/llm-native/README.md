# 原生LLM Pipeline模板

入口：[LLM子流程](../../references/llm-finetuning/README.md)。这些是固定版本原生参数模板，不包含自写训练循环；实际计算由ms-swift→HF Transformers Trainer/PEFT等上游完成。项目已有原生栈可继续使用。外部源码在`ms-swift/upstream/`原样保留，SHA/许可见`ms-swift/UPSTREAM.json`。

## 使用方式

1. 按[14环节清单](../../references/llm-finetuning/execution-checklist.md)确认任务、数据边界、预算与栈卡。使用[逐环节状态模板](stage-status.template.md)记录对象和证据。核对对应版本/模型/硬件支持；基准参考ms-swift修订`484e836d691a52fd8c1723137ee3d64c6e066683`，并非所有任务永远锁死此版。
2. 将需要的原生模板快照复制到项目新run目录，替换全部SET；填写训练/部署量化决策、run-contract与数据identity manifest，绑定模板、配置、数据及来源SHA。原生val_dataset只对应select，evaluate/test不送入trainer。模型/模板/LoRA模块/长度/batch/学习率/步数均按任务验证，不当最优默认值。
3. **任何训练或导出之前**，先核查具体授权/预算/环境并禁用意外下载；对薄预检已覆盖的本地JSONL SFT与BNB量化导出运行[原生Pipeline中的preflight](../../references/llm-finetuning/native-pipeline.md)。检查通过只证明声明的一致性，不代替真实数据、许可、预算及授权；不合格先修复再执行。量化源完整资产清单和SHA按导出环节绑定。
4. 工程smoke不使用evaluate/test，训练输入只用fit或合成夹具，select仅用于开发验证。先模板/少步/实际更新/重载测试，再目标模型最小可行硬件、按需多卡；凡声明支持恢复或计划中断续训，须严格恢复对照；通过所需检查后才启动有界正式作业。训练由原生`swift sft run.json`完成，多卡/分片按已验后端配置，配置不自动安排GPU。
5. 用select选择checkpoint；需要合并时用`swift export merge.json`，合并前人工核对base/adapter身份与SHA、配置和新输出路径，合并后独立重载；薄预检当前不覆盖merge操作本身，不覆盖原产物。部署量化选择采用时按原生`swift export quantize-bnb4.json`等已验配方执行；BNB是无校准权重量化，不替代AWQ/GPTQ的校准或证明FP8/FP4支持。训练/部署量化均可选择保持原精度，理由明确；PENDING不能作就绪决定。
6. 对最终候选做开发质量与性能复测、独立evaluate确认，冻结后最终test，再按目标服务验收和回滚。tiny训练/量化成功只算工程检查；量化运行成功不等于领域质量合格。直接HF固定TRL路线需另验受影响接口/parity。

模板尚未绑定任何真实资产；SET占位不能执行。实际命令、实际生效配置、代码/模型/数据hash、环境与scope放项目；输出新目录、保留失败，不自动推送。配置JSON不是授权沙箱，使用者仍须核查真实范围与前置验收。

## 已验范围的记录原则

模板发布时可报告固定版本上的CPU解析、tiny单卡训练或量化序列化；具体项目/机器结果记录于项目，不写进全局当普遍能力。Qwen式dense tiny成功不证明MLA/Mamba/MoE/VLM、多卡QLoRA、A100、正式任务或服务合格。项目中的预览/范围/哈希薄包装可保留，训练仍由上游负责。

## 变更

更换模型/数据/资源只改原生配置与绑定；新增算法/内核/训练目标先核对上游实现，使用已支持的原生扩展。默认不自研Dataset/Trainer/训练循环。若研究问题必须修改损失/adapter/reward，按父S6写假设和受控对照，其余工程继续复用。

附加模板：`sft-zero3.json`用原生ZeRO3，`sft-resume.json`恢复完整检查点；两者须项目目标模型/硬件与恢复对照。`quantize-bnb4.json`是无校准部署权重量化（可归入广义PTQ），不是校准型AWQ/GPTQ。逐模板状态见`VALIDATION.md`。

sidecar填写：决策值为`use`/`skip`/`defer`，配具体reason；`defer`不能用于正在执行的量化。data-manifest只含身份与接受凭据/文件SHA，不含test答案；quantize源资产清单含每个文件相对路径及SHA，并由run-contract绑定其SHA。状态/量化决策/真实授权分别记录，预检PASS不授权执行。
