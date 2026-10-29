# COL2 · Top

## Owns

Required: current plan + logs. Optional: decisions (reusable reasons/lessons). Legacy projects may still have roadmap, findings, review digests; they stay readable but are not created by default.

## Anti-owner

- code registry
- data registry
- long method explanations
- second current queue in roadmap/handoff

## Paths

- `_wiki-methodology/_top/_task_plan.md`
- `_wiki-methodology/_top/_logs/`
- `_wiki-methodology/_top/_findings/`
- `_wiki-methodology/_top/_decisions/`

## Update When

- current phase / next action / blocker changes
- new evidence or decision appears
- external review is triaged

## Verify

- `sixone-cli.py plan validate`（不变量 + 体积预算）
- 可选：`doctor --full` 的 state drift、`finding-doctor.py` 的 review 债务
