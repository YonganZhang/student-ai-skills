---
name: dev-grill-to-spec
description: "盘问我/grill me、追问需求、挑战方案与澄清决策；需要时整理 spec/PRD，普通明确小改直接执行。"
---

# Grill To Spec

Use this skill when the user wants an idea interrogated before implementation, or when a plan should become a durable spec. The goal is to turn vague intent into shared decisions, not to slow down obvious work.

## Trigger Boundary

Use this skill for focused questioning of a requirement, plan, research idea or decision. A spec/PRD is optional. Typical requests:

- `grill me` / `盘问我` / `拷问我` / `挑战这个方案` / `帮我问清楚` about an idea, requirement, research plan or decision
- `先问清楚再做`
- `写 spec`
- `写 PRD`
- `把这个流程梳理成需求文档`
- `我们先定清楚需求/流程/边界`

Do not use it for a straightforward code change where the user already supplied clear acceptance criteria. If the request is small and reversible, implement normally.

If the user only wants a plan, decision, or idea stress-tested ("grill me") and no spec/PRD document is expected, run the same questioning loop but stop at shared understanding: summarize the resolved decisions and open risks, and skip the spec and vertical slices.

## Operating Mode

Say briefly that grill-to-spec mode is active.

First inspect what can be known without asking:

1. Read the project entry documents if they exist: `_wiki-methodology/_top/_task_plan.md`, `_codemap.md`, `README*`, `AGENTS.md` / `CLAUDE.md`, `GLOSSARY.md` / `GLOSSARY-MAP.md` (older repos: `CONTEXT.md` / `CONTEXT-MAP.md`), ADRs, or feature docs near the target area.
2. Search the codebase for existing domain terms, UI flows, APIs, tests, and previous versions that relate to the user's idea.
3. If the answer can be found in files or code, use that evidence instead of asking the user.
4. Ask only decisions whose prerequisites are already settled. Default to one question per turn; when 2–3 small questions do not depend on each other or on anything still open, you may ask them together, each with its own recommended answer.

For each question:

- State the decision being resolved.
- Give your recommended answer and why.
- Offer the smallest useful alternatives when the trade-off is real.
- Wait for the user's answer before moving to the next branch.

## Question Ladder

Start with the intended outcome, current evidence, assumptions, alternatives, constraints and success criteria. For research or general decisions, ask about the question, evidence and validation; do not force UI/API questions onto those tasks. For software features, use the following design tree, skipping anything already clear:

1. User outcome: who uses this, what job they are trying to finish, and what success looks like.
2. Current baseline: what exists today, what old behavior should be preserved, and what is broken or too expensive.
3. Happy path: the exact step-by-step user flow.
4. State and data: what is created, edited, previewed, saved, discarded, versioned, or compared.
5. UI surface: where it appears, what controls exist, and what feedback is shown during async work.
6. System contracts: model/tool calls, backend APIs, events, queues, persistence, and failure states.
7. Edge cases: cancel, retry, stale preview, conflicting edits, permissions, empty input, partial success.
8. Acceptance: concrete checks a reviewer or test can use to say the feature works.
9. Out of scope: tempting adjacent work that must not enter the first build.
10. Rollout: MVP slice, later slice, and any hard-to-reverse decision that may need an ADR.

## Documentation Output

When enough answers exist, finish the requested discussion. If the user already requested a spec/PRD, write it without asking again. If no document was requested, summarize the decisions; offer a document only when it would resolve a concrete remaining need. Write authorized documents to the project documentation owner:

- Prefer project TOP/wiki locations when present: `_wiki-methodology/_wiki/`, `_wiki-methodology/_top/`, or the project's established spec folder.
- Use `docs/` only when the project does not use TOP/wiki.
- If the user only wants a conversation draft, present the spec inline and do not write a file.

Before writing a file, read `references/spec-template.md`. Use the template as a shape, not as filler; omit sections that would be empty.

For complex features with multiple independent requirements or interacting failure states, check [requirements quality](references/absorbed/spec-kit-requirements-quality.md) before handing the spec to implementation; skip this extra pass for clear, small changes.

## Task Breakdown

After the spec is accepted, offer a vertical-slice task plan if the user wants implementation planning. Slices should be independently reviewable:

- Each slice should deliver a thin end-to-end behavior, not a horizontal layer.
- Mark slices `AFK` when an agent can implement them without more user decisions.
- Mark slices `HITL` when they require product/design/architecture approval.
- Show dependencies (which slices block which) and acceptance criteria before implementation starts.
- Size each slice to fit one fresh agent context; put any prefactoring slice first.
- A wide mechanical refactor (rename or retype used everywhere) is the exception: sequence it as expand, migrate in batches, then contract, instead of forcing one vertical slice.

## Prototype Option

When the user wants to sanity-check a state model, data flow, or UI direction before committing, read `references/absorbed/mattpocock-real-engineering.md` and propose a throwaway prototype only if it answers a concrete unresolved question. Keep the prototype outside durable truth until the verdict is captured.

## Questionnaire Exit

When a decision depends on knowledge the user does not hold (a supervisor, collaborator, client, or another team owns it), offer to turn those open questions into a questionnaire for that person instead of guessing. Read `references/absorbed/mattpocock-questionnaire.md` first.

## Source Notes

This skill semantically absorbs the public `grill-me` / `grilling`, `grill-with-docs`, `to-spec`, `to-tickets`, `to-questionnaire`, and selected real-engineering workflow checks into this skill package's style. Read `references/source-map.md` only when you need provenance or want to compare the upstream concepts.

## Exit Rule

At the end of the turn, state whether the mode is still active:

- `继续盘问`: unresolved decisions remain and the next question is pending.
- `已进入 spec`: enough decisions exist and a spec draft/file was produced.
- `已退出`: the user redirected to normal implementation or conversation.
