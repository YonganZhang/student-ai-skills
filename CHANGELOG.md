# 更新记录

## v1.0.0（2026-10-29）

首个公开版本。

- 收录 12 个技能：project-top（含 `plan` 与 `sixone-cli.py`）、content-pptx-gen、content-real-ppt、content-technical-roadmap、content-black-white-roadmap、dev-grill-to-spec、dev-code-review、dev-find-wheels、dev-agent-cli、frontend-design、design-taste-frontend、dev-project-provision（含模板与模块配方）。
- 随附 Superpowers 7.0.0（obra/superpowers，MIT）原样副本。
- 新增 `install.sh`：Claude Code / Codex 双端安装，复制或软链，按名选装，安装 `plan` 命令，Superpowers 官方插件优先、失败退回随附副本，支持 `--dry-run`、`--force`、`--help`。
- 公开前处理：本机路径改为 `~/.claude/skills/<技能>` 等可移植写法；删去私有项目、人员、内部看板与私有规则文件的引用；未收录技能统一标注“可选，本包未包含”。技能方法本身未改写。
