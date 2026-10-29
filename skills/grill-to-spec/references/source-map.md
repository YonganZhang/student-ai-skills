<!--
来源: mattpocock/skills
吸收时间: 2026-06-14；2026-09-23 按 c55ee46073ed 对齐上游改名后的路径并选择性补充；2026-10-07 按 4588b32 复核并同步
吸收者: 本技能包维护者
方式: 语义吸收；没有机械复制完整上游文本。版本记录见 skill 根目录 UPSTREAM.json。
-->

# Source Map

This local skill combines several upstream ideas from Matt Pocock's public skills repository:

- `skills/productivity/grill-me/SKILL.md` and its primitive `skills/productivity/grilling/SKILL.md`: relentless interview with a recommended answer per question, and fact-finding in the codebase instead of asking. Upstream now asks the whole frontier of settled-prerequisite questions in numbered rounds; locally we default to one question per turn and only batch 2–3 mutually independent small questions.
- `skills/engineering/grill-with-docs/SKILL.md`: challenge vague language against project docs, resolve terminology, and capture durable decisions in docs. Upstream renamed its glossary convention from `CONTEXT.md` / `CONTEXT-MAP.md` to `GLOSSARY.md` / `GLOSSARY-MAP.md` (2026-09); we read both.
- `skills/productivity/to-questionnaire/SKILL.md`: when the user cannot answer a decision alone, interview only about the send (recipient, what to get back) and write a questionnaire aimed at the knowledge gap → `absorbed/mattpocock-questionnaire.md`.
- `skills/engineering/to-spec/SKILL.md` (formerly `to-prd`, unified 2026-07-08): synthesize current conversation and codebase understanding into a spec with problem, solution, user stories, implementation decisions, testing decisions, out-of-scope, and notes; agree on the highest existing test seam, with as few seams as possible.
- `skills/engineering/to-tickets/SKILL.md` (formerly `to-issues`): break an accepted plan into tracer-bullet vertical slices, each declaring its blocking edges and sized for one fresh context; prefactor first, and sequence wide mechanical refactors as expand–contract instead of forcing a vertical slice.
- `skills/engineering/prototype/SKILL.md`: use prototypes to answer a concrete design question. Upstream now keeps (captures) the prototype; locally we still delete it or absorb the verdict into the spec/TOP.
- `skills/engineering/tdd/SKILL.md`: vertical-slice red → green TDD at pre-agreed seams, tautological-test anti-pattern, refactoring moved to review.

Related upstream absorbed elsewhere:

- `skills/productivity/handoff/SKILL.md` → `share-top/references/absorbed/mattpocock-handoff.md`.
- `skills/engineering/diagnosing-bugs/SKILL.md` → moved out of this skill 2026-10-07 (local adaptation not included in this package; read upstream https://github.com/mattpocock/skills ).
- `skills/engineering/codebase-design/` and `improve-codebase-architecture/SKILL.md` → moved out 2026-10-07 (local adaptation not included in this package; read upstream).
- `skills/engineering/code-review/SKILL.md` → `share-code-review/references/absorbed/mattpocock-two-axis-review.md`.
- `skills/productivity/writing-for-agents/SKILL.md` and `skills/engineering/retro/SKILL.md` → `share-skill-creator`.

Local adaptations:

- Uses project-top (TOP/wiki) owners before generic `docs/`.
- Does not publish to an issue tracker by default; upstream `to-spec` is a no-interview synthesis step, while this skill keeps the interview and the spec in one flow.
- Keeps the interview interactive; spec writing starts only when enough decisions exist or the user asks for a draft.
- Keeps implementation out of scope until the user accepts the spec or explicitly redirects.

Detailed absorbed checkpoints: `absorbed/mattpocock-real-engineering.md`.
