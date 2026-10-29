# Strata部署子技能

归属：DL Pipeline Base → 大模型部署 → Strata；状态为DOCUMENTED，尚未安装或通过目标模型实测。涉及Strata安装/模型选择/启停/API/排障/升级时从部署父流程进入；读取本文件不授权下载或占用资源。来源以[固定清单](sources.json)为准，升级时查对应release和官方AI_SETUP，而非直接使用latest。

## 适用与边界

Strata提供本地推理/兼容API，把模型工作集放在GPU显存、系统RAM和SSD，低位数模型与MoE稀疏计算一起降低驻留门槛。它不是微调训练器，也不表示原精度总权重装进小显卡。

官方DeepSeek分支为strata-dsv41，独立于Qwen引擎。DeepSeek-V4.1-Flash-1017有约763B总参数；量化包backbone约551.9B，不能拿backbone或激活参数代替总参数。代码、模型、第三方量化与drafter分别核身份/许可；高分辨率图片、并发与长上下文逐引擎验证。

固定资料中的12GB显卡路线还需要约46–64GB系统RAM与SSD分层：1.75/2.00/2.25bpw是backbone平均位数，Engram不按该位数压缩，另有共享文件。量化卡总下载约231/249/266GB（backbone+Engram），Strata加入drafter后约239/257/274GB；不是全部参数的纯2bit大小，也不保证包含安装/转换/缓存所有峰值。不同统计口径不可相加两次。

Strata文档中单卡12GB示例约4.7或8–10 token/s，硬件/CPU/RAM/磁盘不同，不能据此预测另一机器。维护者报告与本机实测分开，中文领域质量另验；量化任务均分保持不等于分布、文本质量或所有推理步骤无损。

## 执行时必须核对

- 单卡显存总量不超过16GiB时，文档中的Faster默认可能每token只用5个专家，原生完整路由为6个。比较完整路由时显式`--speed full`（需相应引擎版本），记录量化与专家数；包内保留所有专家不等于每次计算原样。
- DeepSeek该版本默认/验证上下文8K；模型原生1M、其他家族32K等不能照搬。文档明确DeepSeek不支持同时多个请求和图像输入，不把通用CLI flag当该引擎已支持。
- 使用官方Terminal/release，而非第三方项目中的旧Windows路径、端口或“只支持Qwen”限制。官方仓库有AI_SETUP操作指南；第三方Artemis的strata skill是特定Qwen/OpenClaw环境，不自动安装为通用DeepSeek部署能力。
- release/Terminal、Control、Qwen与DeepSeek引擎各自版本可能不同，分别记录；不能只记桌面app版本。计划输出与实际CLI帮助/资产SHA要一致。
- 先确认高速存储位置；硬盘容量够不等于随机读取够快。大RAM新版本可让CPU专家驻留，Engram/冷启动与共享内存压力仍须测。不要为测试去停止别的项目或清理用户文件。

## 原生计划示例（不是执行授权）

只有已选择Strata且装好对应版本时，再绑定GPU、快速存储和模型包，先跑原生plan：

```bash
strata launch --family deepseek41 --model ist-das-2.00bpw --speed full \
  --gpu SET_GPU --data-dir SET_FAST_STORAGE --plan --output json
```

SET未绑定不能执行。核对最终解析的家族、模型、专家数、默认上下文、下载清单、RAM/VRAM和目录，再按批准范围使用官方launch。不要复制默认Qwen的plan到DeepSeek，也不要执行未经审阅的curl/PowerShell安装脚本。健康和API验收沿官方AI_SETUP，推理/质量/成本记录沿部署父流程。

## 原生生命周期

以固定版本的[官方AI_SETUP](https://github.com/Niko1221/Strata/blob/4b9e05a2a806a3fe24f7b2560d98626c37dade35/docs/AI_SETUP.md)作为操作主线；它的本机路径、默认模型/硬件示例须替换为项目实际配置，版本升级重新核对。只保留调用编排，不复制上游安装器或推理代码。

| 阶段 | 原生入口与完成依据 |
|---|---|
| 盘点与绑定 | 记录实际资源/存储、包与模型来源；填写[运行记录模板](../../assets/llm-deployment/strata-run.template.json)，不在全局写机器状态 |
| 安装Terminal/引擎 | 在明确安装/下载范围内，审阅固定release安装器及校验方式，再按官方指南安装；记录Terminal、Control、引擎分别的版本，使用隔离环境，不改共享torch或驱动 |
| 预检与获取模型 | `strata --version`、`strata launch --help`及上面的显式family/model/quality plan；检查实际解析的目录、缺失下载、上下文及预算后才获取/打包。已有权重可用官方model-path，不凭同名认定兼容 |
| 启动与健康 | 使用核验后的同一组原生launch参数；已在运行先查`strata launch --status`，不直接restart。启动后核对实际地址的`/health`、`/v1/models`及`strata doctor --live`，确认loaded/模型身份；退出0或下载完成不算服务已验 |
| API与客户端 | 用实际地址/模型/凭证发有界真实请求，验流式/工具参数/停止与中文输出；客户端接入按官方connect指南，只有需要且已授权时写客户端配置并备份；密钥不进入Git或共享日志 |
| 排障、更新与回滚 | 区分后端缺失/模型包不齐/资源不足/未loaded/模板解析/质量退化，保留日志和失败；`strata update --check`只检查，实际更新前保存版本/配置与恢复路径，协调仅属于本次的服务；原生stop后回读确认，不能停其他任务 |

安装/预检、短smoke、目标质量和服务验收分别留证。更新先保存旧安装与数据引用，按差异复测；失败按已保存版本/配置恢复，不以删除模型或重下全部权重当默认修复。具体预算、地址、进程归属和验收回执放项目；官方指南与部署父合同冲突时先说明，不擅自扩大授权。
