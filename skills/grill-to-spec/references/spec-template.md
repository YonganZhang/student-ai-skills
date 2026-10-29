<!--
Purpose: local spec template for grill-to-spec.
Use after enough user decisions have been collected. Do not fill sections with boilerplate.
-->

# [Feature / Flow Name] Spec

## Problem

State the user-visible problem in plain language. Mention the current baseline or old behavior if it matters.

## Goal

Describe the target outcome from the user's perspective.

## Non-Goals

List work that is explicitly out of scope for this version.

## Users And Context

Name the user roles, entry points, and project/domain terms. Use the project's existing glossary or docs when present.

## Proposed Flow

Describe the happy path as numbered user steps. Include UI states, async progress, preview behavior, save/discard behavior, and versioning when relevant.

## Decisions

Record settled product and technical decisions. For each decision, include:

- Decision
- Reason
- Alternatives rejected, if meaningful

## Contracts

Document stable interfaces without overfitting to temporary file paths:

- UI events and state transitions
- API/tool/model calls
- Data created or mutated
- Persistence/versioning rules
- Error and retry behavior

## Acceptance Criteria

Use checkable statements:

- [ ] A user can ...
- [ ] When ..., the system ...
- [ ] Failure state ... is visible and recoverable

## Test Plan

Prefer external behavior tests over implementation-detail tests. Mention existing comparable tests if found. Name the test seams: prefer existing seams, test at the highest seam that covers the behavior, and keep the number of new seams as small as possible; confirm the seams with the user.

## Open Questions

Keep only questions that block or materially alter the implementation. Each question should have an owner or recommended default.

## Vertical Slices

Use after the spec is accepted.

| Slice | Type | Builds | Blocked By | Acceptance |
|---|---|---|---|---|
| 1 | AFK/HITL | Thin end-to-end behavior | None / Slice N | Checkable result |
