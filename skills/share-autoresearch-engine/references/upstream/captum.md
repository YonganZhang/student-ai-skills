# 上游卡片：Captum（工具）

## 链接与许可证

- 仓库：<https://github.com/meta-pytorch/captum>（默认分支 `master`；旧地址 pytorch/captum）
- 许可证：BSD-3-Clause。

## 吸收的版本

- 记录点：2026-10-22 查到的默认分支 HEAD `b89cccbe0add104f734793be69488c078164c532`（提交于 2026-10-15）。行号对应此 commit。
- 尚未安装或验证；接入时装进当前项目的解释器，并在此记录验证过的版本。

## 拿了什么

| 上游位置 | 用途 | 状态 |
|---|---|---|
| `captum/attr/_core/layer/layer_activation.py:21` `LayerActivation` | 取某层激活，量化新模块的输出幅度 | 备选，未接入（设想用于 `../mlgain-integrate-component/scripts/module_probe.py` 的有效贡献检查；该脚本现在用自写的 `ResidualSocket`/`EffectiveContribution`，不导入 Captum） |
| `captum/attr/_core/layer/layer_feature_ablation.py:29` `LayerFeatureAblation`、`captum/attr/_core/feature_ablation.py:269` `FeatureAblation` | 消融式归因：把某层/某组特征置为基线后看输出变化 | 备选，未接入 |

用法要点：Captum 的归因目标须是标量。热图输出的定位模型要先包一层，把热图变成标量目标（例如真值点附近窗口内的热图和、或某个预测峰值），再传给归因方法；窗口半径要在真实物理尺度上验证过。

工具清单另见 `references/workflow/paradigms/vision-dense.md`。

## 没拿什么及原因

- 梯度类归因（Integrated Gradients、Saliency 等）的结论：对热图模型噪声大，只作为可视化辅助，不作为模块"有用/无用"的证据；证据仍是强制关闭模块后的分数变化。
- Captum Insights 可视化界面：不新增服务。
- LLM 归因模块：与本任务无关。

## 下次升级看哪些路径

- `captum/attr/_core/layer/layer_activation.py`
- `captum/attr/_core/layer/layer_feature_ablation.py`、`captum/attr/_core/feature_ablation.py`
- 仓库已从 pytorch 组织迁到 meta-pytorch；再次迁移时更新 UPSTREAM.json 的 `repo`。
