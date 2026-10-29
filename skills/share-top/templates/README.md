# share-top Templates

Templates are starting points, not proof that automation exists.

| Template | Use For | Generates | Does Not Generate | Verify |
|---|---|---|---|---|
| `methodology/method.md` | 方法介绍/设计/优化任务按需启用 | 一页方法合同起点；图模板/工具由content-technical-roadmap提供 | 进度副本、默认已实现/已验证结论 | 方法来源/单位/接口核对、图预览及来源漂移检查 |
| `minimal/` | every new project (default of `scripts/init-research.sh`) | `AGENTS.md`, `_task_plan.md`, `_logs/` | optional modules | `sixone-cli.py plan validate` |
| `v4-architecture/` | per-kind default dirs (`init-research.sh` copies only `<dir>/_readme.md`: research `_code _data _outputs _figures _paper _refs _sandbox _tmp _legacy _meta`, dev `_meta _sandbox _tmp _legacy`); source for optional modules (`--with codemap,registry,…`); `--with full` copies all of it for legacy compatibility | five-question dir READMEs, codemap, `_wiki-methodology/`(incl. `_tests/_gates.yml`), `_meta/` | old project migration | `sixone-cli.py doctor` |
| `dir-readme.md` | README for any top-level dir that is not `_`-prefixed (dev module dirs like `frontend/`, `backend/`) | five questions: what goes in, what does not, entry, non-obvious file roles, where change reasons live | change history (Git) or call graph (CodeGraph) | `sixone-cli.py track` → `structure.unarchived` |
| `registry-architecture/` | pipeline-heavy or tool-heavy projects | registry/query/reachability helpers | replacement for codemap | registry tests/path checks |
| `lint-armor/` | complex software guardrails | lint/register helper templates | default installed hooks | py_compile + project lint |
| `gitignore/research.gitignore`、`gitignore/dev.gitignore` | `.gitignore` baseline by project kind (`init-research.sh --kind research|dev`; written when absent, otherwise missing lines appended in a `# >>> top baseline` block) | ignore rules for caches, credentials, `_tmp/`, test artifacts, bulk/binary outputs | per-project data decisions (use `sixone-cli.py track`) | `git check-ignore -v <path>` |
| `codebook/_node_schema.md` | **retired 2026-09-24** — kept only to read old `_codebook/` nodes | nothing (`init-research.sh --with codebook` no longer creates `_codebook/`; `deposit` no longer stamps) | — | — |

Before copying a template:

1. confirm project profile
2. do not overwrite user files
3. do not claim helper automation unless scripts/hooks/tests exist
4. run `sixone-cli.py plan validate` (and `doctor` if registries were added) after copying
- `capabilities/_capabilities.yml` — COL5 能力清单模板（登记「能产出什么」，不是装机清单）
