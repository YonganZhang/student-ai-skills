# Impeccable：可选的项目设计核心

状态：可安装候选；安装与拒绝路径有测试，设计效果需目标项目实测。现有前端设计模式保持原预设；用户明确选择 Impeccable 时安装本包，不静默替换既有方案。

## 配方与边界

- 来源：`https://github.com/pbakaus/impeccable`，Apache-2.0；固定 commit `d631a8827f99414d2b6daba4ef08b7f8701751d7`，skill 4.5.2，engine 0.1.14。
- 使用上游编译好的 Claude / Codex skill 分发目录，保留完整按需 references。安装器只读取 Git 对象，不执行下载仓库里的安装代码。
- 每个项目入口追加本地适配指针并复制 [接入合同](impeccable-adapter.md)，明确宿主指令、既有真源与授权优先；POSIX launcher 的账号/PATH 非版本缓存仅接受匹配本包的 engine-probe。适配后的内容记录在安装回执中，其余上游文件保留原文。当前安装验证针对本机 Linux；Windows launcher 尚未做同等适配与验收。
- 只安装项目 skill，不安装 hook、plugin 或浏览器扩展。运行 launcher 时可能下载 engine 0.1.14 并校验上游 SHA256；首次运行及网络失败如实报告。文件指纹与下载校验不等于安全审计。
- 与项目 frontend-design / design-taste-frontend 作为设计总控互斥；保留全局 Playwright CLI 等工具。已有同职责技能时先确定替换范围并归档，安装器拒绝直接覆盖。
- 项目品牌、产品事实、设计 token 和本地约定优先；用本机 Playwright CLI 验收。上游 Browser skill 专属调用需适配到实际工具；缺少工具报告降级。上游评审中的子智能体授权沿用当前宿主与会话合同，不照搬其他宿主的权限说明。

## 安装与核验

未来 AI 的调用入口是 `scripts/install_impeccable.py`。它是单模块复制器，不解析依赖、不自动升级、不注册全局命令。源码 checkout 放任务临时目录（例：`~/tmp/<任务>/impeccable`），先从上游取上述 commit；安装器从该 commit 的 Git 对象导出，因此不采用工作树里的本地改动。

```bash
python3 ~/.claude/skills/share-project-provision/scripts/install_impeccable.py --source <checkout> --project <项目绝对路径>
python3 ~/.claude/skills/share-project-provision/scripts/install_impeccable.py --source <checkout> --project <项目绝对路径> --apply
python3 ~/.claude/skills/share-project-provision/scripts/install_impeccable.py --project <项目绝对路径> --verify
```

默认预览不写文件；`--apply` 表示执行已授权安装，不能替代用户授权。stdout 为 JSON，错误写 stderr；退出码 0 成功、1 安装/核验失败、2 参数错误。依赖 Python 3.10+ 与 Git。`--help` 有示例。源码获取失败不无限重试。

写入：项目 `.claude/skills/impeccable/`、`.agents/skills/impeccable/` 及 `.agents/impeccable-install.json`。两端使用各自上游分发，配方只有一个；不写旧 `.codex/skills/`，不改 settings / AGENTS / hooks / 正文。回执包括源 commit、配方版本、engine 版本、文件 SHA256；回执与 skill 文本随项目版本管理。安装锁与 staging 为临时运行态；中断残留需核查后清理。

安装锁只协调本安装器，不保证抵御外部手工并发修改。父路径软链或目标目录已存在时拒绝。失败回滚撤销本次未完成安装，可能留下无害的空父目录。核验检查缺失、修改、额外文件与软链；不执行安装包。哈希来自可编辑回执，证明内容一致，不能证明来源可信或宿主已经加载。

## 使用验收与退出

1. 在目标项目验证 Claude 与 Codex 的技能选择器确实出现 Impeccable；按各宿主实际行为 reload/restart 后再查。仅在安装目录存在不能报可用。
2. 在任务临时项目运行一次 launcher `--help`、`context` 和有已知正负例的 `detect --json`，记录实际 engine 版本、退出码和联网/降级情况；不对现有项目自动运行 init/document/doctor 写入。
3. 选择一个真实页面，比较当前方案与该包的任务可完成性、视觉质量、响应式问题及耗时；两个真实任务无收益时不晋级为默认包。安装验证不冒充设计效果验证。
4. 升级先修改并评审安装器的 COMMIT、RECIPE、skill/engine 版本；核对两端分发及 LICENSE/NOTICE.md 路径仍存在，launcher 适配仍成立。入口、适配合同或安装布局变化也递增 RECIPE。再核验项目本地内容、归档旧 skill 目录及回执后安装新配方；归档路径不能处于 `.claude/skills` / `.agents/skills` 等发现根内，避免旧技能继续曝光。
5. 卸载时把上述两个目录及回执移到项目 `_legacy/` 并写恢复说明；保留 PRODUCT.md、DESIGN.md、代码和用户材料。账号级 engine 缓存有其他消费者时不删除。

本机 smoke 测试见 `tests/test_install_impeccable.py`。许可文件随安装复制。
