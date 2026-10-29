# Skill Authoring and Evaluation Guide

This is the detailed book behind the short `share-skill-creator` router. Read only the sections needed for authoring, evaluation, description optimization, or packaging.

A skill for creating new skills and iteratively improving them.

At a high level, the process of creating a skill goes like this:

- Decide what you want the skill to do and roughly how it should do it
- Write a draft of the skill
- Create a few test prompts and run claude-with-access-to-the-skill on them
- Help the user evaluate the results both qualitatively and quantitatively
  - While the runs happen in the background, draft some quantitative evals if there aren't any (if there are some, you can either use as is or modify if you feel something needs to change about them). Then explain them to the user (or if they already existed, explain the ones that already exist)
  - Use the `eval-viewer/generate_review.py` script to show the user the results for them to look at, and also let them look at the quantitative metrics
- Rewrite the skill based on feedback from the user's evaluation of the results (and also if there are any glaring flaws that become apparent from the quantitative benchmarks)
- Repeat until you're satisfied
- Expand the test set and try again at larger scale

Your job when using this skill is to figure out where the user is in this process and then jump in and help them progress through these stages. So for instance, maybe they're like "I want to make a skill for X". You can help narrow down what they mean, write a draft, write the test cases, figure out how they want to evaluate, run all the prompts, and repeat.

On the other hand, maybe they already have a draft of the skill. In this case you can go straight to the eval/iterate part of the loop.

Of course, you should always be flexible and if the user is like "I don't need to run a bunch of evaluations, just vibe with me", you can do that instead.

Then after the skill is done (but again, the order is flexible), you can also run the skill description improver, which we have a whole separate script for, to optimize the triggering of the skill.

Cool? Cool.

## Communicating with the user

The skill creator is liable to be used by people across a wide range of familiarity with coding jargon. If you haven't heard (and how could you, it's only very recently that it started), there's a trend now where the power of Claude is inspiring plumbers to open up their terminals, parents and grandparents to google "how to install npm". On the other hand, the bulk of users are probably fairly computer-literate.

So please pay attention to context cues to understand how to phrase your communication! In the default case, just to give you some idea:

- "evaluation" and "benchmark" are borderline, but OK
- for "JSON" and "assertion" you want to see serious cues from the user that they know what those things are before using them without explaining them

It's OK to briefly explain terms if you're in doubt, and feel free to clarify terms with a short definition if you're unsure if the user will get it.

---

## Creating a skill

### Capture Intent

Start by understanding the user's intent. The current conversation might already contain a workflow the user wants to capture (e.g., they say "turn this into a skill"). If so, extract answers from the conversation history first — the tools used, the sequence of steps, corrections the user made, input/output formats observed. The user may need to fill the gaps, and should confirm before proceeding to the next step.

1. What should this skill enable Claude to do?
2. When should this skill trigger? (what user phrases/contexts)
3. What's the expected output format?
4. Should we set up test cases to verify the skill works? Skills with objectively verifiable outputs (file transforms, data extraction, code generation, fixed workflow steps) benefit from test cases. Skills with subjective outputs (writing style, art) often don't need them. Suggest the appropriate default based on the skill type, but let the user decide.

### Interview and Research

Proactively ask questions about edge cases, input/output formats, example files, success criteria, and dependencies. Wait to write test prompts until you've got this part ironed out.

Check available CLI/API/web sources for research (docs, similar skills, best practices); MCP is not a default research path. Research in parallel via subagents if available, otherwise inline. Come prepared with context to reduce burden on the user.

### Write the SKILL.md

⚠️ **CRITICAL — 入口文件名必须是大写 `SKILL.md`**（不是 `skill.md`、不是 `Skill.md`、不是 `readme.md`）。Claude Code 的 skill loader **只扫描大写**，命名错会让整个 skill 永久对所有节点所有 AI 不可见。

**新建 / 重命名 skill 后必跑自检**：

```bash
bash ~/.claude/skills/share-skill-creator/scripts/check_skill_filenames.sh
# exit 0 = 全部合规；exit 1 = 有违规（用 --fix 自动 git mv 修复）

python3 ~/.claude/skills/share-skill-creator/scripts/audit_skill_routing.py ~/.claude/skills   # Codex: ~/.agents/skills
# exit 0 = 路由合规；exit 1 = description/name/legacy 暴露等问题

python3 ~/.claude/skills/share-skill-creator/scripts/audit_skill_refs.py ~/.claude   # Codex: ~/.agents
# exit 0 = 顶层 SKILL.md 引用都能解析；exit 1 = 有死引用
```


Based on the user interview, fill in these components:

- **name**: Skill identifier
- **description**: Route the skill. Say what it does, when it should trigger, and how it differs from adjacent skills. Keep it token-cheap: use realistic user phrases and explicit special triggers, but do not turn the description into a README.
- **compatibility**: Required tools, dependencies (optional, rarely needed)
- **the rest of the skill :)**

### Skill Writing Guide

#### Anatomy of a Skill

```
skill-name/
├── SKILL.md (required)
│   ├── YAML frontmatter (name, description required)
│   └── Markdown instructions
└── Bundled Resources (optional)
    ├── scripts/    - Executable code for deterministic/repetitive tasks
    ├── references/ - Docs loaded into context as needed
    └── assets/     - Files used in output (templates, icons, fonts)
```

#### Router / Book Split

Use this pattern when a skill grows multiple sub-capabilities:

- The top-level `SKILL.md` becomes the router: short description, boundaries, and a compact table that says which child file to read.
- Move the original long workflow into a child book such as `references/sub-skills/<capability>/REFERENCE.md` or `references/<capability>.md`.
- Use nested `SKILL.md` only when the child must be independently routable by global metadata. Otherwise use `REFERENCE.md` / `GUIDE.md` so the loader does not spend tokens advertising every child.
- Do not put every child trigger in the parent description. Put representative user phrases and adjacent-skill boundaries in description; put detailed dispatch rules in the router body.
- Archived or legacy child content must not be named `SKILL.md`; use `ARCHIVED.md`.

Router shape (this package's convention):
- If a skill has more than two child capabilities, convert the top `SKILL.md` into a directory/router: describe the capability family, then point to child references.
- If a skill has one or two child capabilities, the top `SKILL.md` may keep its normal workflow and add a pointer saying when to read each child.
- Parent description must be semantic coverage, not a child list. Example: "Office operations covering Word/PPT/Excel/PDF conversion" instead of enumerating every Word/PPT/Excel command.
- Child details live in `references/` unless the child genuinely needs independent global routing.

After restructuring, run:

```bash
python3 ~/.claude/skills/share-skill-creator/scripts/audit_skill_routing.py ~/.claude/skills   # Codex: ~/.agents/skills
```

#### Progressive Disclosure

Skills use a three-level loading system:
1. **Metadata** (name + description) - Always in context (~100 words)
2. **SKILL.md body** - In context whenever skill triggers (<500 lines ideal)
3. **Bundled resources** - As needed (unlimited, scripts can execute without loading)

These word counts are approximate and you can feel free to go longer if needed.

**Key patterns:**
- Keep SKILL.md under 500 lines; if you're approaching this limit, add an additional layer of hierarchy along with clear pointers about where the model using the skill should go next to follow up.
- Reference files clearly from SKILL.md with guidance on when to read them
- For large reference files (>300 lines), include a table of contents

**Domain organization**: When a skill supports multiple domains/frameworks, organize by variant:
```
cloud-deploy/
├── SKILL.md (workflow + selection)
└── references/
    ├── aws.md
    ├── gcp.md
    └── azure.md
```
Claude reads only the relevant reference file.

#### Principle of Lack of Surprise

This goes without saying, but skills must not contain malware, exploit code, or any content that could compromise system security. A skill's contents should not surprise the user in their intent if described. Don't go along with requests to create misleading skills or skills designed to facilitate unauthorized access, data exfiltration, or other malicious activities. Things like a "roleplay as an XYZ" are OK though.

#### Writing Patterns

Prefer using the imperative form in instructions.

**Defining output formats** - You can do it like this:
```markdown
## Report structure
ALWAYS use this exact template:
# [Title]
## Executive summary
## Key findings
## Recommendations
```

**Examples pattern** - It's useful to include examples. You can format them like this (but if "Input" and "Output" are in the examples you might want to deviate a little):
```markdown
## Commit message format
**Example 1:**
Input: Added user authentication with JWT tokens
Output: feat(auth): implement JWT-based authentication
```

### Writing Style

Try to explain to the model why things are important in lieu of heavy-handed musty MUSTs. Use theory of mind and try to make the skill general and not super-narrow to specific examples. Start by writing a draft and then look at it with fresh eyes and improve it.

### Test Cases

After writing the skill draft, come up with 2-3 realistic test prompts — the kind of thing a real user would actually say. Share them with the user: [you don't have to use this exact language] "Here are a few test cases I'd like to try. Do these look right, or do you want to add more?" Then run them.

Save test cases to `evals/evals.json`. Don't write assertions yet — just the prompts. You'll draft assertions in the next step while the runs are in progress.

```json
{
  "skill_name": "example-skill",
  "evals": [
    {
      "id": 1,
      "prompt": "User's task prompt",
      "expected_output": "Description of expected result",
      "files": []
    }
  ]
}
```

See `references/schemas.md` for the full schema (including the `assertions` field, which you'll add later).

## Running and evaluating test cases

This section is one continuous sequence — don't stop partway through. Do NOT use `/skill-test` or any other testing skill.

Put results in `<skill-name>-workspace/` as a sibling to the skill directory. Within the workspace, organize results by iteration (`iteration-1/`, `iteration-2/`, etc.) and within that, each test case gets a directory (`eval-0/`, `eval-1/`, etc.). Don't create all of this upfront — just create directories as you go.

### Step 1: Spawn all runs (with-skill AND baseline) in the same turn

For each test case, spawn two subagents in the same turn — one with the skill, one without. This is important: don't spawn the with-skill runs first and then come back for baselines later. Launch everything at once so it all finishes around the same time.

**With-skill run:**

```
Execute this task:
- Skill path: <path-to-skill>
- Task: <eval prompt>
- Input files: <eval files if any, or "none">
- Save outputs to: <workspace>/iteration-<N>/eval-<ID>/with_skill/outputs/
- Outputs to save: <what the user cares about — e.g., "the .docx file", "the final CSV">
```

**Baseline run** (same prompt, but the baseline depends on context):
- **Creating a new skill**: no skill at all. Same prompt, no skill path, save to `without_skill/outputs/`.
- **Improving an existing skill**: the old version. Before editing, snapshot the skill (`cp -r <skill-path> <workspace>/skill-snapshot/`), then point the baseline subagent at the snapshot. Save to `old_skill/outputs/`.

Write an `eval_metadata.json` for each test case (assertions can be empty for now). Give each eval a descriptive name based on what it's testing — not just "eval-0". Use this name for the directory too. If this iteration uses new or modified eval prompts, create these files for each new eval directory — don't assume they carry over from previous iterations.

```json
{
  "eval_id": 0,
  "eval_name": "descriptive-name-here",
  "prompt": "The user's task prompt",
  "assertions": []
}
```

### Step 2: While runs are in progress, draft assertions

Don't just wait for the runs to finish — you can use this time productively. Draft quantitative assertions for each test case and explain them to the user. If assertions already exist in `evals/evals.json`, review them and explain what they check.

Good assertions are objectively verifiable and have descriptive names — they should read clearly in the benchmark viewer so someone glancing at the results immediately understands what each one checks. Subjective skills (writing style, design quality) are better evaluated qualitatively — don't force assertions onto things that need human judgment.

Update the `eval_metadata.json` files and `evals/evals.json` with the assertions once drafted. Also explain to the user what they'll see in the viewer — both the qualitative outputs and the quantitative benchmark.

### Step 3: As runs complete, capture timing data

When each subagent task completes, you receive a notification containing `total_tokens` and `duration_ms`. Save this data immediately to `timing.json` in the run directory:

```json
{
  "total_tokens": 84852,
  "duration_ms": 23332,
  "total_duration_seconds": 23.3
}
```

This is the only opportunity to capture this data — it comes through the task notification and isn't persisted elsewhere. Process each notification as it arrives rather than trying to batch them.

### Step 4: Grade, aggregate, and launch the viewer

Once all runs are done:

1. **Grade each run** — spawn a grader subagent (or grade inline) that reads `agents/grader.md` and evaluates each assertion against the outputs. Save results to `grading.json` in each run directory. The grading.json expectations array must use the fields `text`, `passed`, and `evidence` (not `name`/`met`/`details` or other variants) — the viewer depends on these exact field names. For assertions that can be checked programmatically, write and run a script rather than eyeballing it — scripts are faster, more reliable, and can be reused across iterations.

2. **Aggregate into benchmark** — run the aggregation script from the skill-creator directory:
   ```bash
   python -m scripts.aggregate_benchmark <workspace>/iteration-N --skill-name <name>
   ```
   This produces `benchmark.json` and `benchmark.md` with pass_rate, time, and tokens for each configuration, with mean ± stddev and the delta. If generating benchmark.json manually, see `references/schemas.md` for the exact schema the viewer expects.
Put each with_skill version before its baseline counterpart.

3. **Do an analyst pass** — read the benchmark data and surface patterns the aggregate stats might hide. See `agents/analyzer.md` (the "Analyzing Benchmark Results" section) for what to look for — things like assertions that always pass regardless of skill (non-discriminating), high-variance evals (possibly flaky), and time/token tradeoffs.

4. **Launch the viewer** with both qualitative outputs and quantitative data:
   ```bash
   nohup python <skill-creator-path>/eval-viewer/generate_review.py \
     <workspace>/iteration-N \
     --skill-name "my-skill" \
     --benchmark <workspace>/iteration-N/benchmark.json \
     > /dev/null 2>&1 &
   VIEWER_PID=$!
   ```
   For iteration 2+, also pass `--previous-workspace <workspace>/iteration-<N-1>`.

   **Cowork / headless environments:** If `webbrowser.open()` is not available or the environment has no display, use `--static <output_path>` to write a standalone HTML file instead of starting a server. Feedback will be downloaded as a `feedback.json` file when the user clicks "Submit All Reviews". After download, copy `feedback.json` into the workspace directory for the next iteration to pick up.

Note: please use generate_review.py to create the viewer; there's no need to write custom HTML.

5. **Tell the user** something like: "I've opened the results in your browser. There are two tabs — 'Outputs' lets you click through each test case and leave feedback, 'Benchmark' shows the quantitative comparison. When you're done, come back here and let me know."

### What the user sees in the viewer

The "Outputs" tab shows one test case at a time:
- **Prompt**: the task that was given
- **Output**: the files the skill produced, rendered inline where possible
- **Previous Output** (iteration 2+): collapsed section showing last iteration's output
- **Formal Grades** (if grading was run): collapsed section showing assertion pass/fail
- **Feedback**: a textbox that auto-saves as they type
- **Previous Feedback** (iteration 2+): their comments from last time, shown below the textbox

The "Benchmark" tab shows the stats summary: pass rates, timing, and token usage for each configuration, with per-eval breakdowns and analyst observations.

Navigation is via prev/next buttons or arrow keys. When done, they click "Submit All Reviews" which saves all feedback to `feedback.json`.

### Step 5: Read the feedback

When the user tells you they're done, read `feedback.json`:

```json
{
  "reviews": [
    {"run_id": "eval-0-with_skill", "feedback": "the chart is missing axis labels", "timestamp": "..."},
    {"run_id": "eval-1-with_skill", "feedback": "", "timestamp": "..."},
    {"run_id": "eval-2-with_skill", "feedback": "perfect, love this", "timestamp": "..."}
  ],
  "status": "complete"
}
```

Empty feedback means the user thought it was fine. Focus your improvements on the test cases where the user had specific complaints.

Kill the viewer server when you're done with it:

```bash
kill $VIEWER_PID 2>/dev/null
```

---

## Improving the skill

This is the heart of the loop. You've run the test cases, the user has reviewed the results, and now you need to make the skill better based on their feedback.

### How to think about improvements

1. **Generalize from the feedback.** The big picture thing that's happening here is that we're trying to create skills that can be used a million times (maybe literally, maybe even more who knows) across many different prompts. Here you and the user are iterating on only a few examples over and over again because it helps move faster. The user knows these examples in and out and it's quick for them to assess new outputs. But if the skill you and the user are codeveloping works only for those examples, it's useless. Rather than put in fiddly overfitty changes, or oppressively constrictive MUSTs, if there's some stubborn issue, you might try branching out and using different metaphors, or recommending different patterns of working. It's relatively cheap to try and maybe you'll land on something great.

2. **Keep the prompt lean.** Remove things that aren't pulling their weight. Make sure to read the transcripts, not just the final outputs — if it looks like the skill is making the model waste a bunch of time doing things that are unproductive, you can try getting rid of the parts of the skill that are making it do that and seeing what happens.

3. **Explain the why.** Try hard to explain the **why** behind everything you're asking the model to do. Today's LLMs are *smart*. They have good theory of mind and when given a good harness can go beyond rote instructions and really make things happen. Even if the feedback from the user is terse or frustrated, try to actually understand the task and why the user is writing what they wrote, and what they actually wrote, and then transmit this understanding into the instructions. If you find yourself writing ALWAYS or NEVER in all caps, or using super rigid structures, that's a yellow flag — if possible, reframe and explain the reasoning so that the model understands why the thing you're asking for is important. That's a more humane, powerful, and effective approach.

4. **Look for repeated work across test cases.** Read the transcripts from the test runs and notice if the subagents all independently wrote similar helper scripts or took the same multi-step approach to something. If all 3 test cases resulted in the subagent writing a `create_docx.py` or a `build_chart.py`, that's a strong signal the skill should bundle that script. Write it once, put it in `scripts/`, and tell the skill to use it. This saves every future invocation from reinventing the wheel.

This task is pretty important (we are trying to create billions a year in economic value here!) and your thinking time is not the blocker; take your time and really mull things over. I'd suggest writing a draft revision and then looking at it anew and making improvements. Really do your best to get into the head of the user and understand what they want and need.

### The iteration loop

After improving the skill:

1. Apply your improvements to the skill
2. Rerun all test cases into a new `iteration-<N+1>/` directory, including baseline runs. If you're creating a new skill, the baseline is always `without_skill` (no skill) — that stays the same across iterations. If you're improving an existing skill, use your judgment on what makes sense as the baseline: the original version the user came in with, or the previous iteration.
3. Launch the reviewer with `--previous-workspace` pointing at the previous iteration
4. Wait for the user to review and tell you they're done
5. Read the new feedback, improve again, repeat

Keep going until:
- The user says they're happy
- The feedback is all empty (everything looks good)
- You're not making meaningful progress

---

## Advanced: Blind comparison

For situations where you want a more rigorous comparison between two versions of a skill (e.g., the user asks "is the new version actually better?"), there's a blind comparison system. Read `agents/comparator.md` and `agents/analyzer.md` for the details. The basic idea is: give two outputs to an independent agent without telling it which is which, and let it judge quality. Then analyze why the winner won.

This is optional, requires subagents, and most users won't need it. The human review loop is usually sufficient.

---

## Description Optimization

The description field in SKILL.md frontmatter is the primary mechanism that determines whether Claude invokes a skill. After creating or improving a skill, offer to optimize the description for better triggering accuracy.

### Scope of the local trigger probe

`run_eval.py` and `run_loop.py` register a uniquely named candidate command (`<skill>-skill-<run-id>`). A trigger counts only when Claude selects that exact candidate name, optionally with a namespace, or uses Read on that run's exact absolute command-file path. Selecting an already installed original skill or another run's candidate does not count. A non-trigger requires a successful terminal result and exit status 0; timeout, authentication, malformed output and missing terminal evidence are evaluation errors. The optimization loop stops on these errors. The standalone evaluator emits JSON and exits 0 only when every query passes, otherwise 1; argparse usage errors exit 2.

These are bounded candidate-description probes with Skill/Read tools and a two-turn limit. They retain host context and competing candidates, including any installed original skill. Parallel workers may also expose one another's temporary candidates; use `--num-workers 1` for description comparisons. Scores cover this candidate's selection in that environment, not a fully isolated native A/B comparison or the skill's workflow execution quality. Record the environment, model and measurement boundary with results.

The probe supplies an empty strict MCP configuration, disables Chrome and session persistence, and sets `disableAllHooks` plus `disableSkillShellExecution` to suppress configurable hooks and inline shell expansion. User/project settings and candidate discovery remain available for authentication and competition. Managed hook policy still applies; see the [official hooks configuration scope](https://code.claude.com/docs/en/hooks#disable-or-remove-hooks). Do not use `--bare` or `--safe-mode` as an interchangeable isolation switch: they change authentication/context or disable skills.

### Step 1: Generate trigger eval queries

Create 20 eval queries — a mix of should-trigger and should-not-trigger. Save as JSON:

```json
[
  {"query": "the user prompt", "should_trigger": true},
  {"query": "another prompt", "should_trigger": false}
]
```

The queries must be realistic and something a Claude Code or Claude.ai user would actually type. Not abstract requests, but requests that are concrete and specific and have a good amount of detail. For instance, file paths, personal context about the user's job or situation, column names and values, company names, URLs. A little bit of backstory. Some might be in lowercase or contain abbreviations or typos or casual speech. Use a mix of different lengths, and focus on edge cases rather than making them clear-cut (the user will get a chance to sign off on them).

Bad: `"Format this data"`, `"Extract text from PDF"`, `"Create a chart"`

Good: `"ok so my boss just sent me this xlsx file (its in my downloads, called something like 'Q4 sales final FINAL v2.xlsx') and she wants me to add a column that shows the profit margin as a percentage. The revenue is in column C and costs are in column D i think"`

For the **should-trigger** queries (8-10), think about coverage. You want different phrasings of the same intent — some formal, some casual. Include cases where the user doesn't explicitly name the skill or file type but clearly needs it. Throw in some uncommon use cases and cases where this skill competes with another but should win.

For the **should-not-trigger** queries (8-10), the most valuable ones are the near-misses — queries that share keywords or concepts with the skill but actually need something different. Think adjacent domains, ambiguous phrasing where a naive keyword match would trigger but shouldn't, and cases where the query touches on something the skill does but in a context where another tool is more appropriate.

The key thing to avoid: don't make should-not-trigger queries obviously irrelevant. "Write a fibonacci function" as a negative test for a PDF skill is too easy — it doesn't test anything. The negative cases should be genuinely tricky.

### Step 2: Review with user

Present the eval set to the user for review using the HTML template:

1. Read the template from `assets/eval_review.html`
2. Replace the placeholders:
   - `__EVAL_DATA_PLACEHOLDER__` → the JSON array of eval items (no quotes around it — it's a JS variable assignment)
   - `__SKILL_NAME_PLACEHOLDER__` → the skill's name
   - `__SKILL_DESCRIPTION_PLACEHOLDER__` → the skill's current description
3. Write to a temp file (e.g., `/tmp/eval_review_<skill-name>.html`) and open it: `open /tmp/eval_review_<skill-name>.html`
4. The user can edit queries, toggle should-trigger, add/remove entries, then click "Export Eval Set"
5. The file downloads to `~/Downloads/eval_set.json` — check the Downloads folder for the most recent version in case there are multiple (e.g., `eval_set (1).json`)

This step matters — bad eval queries lead to bad descriptions.

### Step 3: Run the optimization loop

Tell the user: "This will take some time — I'll run the optimization loop in the background and check on it periodically."

Save the eval set to the workspace, then run in the background:

```bash
python -m scripts.run_loop \
  --eval-set <path-to-trigger-eval.json> \
  --skill-path <path-to-skill> \
  --model <model-id-powering-this-session> \
  --max-iterations 5 \
  --num-workers 1 \
  --verbose
```

Use the model ID from your system prompt (the one powering the current session) so the triggering test matches what the user actually experiences.

While it runs, periodically tail the output to give the user updates on which iteration it's on and what the scores look like.

This handles the full optimization loop automatically. It splits the eval set into 60% train and 40% held-out test, evaluates the current description (running each query 3 times to get a reliable trigger rate), then calls Claude to propose improvements based on what failed. It re-evaluates each new description on both train and test, iterating up to 5 times. When it's done, it opens an HTML report in the browser showing the results per iteration and returns JSON with `best_description` — selected by test score rather than train score to avoid overfitting.

### How skill triggering works

Understanding the triggering mechanism helps design better eval queries. Skills appear in Claude's `available_skills` list with their name + description, and Claude decides whether to consult a skill based on that description. The important thing to know is that Claude only consults skills for tasks it can't easily handle on its own — simple, one-step queries like "read this PDF" may not trigger a skill even if the description matches perfectly, because Claude can handle them directly with basic tools. Complex, multi-step, or specialized queries reliably trigger skills when the description matches.

This means your eval queries should be substantive enough that Claude would actually benefit from consulting a skill. Simple queries like "read file X" are poor test cases — they won't trigger skills regardless of description quality.

### Step 4: Apply the result

Take `best_description` from the JSON output and update the skill's SKILL.md frontmatter. Show the user before/after and report the scores.

---

### Package and Present (only if `present_files` tool is available)

Check whether you have access to the `present_files` tool. If you don't, skip this step. If you do, package the skill and present the .skill file to the user:

```bash
python -m scripts.package_skill <path/to/skill-folder>
```

After packaging, direct the user to the resulting `.skill` file path so they can install it.

---

## Claude.ai-specific instructions

In Claude.ai, the core workflow is the same (draft → test → review → improve → repeat), but because Claude.ai doesn't have subagents, some mechanics change. Here's what to adapt:

**Running test cases**: No subagents means no parallel execution. For each test case, read the skill's SKILL.md, then follow its instructions to accomplish the test prompt yourself. Do them one at a time. This is less rigorous than independent subagents (you wrote the skill and you're also running it, so you have full context), but it's a useful sanity check — and the human review step compensates. Skip the baseline runs — just use the skill to complete the task as requested.

**Reviewing results**: If you can't open a browser (e.g., Claude.ai's VM has no display, or you're on a remote server), skip the browser reviewer entirely. Instead, present results directly in the conversation. For each test case, show the prompt and the output. If the output is a file the user needs to see (like a .docx or .xlsx), save it to the filesystem and tell them where it is so they can download and inspect it. Ask for feedback inline: "How does this look? Anything you'd change?"

**Benchmarking**: Skip the quantitative benchmarking — it relies on baseline comparisons which aren't meaningful without subagents. Focus on qualitative feedback from the user.

**The iteration loop**: Same as before — improve the skill, rerun the test cases, ask for feedback — just without the browser reviewer in the middle. You can still organize results into iteration directories on the filesystem if you have one.

**Description optimization**: This section requires the `claude` CLI tool (specifically `claude -p`) which is only available in Claude Code. Skip it if you're on Claude.ai.

**Blind comparison**: Requires subagents. Skip it.

**Packaging**: The `package_skill.py` script works anywhere with Python and a filesystem. On Claude.ai, you can run it and the user can download the resulting `.skill` file.

**Updating an existing skill**: The user might be asking you to update an existing skill, not create a new one. In this case:
- **Preserve the original name.** Note the skill's directory name and `name` frontmatter field -- use them unchanged. E.g., if the installed skill is `research-helper`, output `research-helper.skill` (not `research-helper-v2`).
- **Copy to a writeable location before editing.** The installed skill path may be read-only. Copy to `/tmp/skill-name/`, edit there, and package from the copy.
- **If packaging manually, stage in `/tmp/` first**, then copy to the output directory -- direct writes may fail due to permissions.

---

## Cowork-Specific Instructions

If you're in Cowork, the main things to know are:

- You have subagents, so the main workflow (spawn test cases in parallel, run baselines, grade, etc.) all works. (However, if you run into severe problems with timeouts, it's OK to run the test prompts in series rather than parallel.)
- You don't have a browser or display, so when generating the eval viewer, use `--static <output_path>` to write a standalone HTML file instead of starting a server. Then proffer a link that the user can click to open the HTML in their browser.
- For whatever reason, the Cowork setup seems to disincline Claude from generating the eval viewer after running the tests, so just to reiterate: whether you're in Cowork or in Claude Code, after running tests, you should always generate the eval viewer for the human to look at examples before revising the skill yourself and trying to make corrections, using `generate_review.py` (not writing your own boutique html code). Sorry in advance but I'm gonna go all caps here: GENERATE THE EVAL VIEWER *BEFORE* evaluating inputs yourself. You want to get them in front of the human ASAP!
- Feedback works differently: since there's no running server, the viewer's "Submit All Reviews" button will download `feedback.json` as a file. You can then read it from there (you may have to request access first).
- Packaging works — `package_skill.py` just needs Python and a filesystem.
- Description optimization (`run_loop.py` / `run_eval.py`) should work in Cowork just fine since it uses `claude -p` via subprocess, not a browser, but please save it until you've fully finished making the skill and the user agrees it's in good shape.
- **Updating an existing skill**: The user might be asking you to update an existing skill, not create a new one. Follow the update guidance in the claude.ai section above.

---

## Reference files

The agents/ directory contains instructions for specialized subagents. Read them when you need to spawn the relevant subagent.

- `agents/grader.md` — How to evaluate assertions against outputs
- `agents/comparator.md` — How to do blind A/B comparison between two outputs
- `agents/analyzer.md` — How to analyze why one version beat another

The references/ directory has additional documentation:
- `references/schemas.md` — JSON structures for evals.json, grading.json, etc.

---

Repeating one more time the core loop here for emphasis:

- Figure out what the skill is about
- Draft or edit the skill
- Run claude-with-access-to-the-skill on test prompts
- With the user, evaluate the outputs:
  - Create benchmark.json and run `eval-viewer/generate_review.py` to help the user review them
  - Run quantitative evals
- Repeat until you and the user are satisfied
- Package the final skill and return it to the user.

Please add steps to your TodoList, if you have such a thing, to make sure you don't forget. If you're in Cowork, please specifically put "Create evals JSON and run `eval-viewer/generate_review.py` so human can review test cases" in your TodoList to make sure it happens.

Good luck!

---

## 本包写法约定

新建/修改任何 skill 前，**必须** Read `references/conventions.md`。核心要点：
- B 模式（索引 + references）为默认结构，入口 SKILL.md 以 ~150 行为目标、500 行为拆分检查点；完整约束与流程优先，长度不是平台技术限制
- description 是路由提示：做什么 + 触发说法在前，“不触发”边界压成末尾一小句
- Rule + Skill 联动
- 新建脚本前先过防死代码三问

## SKILL.md 风格铁律 — 手册不是日记本

**Skill 是手册，不是日记本**。手册写"做什么 / 怎么做 / 怎么复现"；日记本写"X 月 X 日加了什么 / 因为 Y 出了什么事"。两者必须分离。

### 🔴 禁止（在主 SKILL.md 里）

- 🔴 标题用 `🆕 vX.X 升级（YYYY-MM-DD，某某审吸收 / 某某血泪）` 风格
- 🔴 章节标题挂版本号：`## 五合一架构（2026-05-13 v3.4 升级）` `## CLAUDE.md 规范（强制 — 五合一 v2.1）`
- 🔴 段落开头叙事："2026-04-29 事故：项目 CLAUDE.md 写..." 然后展开 5 行
- 🔴 description 里塞版本号 / 升级历史 / "v3.4 加了第 6 列"
- 🔴 日记词典：**血泪 / 经验沉淀 / 多轮审吸收 / 后期吸收 / 升级**

### ✅ 应该（手册风格）

- ✅ 章节标题是**动作短语**：`## 创建项目` `## 清死代码` `## 接入语义检索` `## 反硬塞铁律`
- ✅ description 只说"是什么 + 主触发"，子能力放正文章节
- ✅ 规则要点直接写，1 行 Why 句留语境（"因为 X 会 Y"），不展开事故叙事

### 历史改动记录怎么处理

挪到 `references/changelog.md`，主 SKILL.md 不污染。changelog.md 写法：

```markdown
## vX.X — 短标题（YYYY-MM-DD）

**做了什么**：1-2 句话
**为什么**：1 句话动机

# 规矩：只记结构性变更（新加 column / 新协议），不记 bug 修复 / 措辞调整。
```

### 更新 skill 的正确动作

1. 改 SKILL.md 里**对应章节**（不在末尾加新"v3.5 升级"段）
2. 如是结构性变更，在 `references/changelog.md` 加 1 条
3. description 字段对应更新（如有触发词变化）

参考本包 `share-top`：主手册不含版本日记标题，历史在 `share-top/references/changelog.md`。

## 渐进式分级（叉树结构）

新建 / 改 skill 时遵循"一级最精简 + 二级 references + 按需加载"原则。
详见 `references/skill-structure-hierarchy.md`。

补充：子技能数量 >2 时，一级 `SKILL.md` 必须转成 router/book 结构；子技能数量 ≤2 时可保留主流程，但只放路径指针和触发时机。description 写类别模式，语义覆盖子能力，不展开子技能触发词清单。

---

## 核心闭环（最后强调一次）

- 搞清楚 skill 要做什么
- 起草或改 skill
- 用测试 prompt 跑 claude-with-access-to-the-skill
- 跟用户一起评估输出：
  - 建 benchmark.json + 跑 `eval-viewer/generate_review.py` 让用户审
  - 跑定量 eval
- 反复迭代到你和用户都满意为止
- 打包最终 skill 交回给用户

记得把这些步骤加到你的 TodoList（如果有）。Cowork 环境特别注意：**显式**加一项 "Create evals JSON and run `eval-viewer/generate_review.py` so human can review test cases" 以免漏。

---

## 🔴 吸收外部 skill 时的硬约束

吸收任何外部 skill (含 subagent 类) 到本地 — **文件搬运 + UPSTREAM.json + 子技能 SKILL.md 不算吸收完成**（UPSTREAM.json 格式见 `references/upstream-tracking.md`，吸收时必须写入）. 必须强制走 6 项 audit:

1. **概念重叠扫描** — grep 新概念跟主流程产物名是否撞 (AI 自己做)
2. **接入点 mapping** — 列新工具应该镶嵌在主技能哪个 Step / Round / Phase (**问用户拍板**)
3. **触发词冲突扫描** — grep 现有 skill description 看冲突 (AI 自己做)
4. **替换/叠加/分流决策** — 每个有重叠的工具 (**问用户拍板**)
5. **强制 vs 可选门控** — schema 卡死还是用户喊才触发 (**问用户拍板**)
6. **必问用户清单** — 整理 2/4/5 的决策点用人话场景叙事问, 不用 A1/B1 编号

### 用户铁律 (吸收 skill / 创建 subagent 都遵守)

- 每个吸收必须**明确触发时机** — 不留模糊
- 不确定触发时机 → **主动问用户**
- **主技能是大目标 + 新技能是工具 → 必须问"怎么变成大流程零件"** (不许只挂 sub-skill 文件不接流程)
- 简单问题 AI 自己规定 (不浪费用户时间)

详细 checklist + 反例 + 正例 + subagent 创建场景延伸 → `references/absorber/references/absorption-checklist.md`

### 反例 (绝对禁止)

🔴 文件搬完 + UPSTREAM.json 写完就汇报"吸收完成" — 这是 phantom registration, 注册了但没人调
🔴 用编号 A1/B1/C1 让用户做选择题 — 用人话场景叙事
🔴 AI 自己决定接入点不问用户 — 大目标的"零件怎么接"必须用户拍板

## 本地比上游多的工具（anthropics/skills 没有）

| 本地工具 | 用途 |
|---|---|
| `scripts/check_skill_filenames.sh` | 防小写 `skill.md` 陷阱，自动 `git mv` 修复 |
| `scripts/scan_orphans.py` | 扫死代码（落盘 scripts/ 没挂载的） |
| `scripts/audit_skill_routing.py` | 检查 name/description、归档目录暴露和父子路由提示 |
| `scripts/audit_skill_refs.py` | 检查顶层 SKILL.md 里的 references/scripts 路径能否解析 |
| `scripts/upstream_watch.py` | 检查各 skill 的 `UPSTREAM.json` 格式与上游变化（只读） |
| `references/absorber/` | 吸收外部 skill 到本地的工作流 |
| `references/conventions.md` | 结构与写法约定（指针 + references、description、拆分检查点、防死代码） |
| `references/skill-structure-hierarchy.md` | 渐进式分级（一级 + 二级 references） |

## 上游同步参考

上游：`anthropics/skills/skills/skill-creator/`（公开仓库，活跃维护）；吸收版本记录在本 skill 的 `UPSTREAM.json`，定时检查见 `references/upstream-tracking.md`。

本地 fork 化路线：保留上游主流程 + 加本地工具（上表）。本文件正文对应上游 `SKILL.md` 正文（去掉 frontmatter 和一级标题）；本地部分副本（agents/、schemas.md 等）是 CRLF，比较时忽略行尾。对比上游正文：
```bash
gh api -H "Accept: application/vnd.github.raw" repos/anthropics/skills/contents/skills/skill-creator/SKILL.md \
  | awk 'NR>1 && /^---$/ {body=1; next} body' | sed 1,3d \
  | diff --strip-trailing-cr - <(sed 1,4d ~/.claude/skills/share-skill-creator/references/authoring-evaluation-guide.md)
```
输出里本地新增段落（`>` 行）是有意的魔改；只关注上游侧（`<` 行）的新内容。
