# 把模块接入检查变成实际执行

这套入口执行项目自己的断言，**不会自动猜每一维的意义，不会自动生成正确测试，也不会接管已有训练命令**。它把缺项、失败、超时和证据留存做成可执行检查；助手按本流程消费报告。项目有正式启动器时可将返回非零接成启动前条件，不宣称所有现有项目已被自动拦截。

## 每个项目必须落实的五类检查

| ID | 断言应覆盖的事实 |
|---|---|
| `interface` | 真实插入点输入/输出每一维的含义；多种有效形状和易混轴案例；shape/dtype/device；不靠广播掩盖错误 |
| `training_path` | 经真实训练入口构造模型/损失/优化器；配置开关确实生效；新增可训练参数按身份进入优化器；前向/损失有限、反向及实际参数更新符合初始化机制 |
| `data_semantics` | 样本身份、时间、模态对应、单位/归一化与预测时可见性；有 mask 时验证改动被遮蔽值不影响有效输出及全缺失行为；无 mask 时仍验证适用的数据语义 |
| `baseline_control` | 关闭模块或允许的退化模式能回到原 baseline；控制 RNG/训练模式与副作用。改变接口而无法恒等时用明确的桥接对照，并解释界限 |
| `checkpoint` | 走项目真实 save/load，确认新增参数及必要状态被保存，恢复后预测在声明容差内一致；若声明断点续训，还检查优化器等续训状态 |

`interface`、`training_path`、`data_semantics` 不可整体跳过；内部哪些子项不适用，要在测试/报告写理由。`baseline_control`、`checkpoint` 仅在确实不适用的任务可用 `not_applicable` 说明，交独立审查判断，不能填空。不要创建全是 `print('PASS')` 的探针。

复用兄弟技能 `mlgain-integrate-component/scripts/probe_hooks.py` 的参数注册、梯度及真实更新函数；接入模板位于 `mlgain-integrate-component/assets/pytorch-component-socket.py`。这些是辅助工具，不能替代宿主训练入口的测试。按当前执行器技能目录定位，不跨用另一个执行器的配置目录。

零初始化分支可在首步出现零梯度，应检查若干步后预期的解锁和更新；BatchNorm、batch 对比损失等依赖批次组成，不要求拆批前后机械相等；非确定算子采用事先声明的合理容差。数据语义断言应尽可能由索引/时间戳/已知小样本得出，不能只检查张量大小或用同一个错误变换生成“标准答案”。

## 项目命令清单

复制 [integration-plan.example.json](../../assets/integration-plan.example.json) 到项目 `_tests/integration-plan.json`，把示例测试名与 Python 可执行文件换成项目已有的实际路径。示例引用的项目测试**不随技能提供**；没有这些测试时运行会失败，必须先补真实断言。一个命令对应一类；复用项目已有 pytest/unittest 即可，不要求统一模型接口。

从本技能根目录调用：

```bash
python3 scripts/integration_gate.py "$PROJECT/_tests/integration-plan.json" --project "$PROJECT" --output "$PROJECT/_tests/_artifacts/integration-run-001"
```

- 命令为 argv 数组，不做 shell 插值；使用项目 venv 的 Python 路径，不能把含管道的 shell 文本当数组元素。
- 总预算默认 300 秒，每项默认 60 秒；耗时项目显式设置合理预算。超时只终止本入口创建的进程组，不使用 `pkill -f`；命令不应自行脱离进程组启动后台训练。
- 输出目录必须不存在，防止旧报告混入本次结果。里面保存计划、每项实际命令/工作目录/时间/退出码/日志及 `report.json`。
- 非零返回值表示缺项、配置无效、命令失败或超时。首次失败后后续项标记 `not_run`；修复后用新目录重跑。`not_applicable` 单独列出，不能写成执行通过。
- 返回 0 / `checks_passed` 只进入独立审查；不表示发现了创新、不证明泛化提升，也不自动触发远程部署。

审查报告至少写：实际审查者身份、原始输入文件、本次运行目录、断言覆盖缺口、问题及证据位置、`accepted / changes_needed / review_unavailable`。同模型独立上下文和异模型审查分开标注。

## 排查模式：`"profile": "triage"`

结果反直觉、要判断"模块无用"之前，在计划里加 `"profile": "triage"`。除上面五类外还必须有：`evaluator_selftest`、`input_alignment`、`overfit_train_transforms`、`selection_exposure`；`augmentation_sync`、`positive_control` 可写 `not_applicable` 加理由。各项含义与做法见 [排错](../triage/README.md)；不加 profile 时行为与原来完全一致。

## 本工具的真实行为验收

`tests/fixtures/aris_torch_probe.py` 使用 PyTorch 小模型，演示通道/时间轴混淆、优化器漏参数和 mask 未消费三个失败，并验证正常更新、关闭对照、保存恢复。它是技能工具测试，不是用户项目已通过的证据。

通过设置 `ARIS_TEST_PYTHON` 为已有 PyTorch 环境的解释器，执行 `tests/test_aris_torch.py` 可复跑：它经 `integration_gate.py` 启动真正的张量断言，核对失败日志和退出状态。没有该变量时明确 skip，不假报张量测试通过。不需要 GPU 或安装新包。
