# 模板验证边界

本页说明“存在配置”“原生解析”“tiny运行”与“目标任务验收”的区别；具体项目路径/硬件/模型/得分留在各项目。没有一项tiny结果能外推为任意模型/设备已验。

| 资产 | 证据等级 | 限制 |
|---|---|---|
| BF16 LoRA SFT | 参数绑定后，dense tiny原生单卡smoke与独立adapter重载 | 非领域质量或收敛证明 |
| NF4 QLoRA SFT | 参数绑定后，dense tiny原生4bit训练、梯度/adapter更新与optimizer状态 | 不覆盖MoE/VLM或多卡QLoRA |
| merge | 参数绑定后，原生合并导出；同一adapter独立加载等价 | 不把BF16合并舍入误差冒称严格bitwise等价；正式质量另验 |
| quantize-bnb4 | 参数绑定后，原生无校准权重量化、序列化重载/生成 | 非校准型AWQ/GPTQ；没有业务质量/服务性能合格结论 |
| ZeRO3 / resume配置 | DOCUMENTED_NATIVE_RECIPE；目标环境重验 | 保存optimizer/RNG不等于已经严格恢复；须连续/恢复对照 |
| run-contract / preflight | 静态正负例：hash、簇/split、量化决策、校准角色、原生路径与步数范围 | 不是权限沙箱、语义去重、专家标签或实际GPU预算执行器 |
| CPT/DPO/RL/QAT/全参/VLM | DOCUMENTED_ROUTING_ONLY | 默认资产不执行，进入时补原生配方与完整验收 |

固定参考栈：ms-swift 484e836d691a52fd8c1723137ee3d64c6e066683、HF Transformers/PEFT；BNB路径参考0.50.2。安装版本/模型/资产/命令/模板SHA和每项实际运行范围记录在项目run manifest，不将此表当跨硬件认证。

模板中的SET字段必须完成实际绑定，原始模板和填参配置分开保存。全局文档/配置静态契约测试不验证数学正确性或真实任务；原生CLI/少步/重载和目标任务测试另列证据。偏好/奖励/量化质量等未做项目证据不得标PASS。
