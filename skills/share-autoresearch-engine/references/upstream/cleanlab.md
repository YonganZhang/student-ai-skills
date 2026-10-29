# 上游卡片：cleanlab（工具）

## 链接与许可证

- 仓库：<https://github.com/cleanlab/cleanlab>（默认分支 `master`）
- 许可证：Apache-2.0（以 2026-10-22 GitHub 许可证接口为准；升级时复核 `LICENSE` 是否变化）。

## 吸收的版本

- 记录点：2026-10-22 查到的默认分支 HEAD `750625747de1b26d8530954f51f0530bd0b51d3c`（提交于 2026-01-13）。行号对应此 commit。
- 核对过的已安装版本：cleanlab 2.9.0（2026-10-22；本技能脚本尚不调用它）。安装用当前项目的解释器。

## 拿了什么

| 上游位置 | 用途 | 状态 |
|---|---|---|
| `cleanlab/segmentation/filter.py:14` `find_label_issues(labels, pred_probs, ...)` | 找疑似标错的像素/图像。点标注没有现成接口：把每个点渲染成小圆盘得到二值掩膜作为 `labels`；`pred_probs` 必须用交叉拟合（该图未参与训练的模型）输出的热图，否则模型会"记住"错标 | 备选，未接入（`references/workflow/paradigms/vision-dense.md` 工具表只列出分割模块链接；点转掩膜与交叉拟合用法只在本卡片；`references/triage/README.md` 第 2 层未提及） |
| `cleanlab/object_detection/filter.py:32` `find_label_issues`，同目录 `rank.py` / `summary.py` | 检测框格式的标签问题查找；点可转成固定大小的框后试用 | 备选，未接入（`vision-dense.md` 工具表只列出模块链接） |

工具清单另见 `references/workflow/paradigms/vision-dense.md`。

## 没拿什么及原因

- 分类、多标签、回归、Datalab 等模块：与点定位任务不对口。
- 用 cleanlab 结果自动删样本：只作为人工复核的排序依据，不自动改数据（数据只读原则）。
- 非交叉拟合的预测概率：会系统性低估错标，不用。

## 下次升级看哪些路径

- `cleanlab/segmentation/`（`filter.py`、`rank.py`）
- `cleanlab/object_detection/`
- `LICENSE`
