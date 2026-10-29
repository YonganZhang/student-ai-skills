# Workflows

## Images-Only Generation

Use this when the user wants slide images and does not need PPTX.

Create a JSONL file with one job:

```json
{"job_id":"deck-001","job_type":"full_generation","creation_type":"idea","idea_prompt":"你的主题","template_style":"高质量商务汇报风格，16:9，信息密度高","language":"zh","export":{"formats":["images"],"filename_prefix":"deck-001"},"policy":{"continue_on_error":false,"timeout_sec":1800}}
```

Run it:

```bash
banana_cli_wrapper.sh --json run jobs \
  --file jobs.jsonl \
  --report report.json \
  --state-file state.json \
  --done-marker-file done.json \
  --progress-interval-sec 30 \
  --fail-fast
```

Read `report.json` for final status and artifact URLs. Read `state.json` for live status. Do not parse stdout as clean JSON for `run jobs`.

## From Existing Outline

Use `creation_type="outline"` and set `outline_text`.

```json
{"job_id":"outline-001","job_type":"full_generation","creation_type":"outline","outline_text":"1. 背景\n2. 方法\n3. 结果\n4. 下一步","template_style":"学术汇报风格，16:9","language":"zh","export":{"formats":["images"]}}
```

## From Full Page Descriptions

Use `creation_type="descriptions"` and set `description_text`. Banana will parse the description into outline and per-page descriptions, then generate images.

```json
{"job_id":"desc-001","job_type":"full_generation","creation_type":"descriptions","description_text":"第1页：标题页...\n第2页：问题背景...","template_style":"简洁专业，16:9","language":"zh","export":{"formats":["images"]}}
```

## Export Existing Project

Use this when a Banana project already exists.

```json
{"job_id":"export-001","job_type":"export_only","project_id":"<project-id-or-full-id>","export":{"formats":["images"],"filename_prefix":"export-001"}}
```

## Optional PPTX/PDF

Only add these when asked:

```json
"export":{"formats":["images","pptx","pdf"]}
```

Editable PPTX is slower and calls extra analysis/inpainting paths:

```json
"export":{"formats":["editable_pptx"],"editable_max_depth":1,"editable_max_workers":4}
```

## Output Policy

Prefer project-local outputs:

- jobs: `_outputs/banana-slides/jobs/`
- reports: `_outputs/banana-slides/reports/`
- downloads: `_outputs/banana-slides/downloads/`

When returning results, include the report path, project id, status, artifact URLs, and any downloaded local files.

## Direct 智增增 NanoBanana2 2K PNG（已退役）

该直连API路线仅作历史记录。当前图片生成按顶层`pptx-gen`的内置图片工具流程，不调用旧`generate_pptx.py`或FAL。

## Investor-Deck Image Style

When generating PPT/deck images, information density should come from structured diagrams, icons, layout hierarchy, and visual layers, not from many small labels.

Prefer:

- one strong headline and one short subtitle;
- 3-5 labeled modules with concise text;
- arrows, layers, nodes, icons, mock UI cards, floor-plan lines, BIM wireframes, and metric chips;
- deliberate whitespace and clear reading order.

Avoid:

- random floating tags, tiny explanatory labels, fake labels, decorative SKU bubbles, and misspellable micro-text;
- repeating the same title in multiple places;
- prose paragraphs inside the image;
- dense lists where a diagram would be clearer.

For Arctura-style slides, express "information-rich" as a clean mechanism diagram: brief input → world engine → Imagine / Build / Simulate / Source layers. Keep only intentional visible text.
