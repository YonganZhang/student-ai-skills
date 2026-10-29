# SSOT Link Contract

## Core

One fact type has one owner. Other columns may link or derive; they must not copy body text.

## Owners

| Fact | Owner |
|---|---|
| current state / next action / blocker | `_wiki-methodology/_top/_task_plan.md` |
| code / tool / process entry | `_codemap.md` + `_meta/_registry.yml` |
| data / model / external asset | `_meta/_data_registry.yml` |
| test gate / coverage / evidence | `_wiki-methodology/_tests/` + project tests |
| stable method / formula / entity | `_wiki-methodology/_wiki/` |
| file lifecycle / naming / archive | `_meta/_naming.md` + `_sandbox/` + `_tmp/` + `_legacy/` |
| whole picture | `_whole_picture/` derived view only |

## Refs

Use short refs to connect owners:

```text
code:<native-key>
data:<native-key>
test:<native-key>
wiki:<slug>
finding:<native-key>
decision:<native-key>
pipeline:<native-key>
```

Rules:

- Ref targets are declared once by their owner file.
- The native key comes from the owner file; do not create a second ID registry.
- Refs are links, not summaries. Do not copy current state, method text, test evidence, or data descriptions across columns.
- Reverse refs are derived by scanning owner files; do not maintain a hand-written reverse-ref table.
- `deprecated` / `archived` resources need `superseded_by` or `retire_reason`.
- Generated indexes, reports, and whole-picture pages must say they are derived and are lower authority than owners.

## Validation

```bash
python3 ~/.claude/skills/share-top/scripts/sixone-cli.py doctor <project>   # typed-ref 检查默认开启
```

`--links` checks mechanical facts only: duplicate declared refs, dangling refs, and retired refs without an exit path. It does not prove semantic freshness.
