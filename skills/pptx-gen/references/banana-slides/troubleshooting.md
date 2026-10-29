# Troubleshooting

## Backend Down

Symptoms:

- `HTTP_ERROR`
- connection refused
- health check fails

Check:

```bash
curl -fsS --max-time 10 "$BANANA_CLI_BASE_URL/health"
```

If it fails, start the Banana backend before running generation. Do not treat backend-down as success.

## Missing Provider Key

Symptoms:

- backend returns provider config errors
- `GOOGLE_API_KEY` / `OPENAI_API_KEY` required

Fix in backend `.env` or settings UI. Do not paste keys into reports or skill files.

## No Generated Images Found

This usually means image generation has not completed or failed. Check:

- `state.json`
- `report.json`
- `GET /api/projects/{project_id}/tasks/{task_id}`
- backend logs

For image generation, Banana requires either a template image, project/page style text, or page template binding.

## Mixed Stdout

If parsing `run jobs --json` fails, read `report.json`. `run jobs` progress lines may be mixed into stdout.

## Access Code Leak Risk

HTTP transport errors can include CLI config details. If logging stderr, redact:

- `access_code`
- `BANANA_CLI_ACCESS_CODE`
- API keys

## Real API Tests

Real image generation tests are cost-bearing. Keep no-key smoke tests separate from real provider tests.
