
# Banana Slides

Reference of `pptx-gen` (merged from the standalone `banana-slides` skill on 2026-09-24). Use it when the user wants Banana Slides / 蕉幻 specifically, or wants an agent-driven Banana backend workflow.

> **历史 ZZZ 直连路线已退役。** 用户提到旧直连方式时回到顶层 `pptx-gen`，按其当前宿主图片工具及用户点名的路线执行；旧 FAL-only 政策不覆盖父技能现行合同。历史归档未随本包发布。

## First Checks

1. Read `setup.md` when the backend, dependencies, or API/provider config may be missing.
2. Read `workflows.md` before generating slides or image exports.
3. Read `cli-reference.md` for lower-level project/page/export commands.
4. Read `troubleshooting.md` when health checks, jobs, downloads, or API calls fail.
5. Read `cli-anything-compat.md` only when adapting Banana to CLI-Anything-style harnesses.

## Operating Rules

- Prefer the wrapper: `scripts/banana_cli_wrapper.sh`.
- User asks for 智增增 / zzz / NanoBanana2 direct API / 2K-only route → tell them that route is retired, route to `pptx-gen`（按父技能当前工具选择合同）instead.
- Use `scripts/health_check.sh` for backend readiness when the target is local.
- Use `scripts/smoke_test.sh` after changing this reference or wrapper.
- For generation, prefer `banana-cli run jobs` with a JSONL job file and explicit `--report` / `--state-file`.
- Treat `report.json` and `state.json` as truth. Do not parse `run jobs` stdout as clean JSON because progress lines can be mixed in.
- Default to image export when the user says they do not need PPTX.
- Do not run real image generation without backend readiness and user-visible cost awareness.
- Do not put API keys in prompts, logs, docs, or skill files.
- Do not route generic one-off PPT beautification or unqualified NanoBanana2 slide-image generation here; use `pptx-gen` unless the user names 蕉幻/Banana Slides/banana-cli or is already in a Banana workflow.

## Typical Route

For “用蕉幻/Nano Banana 做一套 PPT 图片”:

1. Health check the backend.
2. Create a JSONL job with `job_type="full_generation"`.
3. Set `export.formats=["images"]` unless the user asks for PPTX/PDF.
4. Run the job with report/state files under the current project output directory.
5. Return the report path, state path, project id, artifact URLs, and downloaded file paths if any.

For “智增增 NanoBanana2 2K 直接出图片”:

该路线已退役（见顶部说明）。告知用户 ZZZ 已停用，改用顶层 `pptx-gen`（按父技能当前工具选择合同）生成。
