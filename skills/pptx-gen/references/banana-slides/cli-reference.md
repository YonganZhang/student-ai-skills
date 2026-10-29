# CLI Reference

## Global Options

```bash
banana-cli [global-options] <group> <command> [options]
```

Useful global options:

- `--base-url`: backend URL, default `http://localhost:5011`
- `--access-code`: sent as `X-Access-Code` for API routes
- `--poll-interval`: task polling seconds
- `--request-timeout`: request timeout seconds
- `--config`: TOML config path
- `--json`: JSON output where supported
- `--verbose`: verbose output

## Command Groups

Registered groups:

- `projects`: create/list/get/update/delete/use/unuse
- `workflows`: outline/descriptions/images/full
- `exports`: pptx/pdf/images/editable-pptx
- `pages`: page create/edit/generation/image versions
- `materials`: upload and manage materials
- `refs`: upload and parse reference files
- `templates`: template operations
- `settings`: backend settings
- `tasks`: wait/query tasks
- `renovation`: renovate existing PPT/PDF
- `styles`: style extraction
- `files`: file transfer
- `run`: batch jobs and monitor

## Batch Job Schema

`run jobs` accepts JSONL or CSV.

Core fields:

- `job_id`
- `job_type`: `full_generation` or `export_only`
- `creation_type`: `idea`, `outline`, or `descriptions`
- `idea_prompt`, `outline_text`, `description_text`
- `project_id` for export-only jobs
- `template_image_path`, `template_style`, `extra_requirements`
- `language`: `zh`, `en`, `ja`, `auto`
- `reference_files`, `material_files`
- `export.formats`: `pptx`, `pdf`, `images`, `editable_pptx`
- `policy.continue_on_error`
- `policy.timeout_sec`

Upload paths must be absolute and must exist.

## Error Contract

CLI command errors are emitted to stderr:

```json
{"success":false,"error":{"code":"HTTP_ERROR","message":"...","details":{}}}
```

Known codes include:

- `CONFIG_ERROR`
- `INPUT_ERROR`
- `HTTP_ERROR`
- `TASK_FAILED`
- `TASK_TIMEOUT`
- `IO_ERROR`

`run jobs` exits with code `2` when one or more jobs fail. In that case read `report.json`.

## Stdout Warning

Most simple commands print JSON to stdout. `run jobs` can print progress and success/failure lines to stdout even with `--json`. For automation, use `report.json` and `state.json`.
