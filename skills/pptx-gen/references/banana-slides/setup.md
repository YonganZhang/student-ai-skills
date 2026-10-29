# Setup

## Source Location

This installation expects the audited upstream clones inside the current project (or set `BANANA_SLIDES_PROJECT_ROOT`):

- Banana Slides: `_external/banana-slides`
- CLI-Anything reference: `_external/CLI-Anything`

The locked Banana commit from the audit is `9056adb7c006e833e11198e1608f0b2b34113eca`.

## Backend

Banana Slides is a backend-driven app. The CLI talks to the Flask API, defaulting to:

- Backend: `http://localhost:5011`
- Frontend: `http://localhost:3011`

Health check:

```bash
curl -fsS --max-time 10 http://localhost:5011/health
```

Or use the bundled helper:

```bash
~/.claude/skills/pptx-gen/references/banana-slides/scripts/health_check.sh
```

If the backend is not running, start it from the Banana repo using the upstream docs. Prefer Docker or the repo's documented local backend flow. Do not invent a second backend.

## CLI Wrapper

Use:

```bash
~/.claude/skills/pptx-gen/references/banana-slides/scripts/banana_cli_wrapper.sh --help
```

The wrapper locates the project clone and injects the temporary dependency directory used during audit:

- `_tmp/banana-cli-deps`
- `_external/banana-slides`

If dependencies are missing, run the project audit setup again or install `typer`, `rich`, and `tomli` into an isolated user/project prefix. Do not use `sudo`.

```bash
/usr/bin/python3 -m pip install --target _tmp/banana-cli-deps typer rich tomli
```

After wrapper changes, run:

```bash
~/.claude/skills/pptx-gen/references/banana-slides/scripts/smoke_test.sh
```

## CLI Config

Config priority:

1. CLI flags
2. `BANANA_CLI_*` environment variables
3. `~/.config/banana-slides/cli.toml`
4. defaults

Important variables:

```bash
BANANA_CLI_BASE_URL=http://localhost:5011
BANANA_CLI_ACCESS_CODE=<optional access code>
BANANA_CLI_POLL_INTERVAL=3
BANANA_CLI_REQUEST_TIMEOUT=60
BANANA_CLI_CONTINUE_ON_ERROR=true
```

## Provider Config

The backend, not the CLI, owns AI provider keys. Common backend environment keys include:

- `AI_PROVIDER_FORMAT=gemini|openai|vertex|lazyllm`
- `GOOGLE_API_KEY`, `GOOGLE_API_BASE`
- `OPENAI_API_KEY`, `OPENAI_API_BASE`
- `TEXT_MODEL`, `IMAGE_MODEL`, `IMAGE_CAPTION_MODEL`
- `TEXT_API_KEY`, `IMAGE_API_KEY`, `IMAGE_CAPTION_API_KEY`

Do not write secrets into the skill, reports, or conversation. Ask the user to configure the backend environment or settings UI when needed.

## Cost Boundary

Real slide image generation can call paid image models. Run help, health, config, loader, and backend-down tests freely. Run real image generation only after the user accepts API cost and output scope.
