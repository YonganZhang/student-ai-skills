---
name: web-playwright
description: "Playwright CLI 网页操作、填表点击、E2E 验收、演示录像；只写代码、不操作浏览器时不触发。"
allowed-tools: Bash(playwright-cli:*) Bash(npx:*) Bash(npm:*)
---

# Playwright CLI

把它当浏览器操作工具，不把命令手册全部装入上下文。

## 默认循环

0. 先确认装了命令行工具：`playwright-cli --version`。没有就 `npm install -g @playwright/cli`（Microsoft 官方 npm 包，Apache-2.0，需要 Node.js 18+），首次打开会话时会按需下载 Chromium。
1. 打开会话用本技能的 `scripts/open_session.sh <会话名> [open 参数] <url>`（Claude Code 装在 `~/.claude/skills/playwright-cli/`，Codex 装在 `~/.agents/skills/playwright-cli/`），多步任务用命名会话；也可以直接 `playwright-cli -s=<会话名> open <url>`。
   - 环境里设了 `HTTPS_PROXY`/`ALL_PROXY` 时，脚本自动带上代理配置：Chromium 用不了代理 URL 里的账号密码，不带会报 `net::ERR_INVALID_AUTH_CREDENTIALS`。配置由 `scripts/proxy_config.py` 生成，可能含代理密码，只放在 `$XDG_RUNTIME_DIR`（没有时为 `~/.cache`）下 0600 文件，脚本只打印路径。没设代理时直接打开。
   - 有可用的 `systemd-run --user` 时（多数 Linux 桌面），脚本把浏览器放进独立的 systemd scope（内存上限 2G）：会话比发起它的命令活得久，不该挂在那条命令的进程组里，否则宿主按组清理时会被连带关掉。macOS 或没有 systemd 时直接运行。
   - 要换配置（如登录用的 secrets、隧道）就传 `--config=...`，脚本不再加代理配置。自己写的配置要指定 `browserName: chromium`：CLI ≥0.1.17 默认走 Chrome stable channel，机器上没装 Chrome 时 daemon 会退出。
   - Google Scholar 常拦截自动化浏览器和代理出口（curl 403，浏览器等到超时），在浏览器里查文献可改用 Semantic Scholar。
2. `snapshot` 获取当前可交互元素和 ref。
3. 用 ref 执行 click/fill/select 等动作，不凭视觉位置猜 selector。
4. 页面变化后重新 snapshot；只有视觉证据需要时才 screenshot。
5. 保存必要证据并关闭本次创建的 session。

## 按需读取

| 任务 | Reference |
|---|---|
| 命令、参数、定位方式和示例 | `references/cli-command-reference.md` |
| session/profile/storage | `references/session-management.md`, `references/storage-state.md` |
| 生成或维护 E2E 测试 | `references/test-generation.md`, `references/playwright-tests.md` |
| trace、视频、网络 mock | `references/tracing.md`, `references/video-recording.md`, `references/request-mocking.md` |
| 端到端工作流验收录像；给演示加组件可视化覆盖层 | `references/sub-skills/share-workflow-recording/REFERENCE.md` |
| B站/知乎/微博热搜/小红书/雪球/Twitter/Reddit/HackerNews 等站点只是要抓数据 | 如已安装带预置站点适配器的抓取 CLI（如第三方 `opencli`，本包未包含，需自行安装）可优先用它；本 skill 负责通用网页操作与验收，也是它跑不通时的回退 |

## 硬边界

- 默认用 Chromium；项目明确要求其他浏览器时再切换。
- 截图、trace、视频和测试证据放项目 `_tests/_artifacts/` 或既有测试目录。
- 登录态和凭证不写进脚本、日志、截图说明或回复。
- 目标站点需要 HTTP Basic Auth 时，不要把 `user:pass@host` 拼进 `goto`/`open` 的 URL 参数，哪怕参数写的是 shell 变量（如 `$USER:$PASS`）——shell 会在传给 playwright-cli 之前就展开成明文，而 playwright-cli 自己会把解析后的完整命令原样回显进 "Ran Playwright code" 日志，导致明文凭证进对话记录（2026-09-01 实测：`microsoft/playwright-cli`，`goto` 回显了解析后的 Basic Auth 明文）。改用只有本账号能读的配置文件（`browser.contextOptions.httpCredentials`，写法参考 `scripts/proxy_config.py`），用 `--config` 传入。`run-code` 里没有 `process`，读不到环境变量。
- 代用户登录时，账号密码从用户自己的密码管理器或凭证工具取（不让用户把明文贴进对话），写进 `$XDG_RUNTIME_DIR` 下 0600 配置的 `secrets`（键为 KEY 名），用 `fill <ref> <KEY名>` 填，回显里只出现名字。要长期保持登录就加 `--profile=~/.local/state/playwright-profiles/<站点>`（目录 0700）。
- 不能只因页面打开成功就宣称工作流通过；按用户路径完成动作并检查结果状态。
- 命令出错时退出码为 1（0.1.18 起）。脚本在 `set -e`/`pipefail` 下读输出时，先想好出错要怎么处理。

## 让用户看或接管

- 用户要看画面或亲手操作时，用有头模式打开（`open ... --headed`，需要图形桌面）。远程服务器或无桌面的 Linux 上看不到窗口：需要自行准备虚拟显示（如 Xvfb）加远程桌面/VNC，本包不提供这类服务。
- 也可以运行 `playwright-cli show`（`--annotate` 让用户在页面上画框批注）打开 Playwright 自带的 Dashboard。它会监听本机 TCP 端口，多人共用的机器上其他账号可能连得上，用完关闭。
- 需要人帮忙（验证码、登录、二次验证、人工确认）时：停下该会话的操作，回复里写明会话名和要做的事，请用户在浏览器窗口或 Dashboard 里完成。用户操作期间不再给该会话发命令：两边按键都打到当前焦点，会混进对方的输入框。用户说好了再 `snapshot` 重取 ref 继续。
- 要用户示范一段操作（例如第一次填报销表）时，用户开始前先 `recording-start`；用户完成后 `recording-stop`，拿到用户操作对应的 Playwright 代码（语义定位）。下次照着写成 `run-code` 一次跑完。
- 无头会话 1 小时没有命令会自动关闭（有头和 `attach` 的不会）。要留给用户稍后看的结果，`open` 时加 `--idle-timeout=<毫秒>`，并在回复里写明会话名。

## 省 token 与提速

- 动作命令（goto、click、fill）只回显约 100–250 token；整页 `snapshot` 才贵（实测政府、大学首页 5k–9k，GitHub 仓库页约 23k token）。大页面先 `find <文字>` 或 `snapshot <ref>`、`--depth=N`，只看需要的部分。
- 一张 1280×800 截图给模型看约 1.4k token；只在需要看图时用。
- 每条命令本身约 0.3–0.4 秒，时间主要花在每一步的模型往返。步骤和定位都确定的多步操作（填一组字段再提交）写成一段 `run-code` 一次跑完；终点动作（提交、支付、发送）仍单独一步并先确认。
