# CLI-Anything Compatibility

Use this only when the user asks to make Banana Slides conform to CLI-Anything-style harness expectations.

## Adopt Now

Reuse these standards immediately:

- Commands should be scriptable and fail loudly.
- Prefer machine-readable JSON artifacts.
- Test the installed command, not only imported functions.
- Use real backend checks for integration readiness.
- Keep a `TEST.md` or audit record with commands and results.

## Do Not Adopt Yet

Do not rewrite Banana into a separate `cli-anything-banana-slides` package by default. Banana already has `banana-cli` with Typer commands and REST API coverage. A second harness should be an adapter only after this skill is useful.

## Adapter Shape

If needed later:

- package name: `cli-anything-banana-slides`
- command wraps `banana_cli_wrapper.sh` or imports `cli.banana_cli`
- high-level commands call `run jobs`
- adapter reads report/state files, redacts secrets, and normalizes exit codes
- tests cover help, backend-down JSON, report parsing, state parsing, and one fake-backend export path

Keep upstream Banana source untouched unless a concrete bug requires a patch.
