# COL5 File/Data Lifecycle Closure

COL5 is not only “where files go”; it is how a file becomes explainable.

## Classify Before Moving

Before writing or moving a file, classify it:

- main code/tool
- main data asset
- temporary experiment
- intermediate/download
- output/figure
- test evidence
- old user asset
- machine artifact
- unknown

## Landing

| Class | Landing |
|---|---|
| main code/tool | `_code/` or `_pipelines/` + `_meta/_registry.yml` |
| main data asset | `_data/` + `_meta/_data_registry.yml` |
| temporary experiment | `_sandbox/` |
| intermediate/download | `_tmp/` |
| output/figure | `_outputs/` or `_figures/` |
| reusable test evidence | `_wiki-methodology/_tests/_artifacts/` or project test artifact dir |
| old user asset | `_legacy/<YYYY-MM-DD>_<name>/README.md` |
| machine artifact | delete only if clearly generated (`__pycache__`, `*.pyc`, build cache) |

## Closure

Root clutter warning is not permission to move files blindly.

To close a COL5 issue:

1. classify the file
2. register if it is a main asset
3. move or keep with a reason
4. add tombstone/README for archive
5. if a data registry is enabled, rerun `sixone-cli.py doctor` (registered paths must exist)

## Data Registry Minimum

For important data assets, prefer:

```yaml
id:
path:
source:
provenance:
size_bytes:
manifest_sha256:
check_command:
used_by:
```

Hash proves local drift status, not external truth.
