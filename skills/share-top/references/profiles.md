# TOP Profiles

Profiles prevent one physical layout from being forced onto every project.

## Current Profiles

| Profile | Use For | Required Strength |
|---|---|---|
| `v4-full` | normal full TOP project | all six columns active |
| `active-software` | product / app / service code | codemap, registry, tests, task_plan |
| `active-research` | paper / experiment / data project | task_plan, data registry, tests/repro gates |
| `active-complex-software` | multi-runtime app with plugins, MCP, live gates, experts, scenarios | test gate map, adapters, finding lifecycle, injection lint |
| `mini` | small project with one lightweight TOP | one current entry and file lifecycle rules |
| `public-contrib` | small public docs/contrib repo | README + minimal project card; no forced full v4 |
| `admin` | teaching/admin/material bucket | status, owner, material location, no full registry requirement |
| `collection` | workspace of many repos/materials | collection map, not full six-column project |
| `upstream-wrapper` | local wrapper around upstream repo | wrapper codemap and sync gap; do not rewrite upstream |
| `archive` | frozen project/paper/archive | reproducibility capsule and tombstones; no active queue |
| `legacy-compatible` | old TOP path still exists | read only; upgrade via sub-skill |

## Complex Software Signals

Treat a project as `active-complex-software` or add capability flags when several of these exist:

- frontend and backend/runtime code
- plugin tools, scenarios, contract tests, expert/persona registry
- MCP/server/runtime smoke tests
- `_meta/_registry.yml` with wrapper schemas or adapters
- `_meta/_data_registry.yml`
- canonical test script such as `scripts/test-*.sh`
- large tests tree or live/release gate

## Rule

Profile controls strictness. Do not make small projects satisfy complex-project rules.
