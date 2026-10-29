# React 组件结构技能的使用范围

vercel-composition-patterns 已从通用技能集合退役；原件未随本包发布，需要时从上游 `vercel-labs/agent-skills` 按固定版本获取。本页只帮助识别项目是否需要组件结构规范；确定需要并已有授权时，再按项目模块流程引入固定版本，不能当作全局已安装技能调用。

## 先识别，不要求用户知道技术栈

- 看目标前端包的 package.json、锁文件和真实源码入口，确认是否声明并使用 React。多包仓库看正在修改的包，不凭仓库根目录的传递依赖判断。
- 声明 React、react-dom 或 React Native 且目标组件真实使用它时，可在组件结构任务中使用此技能。Next.js 也要核对所在包及 React 版本。
- Vue、Svelte、静态 HTML/CSS、后端 Python，或只出现 React 文档/示例时，不把它当作该项目的组件规范。不为使用技能而安装 React 或迁移框架。
- 看锁定/实际使用版本；范围跨 React 主版本或无法确认时，不应用 React 19 专属写法。

## 与现有前端技能配合

视觉、排版与交互风格继续走项目已有 frontend-design/design-taste-frontend；大量模式开关、复用组件接口或共享状态变复杂时，先用项目现有组件规范，确有缺口时评估项目模块。简单页面无需为了“组合”增加 Provider 或组件层。

原版 React 19 章节把 useContext 标作反例，这是该技能的风格取向，不代表 React 官方取消支持。按项目兼容范围决定是否使用 use/ref-as-prop，不单为换写法重构正常代码。正常 disabled/open 等布尔状态也不因“避免 boolean props”被机械删除；重点是混杂多种业务模式造成的分支组合。

重构仍需保留用户可见行为和可访问性，检查受影响调用方并做项目已有的相关验证。TOP 项目按 share-top 登记真实任务、代码入口及验证证据；React 规则本身不写入六合一全局核心规则。

## 验收情境

React 18 后台复杂弹窗：可使用组合设计，跳过 React 19 规则。
React 19 共享编辑器：可按需用 Provider/children；不批量替换正常 useContext。
Vue 管理端、静态落地页、Python 实验：不触发 React 重构。
多包仓库只有文档站用 React：只对文档站相关组件使用。

核对来源：Vercel agent-skills，commit `063bee94c3f4df8453406c830b0a7df0f2860278`，上游声明 MIT；本地选用指导 2026-09-23。
React 官方：[useContext](https://react.dev/reference/react/useContext)、[use](https://react.dev/reference/react/use)。
