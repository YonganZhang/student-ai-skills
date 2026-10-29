# 固定成熟原生Pipeline，按配置替换模型与数据

执行资产见[llm-native](../../assets/llm-native/README.md)。默认复用已采用的HF生态原生训练器，不另写forward/backward/optimizer调度。ms-swift固定源配方与HF Transformers/PEFT底层构成一条已定义路线；直接HF用TRL，Factory为备选，切换须栈卡与parity。只因用户不喜欢Llama模型，不能误排支持多模型的LLaMA-Factory框架。

## 稳定接口

- 模型profile：本地资产路径、官方revision、逐文件hash、model_type、template、dtype、trust_remote_code经审查；不自动下载或执行远端代码。
- 数据profile：messages等原生格式、来源/许可/簇/划分、task/route、token/labels；明确fit/select/evaluate/test可见范围。
- 运行recipe：目标、LoRA/QLoRA/全参、长度/batch/累积、学习率/rank、BF16、卡数/分片、步数/时限、保存/恢复和选择规则。
- 产物profile：base/adapter/merged/PTQ身份、推理器、量化决策、校准与质量/性能阈值、最终测试回执。

## 原生执行

原生JSON可直接交`swift sft run.json`、`swift export export.json`；不需要自研训练器。命令只是说明入口，先固定具体任务/许可/资产/预算，再从模板填入并解析实际版本参数。模板中的SET占位和未验证条件不能执行；旧output拒绝覆盖，输出与run manifest放项目。

运行前把所用全局模板与来源清单原样快照到项目run目录，记录原路径/版本/SHA及填参差异；父run_manifest的code路径属于项目内文件，不向它传项目外的全局路径。保留原始模板和实际生效配置，不能只存一条命令。

固定脚手架不等于所有模型一键通用：替换新模板/MLA/Mamba/MoE、VLM媒体token或新量化方式，先查原生支持再做局部验证；参数/依赖改变写变更记录。多卡用原生torchrun/Accelerate/DeepSpeed/FSDP/Megatron等已支持后端，不能只把nproc改大当分片。

继续训练需保存并恢复optimizer/scheduler/RNG/数据顺序状态；只保存adapter不代表能严格resume。CPU参数解析不代表GPU算子可运行；帮助命令、mock与静态检查不算训练成功。

## 兼容与维护

固定修订用于复现已验路径，并非永久锁死所有模型。换版本前先保存失败/旧证据、查对应文档与依赖解析，隔离环境；不让pip升级共享torch/工作中的OCR。新源码配方与应用配置分别记录SHA及差异，上游许可和来源文件随模板保留。

每个分支标DOCUMENTED/STATIC_CHECKED/SMOKE_TESTED/TARGET_VALIDATED等实际范围；不能因SFT smoke通过就把QLoRA、PTQ、VLM、RL或服务标已验。目标任务前重复受影响的模板/梯度/恢复/质量检查，按父S9留run manifest。项目的来源哈希/审批薄包装可以保留，但不作为另一训练循环或唯一全局入口。

## 执行前预检

在原生配置之外填写run-contract与数据identity manifest，绑定配置/数据/量化决策SHA及真实授权范围；对当前支持的本地JSONL SFT和BNB量化导出先运行 `python3 ~/.claude/skills/share-autoresearch-engine/scripts/llm_preflight.py run-contract.json`，再执行原生CLI。该薄预检不训练、不自动调用CLI，也不是权限沙箱；元数据正确性、近似重复与真实授权仍须验收。框架不认识的metadata不塞进原生配置。

ZeRO3和resume模板仅提供原生配置入口；严格恢复要核验optimizer/scheduler/RNG/数据顺序及连续训练对照，缺任意项不能称通过。模板的存在不代替目标模型、多卡QLoRA或硬件验收。

preflight当前支持已绑定本地JSONL的有界SFT，以及选定/合并checkpoint的BNB无校准导出；会拒绝未登记的数据覆盖路径。量化源通过完整文件清单与逐文件SHA绑定，哈希读盘成本计入项目准备；校准路径必须与fit/select/专用calibration清单一致，evaluate/test不能入校准。身份manifest必须覆盖真实样本，预检不能鉴定虚构元数据、近似重复或专家事实。

薄预检不覆盖merge操作及14环节Markdown状态表完整性。合并前人工核查匹配base/adapter的身份、SHA、原生配置、预算与新输出目录，并保存manifest；逐环节表按其版本绑定与完整性要求单独复核，不以SFT/BNB预检PASS替代。

需要为某环节新增或更换核心实现时，先走`~/.claude/skills/dev-find-wheels/SKILL.md`比较成熟工具、提交用户选择并保留来源/适配证据；既有已选栈按批准范围复用，不重开训练器。14环节的项目接口索引记录真实可调用入口、输入输出和未验状态，不用空骨架充数。
