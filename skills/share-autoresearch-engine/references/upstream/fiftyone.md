# 上游卡片：FiftyOne（工具，暂不接入）

## 链接与许可证

- 仓库：<https://github.com/voxel51/fiftyone>（默认分支 `main`）
- 许可证：Apache-2.0。

## 吸收的版本

- 记录点：2026-10-22 查到的默认分支 HEAD `aacfc8182fc5353296b5edd7475e63335fedb5cb`（提交于 2026-10-17）。行号对应此 commit。
- 未安装。

## 拿了什么（供将来选型）

| 上游位置 | 内容 | 状态 |
|---|---|---|
| `fiftyone/core/labels.py:1079` `Keypoint`、`:1139` `Keypoints` | 点标注的数据结构（归一化坐标、可带置信度），可用于预测与真值的并排浏览 | 备选，未接入（`references/workflow/paradigms/vision-dense.md` 工具表只列出 FiftyOne 名称与用途） |
| `fiftyone/core/labels.py:1340` `Heatmap` | 热图字段，可与图像叠加查看 | 备选，未接入 |

工具清单另见 `references/workflow/paradigms/vision-dense.md`。

## 没拿什么及原因

- 关键点评估器：FiftyOne 没有针对关键点/点定位的内置评估（检测、分割有），点匹配 F1 仍用项目自己的评价器。
- 整体安装：依赖 MongoDB 和较重的 App 服务，维护者环境是共享服务器、空间有限；当前用叠图脚本即可完成可视化检查。
- 数据集管理功能：与项目 `_data_registry` 重复。

## 什么时候重新考虑

需要多人交互式浏览大量预测、按指标筛样本，而叠图脚本已不够用时。届时在独立环境安装并设资源限制。

## 下次升级看哪些路径

- `fiftyone/core/labels.py`（`Keypoint` / `Heatmap` 字段定义）
- `fiftyone/utils/eval/`（是否新增关键点评估）
