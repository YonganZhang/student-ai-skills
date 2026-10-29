---
name: content-pptx-gen
description: "PPT绘图、生成PPT图片、图片型幻灯片：AI生图整页，默认白底、内容充实，交付PNG或PPTX与备注；原生可编辑元素走 content-real-ppt。"
---

# 图片PPT

默认通过宿主官方图片工具生成完整页面，可选模型时用 ChatGPT Image 2（GPT Image 2）；点名 Nano Banana 2 / Gemini 生图时改用 Google 官方会员入口。提供方选择与能力边界统一见 [图片后端](references/image-backend-alternatives.md)。生成后用完整图片组装 PowerPoint，备注保留可编辑文字。

## 先确定产物与工具

- “用技能生成PPT图片”“PPT生图”“图片型幻灯片”都走本技能，生成的是每页含文字与图示的完整 AI 图片。把 HTML/SVG 截图装进 PPT、用形状拼版或只换 PPT 背景，均未完成这一交付。
- 明确要在 PowerPoint 里编辑文字、形状、图表时走 `content-real-ppt`；同时要图片稿和可编辑稿时，先完成生图，再按配对流程重建，不能用后者替代前者。
- 生成或重绘页面前，读取下表的图片工作流与设计手册，并核对当前会话实际可调用的图片生成工具；能读图片、写PPT或加载技能不等于能生图。只将已有图片原样装入PPT时直接走组装，不要求生图工具。
- 新生成的图片PPT默认 **纯白背景 `#FFFFFF`、16:9、内容充实且可读**。用户明确指定其他背景时覆盖默认；参考图的暗色不自动覆盖白底。正文要有关键事实、关系与解释，不以大标题、几个图标或空白卡片代替内容，也不按固定字数硬塞文字。

## 路由

| 任务 | 必读 |
|---|---|
| 生成、修改完整图片PPT（包括单页PNG） | [图片工作流](references/slide-image-workflow.md) + [设计手册](references/slide-design-manual.md) |
| 新 SCI 图一、论文方法架构、机制插画、图形摘要 | 如已安装 `share-sci-plot`（可选，本包未包含），先读其科研示意图候选合同，再走图片生成；科研单图不套演示页模板 |
| 信息密度、主线、配色与版式 | `references/slide-design-manual.md` |
| 用户点名 Gemini / Nano Banana 2 生图 | [图片后端](references/image-backend-alternatives.md) → Google 官方会员生图 |
| 工具能力、模型与额度说明 | `references/image-backend-alternatives.md` |
| 图片组装PPTX、每页演讲备注 | `scripts/images_to_pptx.py --help` |
| 用户明确要对应可编辑重建页 | `references/paired-editable-delivery.md`，再调用 `real-ppt` |
| 用户明确只要PNG | `scripts/package_slide_images.py --help` |
| 用户明确点名Banana Slides工作流 | `references/banana-slides/README.md`；其中旧FAL调用不再使用 |

## 完成标准

- 本技能兼作科研单图的图片生产入口：按上述候选合同完成实际候选图片，论文尺寸、语言、科学内容与字体约束优先。以下逐页、标题、16:9 和备注要求仅适用于图片PPT；普通整套PPT不逐页自动扩成多个版本。
- 每页由图片工具生成最终标题、正文、图示与版式；代码只负责装入PPTX、写备注与检查，不叠字补成整页。
- 科研叙事先明确背景、Gap、研究目标、研究内容与验证关系。需要这些栏目时写出“研究目标：……”等完整文字，不让图示替代定义。
- 每页一个中心问题，图与解释回答该问题，结论承接下一页；保留必要的技术、工程背景和比较条件，避免只剩图标与口号。
- 先确认代表页画风，再用同一代表图约束其他页；已有批准样式或已授权全套时直接继续。
- 按用户反馈逐页核对修改，旧页不因为已有图片就默认通过。封面或其它指定保留页按要求保留。
- 精确数据图由真实数据生成并作为内容参考；可按科学图例外精确嵌入，不能让生图工具重造点位、曲线或单元数。
- 每个最终图片保存到项目输出目录，记录实际尺寸、提示词、内容/风格参考与工具来源。工具未返回模型ID或计费信息时如实标记未知，不伪造4K或额度结论。
- 逐页查看新生成或重绘的实际图片，核对背景、文字完整性、内容密度和关系正确性；未获指定的黑底、缺字或只有装饰的页先用图片工具修正，再组装。提示词写了要求、PPT能打开，都不能代替画面验收。
- 用户要PPT时交付可打开的`.pptx`，每页都有演讲备注。用户只要图片则交付PNG；明确要图片页加可编辑页时按配对流程制作。
- 图片型PPT每页为整页图片。备注可编辑，封面可按用户要求自行加标识。
- 工具不可用、限流或失败时报告实际错误并保留进度；不转用FAL、API Key、非官方OAuth客户端或代码绘制整页。

## 平台适配与旧流程

Codex、Claude、DeepSeek/DSH 共读本技能，工具能力按当前会话核验。DSH 用 `skill` 加载名称 `content-pptx-gen`；只有文件读取工具时读取本文件及对应参考。默认路线使用宿主实际提供的官方图片工具；Claude/DSH 等宿主缺少该工具时按[图片后端](references/image-backend-alternatives.md)保留可交接进度，不能改成代码排版并称为已完成图片PPT。显式 Nano Banana 2 路线沿用 Google 官方入口，不因主控平台而改提供方。
旧FAL流程已退役（归档未随本包发布）。`scripts/generate_pptx.py`仅保留停止执行并指向当前流程的兼容提示，不能生图。
