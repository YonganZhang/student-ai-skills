# Finding Lifecycle

Findings and external reviews are evidence, not current state. Only current accepted work enters `_task_plan.md`.

## Status

| Status | Meaning |
|---|---|
| `open` | not triaged yet |
| `accepted` | should be acted on |
| `fixed` | resolved with evidence |
| `superseded` | replaced by newer finding/decision |
| `rejected` | reviewed and intentionally not adopted |
| `archived` | historical only |

## Recommended Metadata

```yaml
status: open
severity: critical|major|minor|note
owner_col: COL1|COL2|COL3|COL4|COL5|COL6
source: user|self|subagent|external|test|runtime
created_at: YYYY-MM-DD
closed_at:
closure_evidence:
```

## Workflow

1. Record the finding in `_wiki-methodology/_top/_findings/`.
2. Set status and owner column.
3. If accepted and current, summarize the action in `_task_plan.md`.
4. If fixed, rejected, or superseded, write closure evidence.
5. Do not copy full external reviews into task_plan.

## Digest Rule

When findings/reviews are numerous, create a digest that lists only still-active accepted/open items. Keep original reviews as evidence.

## Doctor

Optional (legacy projects that still keep `_findings/` / `_external_reviews/`; new projects put reusable lessons in `_decisions/`). Not a closeout requirement:

```bash
python3 ~/.claude/skills/share-top/scripts/finding-doctor.py [<project>]
```

It checks missing lifecycle status, active findings without owner, closed findings/reviews without closure evidence, pending review adoption, and active lists that need a digest.
