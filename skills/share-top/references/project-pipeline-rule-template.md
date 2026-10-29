# Project Pipeline Rule Template

Use this in the project-level `AGENTS.md` (the single instruction file shared by Claude and Codex) or a TOP note when the project has durable workflows such as Playwright e2e, render jobs, data pipelines, video recording, model evaluation, or deployment checks.

Global rules should not know the project's pipeline names. The project should declare them.

## Minimal Project Rule

```markdown
## Pipelines

Pipeline registry:
- Primary owner: `_wiki-methodology/_tests/pipelines.md`
- Runtime facts: `_fs/manifest.yml` `pipelines:` and `runtime_facts:`
- Code route: `_codemap.md` Pipeline section

When editing files under `<pipeline paths>`, update the affected pipeline row, test gate, and codemap route before reporting done.
```

## Registry Row Shape

```markdown
| Pipeline | Purpose | Entry | Trigger Paths | Gate | Evidence Owner | Last Verified |
|---|---|---|---|---|---|---|
| preview-render | Generate and validate 3D preview | `scripts/...` | `viewer/**`, `render/**` | `npm run test:preview` | `_wiki-methodology/_tests/preview-render.md` | YYYY-MM-DD |
```

## Design Rule

- Keep the list short and project-specific.
- Put exact paths and commands in the project, not in global rules.
- If a pipeline is changed, update COL3 test evidence and the COL4 route together.
- If the AI cannot identify which pipeline a changed file belongs to, it should check the registry first and ask only if the registry is missing or contradictory.
- Hooks are optional. Prefer a project-level lint that compares changed paths with the pipeline registry before restoring global hooks.
