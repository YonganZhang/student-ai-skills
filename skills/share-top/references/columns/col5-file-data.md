# COL5 · File And Data Lifecycle

## Owns

Data assets, **capability inventory**, naming, temporary work, sandbox experiments, outputs, archives, tombstones.

能力清单登记「能按需产出主线所需资源的东西」（模拟器、生成器、可重建环境、配额…）。
资产是名词、能力是动词，两者不可互相替代。收录判据见 `../capability-inventory.md`。

## Anti-owner

- code function registry
- unclassified root clutter
- 把通用工具链/装机清单塞进能力清单
- direct deletion of user assets

## Paths

- `_meta/_data_registry.yml`
- `_meta/_capabilities.yml`
- `_meta/_naming.md`
- `_data/`
- `_outputs/`
- `_figures/`
- `_refs/`
- `_sandbox/`
- `_tmp/`
- `_legacy/`

## Update When

- data asset changes
- temporary or output file is created
- old file is archived
- project has root clutter

## Verify

- data paths exist
- archive has README/tombstone
- root clutter either moved, registered, or known
