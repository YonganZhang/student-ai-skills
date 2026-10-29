# 来源与取舍

做法综合自以下材料，均为意译改写，未照搬原文（访问日 2026-10-29；正式跟踪上游时再固定 commit）：

- Anthropic 博客《How the Claude Code team does code review》 https://claude.dev/blog/solving-code-review-at-anthropic/ ：提 PR 前实跑检查并让新上下文审查；问题分重要/小问题/已有问题，每条修掉或说明理由；按改动定风险档，AI 批准不算人工批准，批准绑定具体提交；PR 写测试、风险、回滚；审查轮次封顶、同类问题一次修全；重复问题沉淀为检查、规则或 REVIEW.md；发起人对改动负责到底。
- obra/superpowers（MIT）：
  - verification-before-completion https://github.com/obra/superpowers/blob/main/skills/verification-before-completion/SKILL.md ：没有本轮实跑证据不宣布完成。
  - requesting-code-review https://github.com/obra/superpowers/blob/main/skills/requesting-code-review/SKILL.md ：审查者拿精心准备的上下文而非会话历史，并对照需求。
  - receiving-code-review https://github.com/obra/superpowers/blob/main/skills/receiving-code-review/SKILL.md ：先核实再改，误报有理有据地回绝。
- 本机 `dev-code-review`：证据分级与报告格式；审他人改动仍走它。
- 2026-10-29 Codex 独立审查两轮（首轮重要 7 / 小问题 7，复核轮重要 3 / 小问题 1），均已修订并补测试。

本技能的取舍：

- 只覆盖作者侧。博客里的 CI 安全阻断、风险分类器、合并队列、灰度发布、事故转评测集属于团队平台，由项目维护，不塞进每次自检。
- 博客的低风险档可以不经人工；面向实习生时，低档仍要一位负责人或导师过目。
- 后续轮次核对修复 diff 与未决意见、而非全量重审，是本技能为控制成本的简化。
- `scope_check.py` 是提交范围内的启发式检查，不是完整的密钥扫描器；项目已有扫描器时优先用项目的。
