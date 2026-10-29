# 上游卡片：torchinfo（工具）

## 链接与许可证

- 仓库：<https://github.com/TylerYep/torchinfo>（默认分支 `main`）
- 许可证：MIT。

## 吸收的版本

- 记录点：2026-10-22 查到的默认分支 HEAD `3eb5f386139a3ed03f3a429302ace1e40c0eb173`（提交于 2026-10-13）。行号对应此 commit。
- 核对过的已安装版本：torchinfo 1.8.0（2026-10-22；`frozen_audit` 的 torchinfo 测试在装有它的解释器上运行，未装时跳过）。安装用当前项目的解释器；torchinfo 是可选依赖。

## 拿了什么

| 上游位置 | 用途 | 状态 |
|---|---|---|
| `torchinfo/torchinfo.py:48` `summary(...)`，参数 `col_names`（54）、`mode`（59） | 逐层打印参数量、输出形状；`mode="train"/"eval"` 控制 BN/dropout 的模式，避免在错误模式下统计 | 已实现（`../mlgain-integrate-component/scripts/train_sanity_checks.py`:`frozen_audit`：装了 torchinfo 时调用 `summary(model, input_size=…, verbose=0)` 附逐层表）；`col_names`、`mode` 未传，备选，未接入 |
| `torchinfo/enums.py:30` `ColumnSettings`，`TRAINABLE = "trainable"`（42） | 每层"可训练"列：确认新接入模块确实可训练、冻结部分确实冻结 | 已实现（`../mlgain-integrate-component/scripts/train_sanity_checks.py`:`frozen_audit` 读取每层结果的 `trainable` 属性，不经 `ColumnSettings`） |
| `torchinfo/enums.py:7` `Mode` | `summary` 的 mode 取值 | 备选，未接入 |

工具清单另见 `references/workflow/paradigms/vision-dense.md`。

与优化器成员检查配合使用：torchinfo 只看 `requires_grad`，看不到参数是否进了优化器（这一点见 [timm 卡片](timm.md) 的 `_param_groups.py`）。

## 没拿什么及原因

- 计算量（mult-adds）估计：当前选择不以 FLOPs 为约束。
- 嵌套模块深度展开的定制格式：默认输出够用。

## 下次升级看哪些路径

- `torchinfo/torchinfo.py`（`summary` 签名、默认 `mode`）
- `torchinfo/enums.py`（列名与模式枚举）
- 升级前确认新版本支持当前项目解释器的 Python 版本。
