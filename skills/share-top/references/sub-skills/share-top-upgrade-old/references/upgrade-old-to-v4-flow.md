# Old TOP -> v4 Upgrade Flow

> Legacy reference only. Current v4 truth is `share-top/SKILL.md`,
> `references/canonical-six-columns.md`, and the per-column references.

## Goal

Convert old TOP / five-in-one / custom project memory into current v4 without
letting old rules become active rules again.

Current v4 truth sources:

| Area | Current truth |
|---|---|
| current state | `_wiki-methodology/_top/_task_plan.md` |
| code map | root `_codemap.md` |
| code/tool registry | `_meta/_registry.yml` |
| data/file registry | `_meta/_data_registry.yml` |
| wiki knowledge | `_wiki-methodology/_wiki/` |
| tests/evidence | `_wiki-methodology/_tests/` + project tests |
| whole picture | `_whole_picture/`, only after user asks for webpage/HTML |

Old files such as `TOP.md`, old `wiki-methodology/`, `_codemap_v25.md`,
`_manifest.yml`, and five-in-one docs are upgrade inputs, not current truth.

## Safety Rules

- Default action is read-only audit.
- Do not move, delete, rename, or rewrite old project files without explicit user confirmation.
- Do not run destructive git commands such as `git reset --hard`.
- Do not write current state into codemap, manifest, handoff, or roadmap.
- If rollback is needed, prefer `git revert <commit>` or ask the user.
- Use old scripts only as helpers after reading their output; never treat helper output as permission to move files.

## Upgrade Stages

### 1. Audit

Run:

```bash
python3 ~/.claude/skills/share-top/scripts/topic-brief.py <project>
python3 ~/.claude/skills/share-top/scripts/topic-doctor.py <project>
bash ~/.claude/skills/share-top/scripts/v4-cleanup.sh <project>
```

Report:

- detected profile and legacy signals
- current truth candidates
- root clutter / tmp / legacy risks
- old files that need migration
- files that must not be moved without user confirmation

### 2. Plan

Create a short migration plan before editing:

```text
1. baseline commit / snapshot status
2. v4 skeleton to create or update
3. old paths to map into v4 truth sources
4. files proposed for _legacy / _tmp / _sandbox
5. tests and lint commands
6. user decisions required
```

If the project is not clean, stop and ask whether to commit, stash, or continue
without migration.

### 3. Skeleton

After user confirmation, initialize or repair the v4 skeleton:

```bash
bash ~/.claude/skills/share-top/scripts/init-research.sh <project>
```

Then verify:

```bash
python3 ~/.claude/skills/share-top/scripts/topic-doctor.py <project>
python3 ~/.claude/skills/share-top/scripts/top-lint.py <project>
```

### 4. Map Old Content

Map old content into current owners:

| Old content | New owner |
|---|---|
| old current status / next action | `_wiki-methodology/_top/_task_plan.md` |
| old roadmap | `_wiki-methodology/_top/_roadmap.md` |
| old findings / decisions | `_wiki-methodology/_top/_findings/` / `_decisions/` |
| old code map / module inventory | root `_codemap.md` + `_meta/_registry.yml` |
| old data/file manifest | `_meta/_data_registry.yml` |
| stable method notes | `_wiki-methodology/_wiki/` |

Use `references/migration-tools/rename_wiki_to_underscore.py` only for the
wiki-name migration case, and run it with dry-run or sandbox first:

```bash
python3 ~/.claude/skills/share-top/references/sub-skills/share-top-upgrade-old/references/migration-tools/rename_wiki_to_underscore.py \
  --root <sandbox-copy> --dry-run --mode B
```

### 5. File Lifecycle

For clutter and old assets:

- classify first: current / temp / generated / legacy / data / output
- register main data assets in `_meta/_data_registry.yml`
- put temporary work under `_tmp/` or `_sandbox/`
- put old user assets under `_legacy/<name>-<date>/` with README or tombstone
- ask before moving ambiguous, large, active, or user-created files

### 6. Verify

Run the strongest available checks:

```bash
python3 ~/.claude/skills/share-top/scripts/topic-doctor.py <project>
python3 ~/.claude/skills/share-top/scripts/top-status.py <project>
python3 ~/.claude/skills/share-top/scripts/top-lint.py <project>
```

Also run project tests if code or data paths changed.

### 7. Record

Write a concise finding:

```text
_wiki-methodology/_top/_findings/_<date>_v4-upgrade.md
```

Include:

- what changed
- what remains legacy
- tests run
- decisions the user made
- paths that must not be treated as current truth

## Known Boundary

This flow upgrades project memory architecture. It does not prove project code,
data, or papers are correct. That evidence must come from the project tests,
data checks, and user review.
