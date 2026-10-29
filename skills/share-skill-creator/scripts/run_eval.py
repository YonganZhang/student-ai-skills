#!/usr/bin/env python3
"""Run trigger evaluation for a skill description.

Tests whether Claude selects this run's uniquely named description candidate.
Installed originals do not count as candidate evidence. Host candidates still
compete, so this is a bounded probe rather than isolated native A/B evaluation.
Outputs results as JSON.
"""

import argparse
import codecs
import json
import os
import select
import subprocess
import sys
import time
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from scripts.utils import parse_skill_md


def find_project_root() -> Path:
    """Find the project root by walking up from cwd looking for .claude/.

    Mimics how Claude Code discovers its project root, so the command file
    we create ends up where claude -p will look for it.
    """
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / ".claude").is_dir():
            return parent
    return current


class QueryEvaluationError(RuntimeError):
    """The subprocess did not provide a valid trigger measurement."""


def run_single_query(
    query: str,
    skill_name: str,
    skill_description: str,
    timeout: int,
    project_root: str,
    model: str | None = None,
) -> bool:
    """Measure a target Skill/Read invocation, not just the first tool.

    True requires the unique synthetic Skill name or exact absolute command
    file path; installed originals and other runs' candidates do not count.
    False requires a successful
    terminal result and zero process exit status. Missing evidence, CLI errors
    and timeouts raise QueryEvaluationError rather than becoming negative passes.
    This is a bounded description probe; it does not execute arbitrary tools.
    """
    unique_id = uuid.uuid4().hex[:8]
    clean_name = f"{skill_name}-skill-{unique_id}"
    project_commands_dir = Path(project_root).resolve() / ".claude" / "commands"
    command_file = project_commands_dir / f"{clean_name}.md"

    def target_tool(tool_name: str, tool_input: dict) -> bool:
        if tool_name not in ("Skill", "Read"):
            return False
        if not isinstance(tool_input, dict):
            raise QueryEvaluationError("Malformed Skill/Read tool input")
        if tool_name == "Skill":
            name = tool_input.get("skill")
            return isinstance(name, str) and name.rsplit(":", 1)[-1] == clean_name
        filename = tool_input.get("file_path")
        if not isinstance(filename, str):
            return False
        path = Path(filename)
        return path.is_absolute() and path == command_file

    try:
        project_commands_dir.mkdir(parents=True, exist_ok=True)
        indented_desc = "\n  ".join(skill_description.split("\n"))
        command_file.write_text(
            f"---\ndescription: |\n  {indented_desc}\n---\n\n"
            f"# {skill_name}\n\nThis skill handles: {skill_description}\n"
        )
        cmd = [
            "claude", "-p", query,
            "--output-format", "stream-json", "--verbose",
            "--include-partial-messages", "--permission-mode", "manual",
            "--permission-prompts", "none", "--tools", "Skill,Read",
            "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
            "--settings", '{"disableAllHooks":true,"disableSkillShellExecution":true}',
            "--no-session-persistence", "--no-chrome", "--max-turns", "2",
        ]
        if model:
            cmd.extend(["--model", model])
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        process = subprocess.Popen(
            cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, cwd=project_root, env=env,
        )
        deadline = time.monotonic() + timeout
        buffer = ""
        decoder = codecs.getincrementaldecoder("utf-8")()
        pending_tools: dict[int, dict] = {}
        completed = False

        def consume_line(line: str) -> bool:
            nonlocal completed
            if not line.strip():
                return False
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise QueryEvaluationError("Malformed stream-json event") from exc
            if not isinstance(event, dict):
                raise QueryEvaluationError("Stream event must be a JSON object")
            event_type = event.get("type")
            if event_type == "stream_event":
                se = event.get("event", {})
                se_type = se.get("type")
                index = se.get("index", 0)
                if se_type == "content_block_start":
                    block = se.get("content_block", {})
                    if block.get("type") == "tool_use":
                        name = block.get("name", "")
                        if target_tool(name, block.get("input", {})):
                            return True
                        if name in ("Skill", "Read"):
                            pending_tools[index] = {"name": name, "input": block.get("input", {}), "json": ""}
                elif se_type == "content_block_delta" and index in pending_tools:
                    delta = se.get("delta", {})
                    if delta.get("type") == "input_json_delta":
                        pending_tools[index]["json"] += delta.get("partial_json", "")
                elif se_type == "content_block_stop" and index in pending_tools:
                    pending = pending_tools.pop(index)
                    try:
                        tool_input = json.loads(pending["json"]) if pending["json"] else pending["input"]
                    except json.JSONDecodeError as exc:
                        raise QueryEvaluationError("Malformed streamed tool input") from exc
                    if target_tool(pending["name"], tool_input):
                        return True
                # message_stop ends one message, not the whole query.
            elif event_type == "assistant":
                for content in event.get("message", {}).get("content", []):
                    if content.get("type") == "tool_use" and target_tool(content.get("name", ""), content.get("input", {})):
                        return True
            elif event_type == "result":
                if event.get("subtype") != "success" or event.get("is_error") is not False:
                    raise QueryEvaluationError(f"Unsuccessful CLI result: {event.get('subtype', 'missing subtype')}")
                if pending_tools:
                    raise QueryEvaluationError("Incomplete streamed tool input at terminal result")
                completed = True
            return False

        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise QueryEvaluationError(f"Query timed out after {timeout}s")
                ready, _, _ = select.select([process.stdout], [], [], min(1.0, remaining))
                if not ready:
                    if process.poll() is not None:
                        break
                    continue
                chunk = os.read(process.stdout.fileno(), 8192)
                if not chunk:
                    break
                buffer += decoder.decode(chunk)
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if consume_line(line):
                        return True
            buffer += decoder.decode(b"", final=True)
            if buffer.strip() and consume_line(buffer):
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise QueryEvaluationError(f"Query timed out after {timeout}s")
            try:
                returncode = process.wait(timeout=remaining)
            except subprocess.TimeoutExpired as exc:
                raise QueryEvaluationError(f"Query timed out after {timeout}s") from exc
            if returncode != 0:
                raise QueryEvaluationError(f"CLI exited {returncode} without target trigger evidence")
            if not completed:
                raise QueryEvaluationError("CLI exited without a valid terminal result")
            return False
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            process.stdout.close()
    finally:
        if command_file.exists():
            command_file.unlink()


def run_eval(
    eval_set: list[dict],
    skill_name: str,
    description: str,
    num_workers: int,
    timeout: int,
    project_root: Path,
    runs_per_query: int = 1,
    trigger_threshold: float = 0.5,
    model: str | None = None,
) -> dict:
    """Run the full eval set and return results."""
    if not eval_set:
        raise ValueError("eval_set must contain at least one query")
    if num_workers < 1 or runs_per_query < 1 or timeout <= 0:
        raise ValueError("num_workers, runs_per_query and timeout must be positive")
    if not 0 < trigger_threshold <= 1:
        raise ValueError("trigger_threshold must be in (0, 1]")
    seen = set()
    for item in eval_set:
        query = item.get("query")
        if not isinstance(query, str) or not query.strip() or type(item.get("should_trigger")) is not bool:
            raise ValueError("each eval item needs a nonempty query and boolean should_trigger")
        if query in seen:
            raise ValueError("eval queries must be unique")
        seen.add(query)
    results = []

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        future_to_info = {}
        for item in eval_set:
            for run_idx in range(runs_per_query):
                future = executor.submit(
                    run_single_query,
                    item["query"],
                    skill_name,
                    description,
                    timeout,
                    str(project_root),
                    model,
                )
                future_to_info[future] = (item, run_idx)

        query_triggers: dict[str, list[bool]] = {}
        query_errors: dict[str, list[str]] = {}
        query_items: dict[str, dict] = {}
        for future in as_completed(future_to_info):
            item, _ = future_to_info[future]
            query = item["query"]
            query_items[query] = item
            if query not in query_triggers:
                query_triggers[query] = []
                query_errors[query] = []
            try:
                outcome = future.result()
                if type(outcome) is not bool:
                    raise QueryEvaluationError("query returned a non-boolean measurement")
                query_triggers[query].append(outcome)
            except Exception as e:
                print(f"Warning: query failed: {e}", file=sys.stderr)
                query_errors[query].append(f"{type(e).__name__}: {e}")

    for query, triggers in query_triggers.items():
        item = query_items[query]
        errors = query_errors[query]
        trigger_rate = sum(triggers) / len(triggers) if triggers else None
        should_trigger = item["should_trigger"]
        did_pass = not errors and trigger_rate is not None and (
            trigger_rate >= trigger_threshold if should_trigger else trigger_rate < trigger_threshold
        )
        results.append({
            "query": query,
            "should_trigger": should_trigger,
            "trigger_rate": trigger_rate,
            "triggers": sum(triggers),
            "runs": len(triggers) + len(errors),
            "valid_runs": len(triggers),
            "error_runs": len(errors),
            "errors": errors,
            "pass": did_pass,
        })

    passed = sum(1 for r in results if r["pass"])
    total = len(results)

    return {
        "skill_name": skill_name,
        "description": description,
        "results": results,
        "summary": {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "errors": sum(r["error_runs"] for r in results),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run trigger evaluation for a skill description")
    parser.add_argument("--eval-set", required=True, help="Path to eval set JSON file")
    parser.add_argument("--skill-path", required=True, help="Path to skill directory")
    parser.add_argument("--description", default=None, help="Override description to test")
    parser.add_argument("--num-workers", type=int, default=10, help="Number of parallel workers")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout per query in seconds")
    parser.add_argument("--runs-per-query", type=int, default=3, help="Number of runs per query")
    parser.add_argument("--trigger-threshold", type=float, default=0.5, help="Trigger rate threshold")
    parser.add_argument("--model", default=None, help="Model to use for claude -p (default: user's configured model)")
    parser.add_argument("--verbose", action="store_true", help="Print progress to stderr")
    args = parser.parse_args()

    eval_set = json.loads(Path(args.eval_set).read_text())
    skill_path = Path(args.skill_path)

    if not (skill_path / "SKILL.md").exists():
        print(f"Error: No SKILL.md found at {skill_path}", file=sys.stderr)
        sys.exit(1)

    name, original_description, content = parse_skill_md(skill_path)
    description = args.description or original_description
    project_root = find_project_root()

    if args.verbose:
        print(f"Evaluating: {description}", file=sys.stderr)

    output = run_eval(
        eval_set=eval_set,
        skill_name=name,
        description=description,
        num_workers=args.num_workers,
        timeout=args.timeout,
        project_root=project_root,
        runs_per_query=args.runs_per_query,
        trigger_threshold=args.trigger_threshold,
        model=args.model,
    )

    if args.verbose:
        summary = output["summary"]
        print(f"Results: {summary['passed']}/{summary['total']} passed", file=sys.stderr)
        for r in output["results"]:
            status = "PASS" if r["pass"] else "FAIL"
            rate_str = f"{r['triggers']}/{r['runs']}"
            print(f"  [{status}] rate={rate_str} expected={r['should_trigger']}: {r['query'][:70]}", file=sys.stderr)

    print(json.dumps(output, indent=2))
    return 1 if output["summary"]["failed"] or output["summary"].get("errors", 0) else 0


if __name__ == "__main__":
    sys.exit(main())
