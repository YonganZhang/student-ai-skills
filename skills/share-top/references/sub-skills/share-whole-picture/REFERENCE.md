---
name: share-whole-picture
description: "把项目当前全貌生成可查看 HTML。仅在用户明确要网页/HTML/项目封面时触发；普通 whole-picture 对齐、TOP 更新和科研图不触发。"
---

# Whole Picture HTML

Whole picture 是项目当前状态的查验与学习界面，不是 changelog、聊天摘要或数据仓库。只在用户明确要网页时生成或更新。

## 边界

- 普通“看全貌、对齐思路、更新六合一”回到 `share-top`，不自动产 HTML。
- 论文 figure、统计图和科研架构图走科研绘图技能 `share-sci-plot`（可选，本包未包含）。
- HTML 只展示已有真源能证明的当前方法、数据流、代码入口和状态；历史放 TOP/changelog。
- 项目已有 `picture.yml`、renderer 或模板时复用；不要另建平行真源。

## SOP

1. 读取项目 TOP、registry、codemap、pipeline 和已有 whole-picture 资产，确定 canonical source。
2. 建立结构化内容合同：目标与 gap、方法/数据流、角色和数据源、可验证代码入口、当前状态、目录与下一步。
3. 对每个节点核对真实实现的输入、输出和调用关系；不靠旧网页或记忆补字段。不确定内容标为待确认，不包装成事实。
4. 从结构化数据渲染 HTML。优先复用 `templates/details_native_picture.html` 和现有 CSS；交互保持原生、移动端可用、无脆弱依赖。
5. 做内容与视觉双审：真源一致性、死方法移除、链接/锚点、展开收起、窄屏和可读性。
6. 只有用户要求发布时才走既有文件分享流程；交付新 URL 后说明数据真源和未确认项。

## 最小页面合同

- 顶部 TL;DR、关键指标和章节导航。
- 项目目标、核心方法、数据/角色、端到端流程、验证或案例、代码/目录与下一步。
- 流程边表达真实数据依赖；平行节点不为了好看强连顺序。
- 代码名保留原文，人话解释与实现标识分层。
- 页面显示“当前有效状态”，不混入版本事故和废弃实现。

## 资源路由

| 需要 | 读取 |
|---|---|
| 默认无 JS/移动端模板 | `templates/details_native_picture.html` |
| 树形或深层流程兼容模板 | `templates/binary_tree*.html`、`templates/binary_tree.css` |
| 旧项目 picture 源、节点规范、流程图语义和交互兼容 | `references/legacy-whole-picture-guide.md`，只抽取仍由当前代码验证的部分 |

完成标准：页面内容能回指真源、当前状态无历史污染、交互在桌面和窄屏可用，且没有因生成网页反向篡改项目事实。
