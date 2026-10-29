"""Deterministic trigger-evaluator regression tests; never invoke an AI CLI."""
import io
import json
import sys
import tempfile
import unittest
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import run_eval, run_loop
from scripts.generate_report import generate_html


def candidate(skill="demo"):
    return f"{skill}-skill-12345678"


def event_bytes(events):
    return b"".join((json.dumps(event, ensure_ascii=False) + "\n").encode() for event in events)


def success():
    return {"type": "result", "subtype": "success", "is_error": False}


def tool(name, tool_input):
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": name, "input": tool_input},
    ]}}


def stream(event_type, index=0, **fields):
    return {"type": "stream_event", "event": {"type": event_type, "index": index, **fields}}


class FakeProcess:
    def __init__(self, exitcode=0):
        self.exitcode = exitcode
        self.returncode = None
        self.stdout = Mock()
        self.stdout.fileno.return_value = 42
        self.killed = False

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        if self.returncode is None:
            self.returncode = self.exitcode
        return self.returncode


class QueryTests(unittest.TestCase):
    def probe(self, events, *, timeout=2, exitcode=0, exited_first=False, chunks=None, skill="demo"):
        process = FakeProcess(exitcode)
        if exited_first:
            process.returncode = exitcode
        with tempfile.TemporaryDirectory() as tmp:
            command_file = Path(tmp).resolve() / ".claude/commands" / f"{candidate(skill)}.md"
            resolved_events = events(command_file) if callable(events) else events
            data = iter(chunks if chunks is not None else [event_bytes(resolved_events), b""])

            def read(fd, size):
                chunk = next(data, b"")
                if not chunk:
                    process.returncode = exitcode
                return chunk

            with patch.object(run_eval.subprocess, "Popen", return_value=process) as popen, \
                 patch.object(run_eval.select, "select", side_effect=lambda *a: ([process.stdout], [], [])), \
                 patch.object(run_eval.os, "read", side_effect=read), \
                 patch.object(run_eval.uuid, "uuid4", return_value=Mock(hex="12345678")):
                try:
                    outcome = run_eval.run_single_query("query", skill, "description", timeout, tmp)
                finally:
                    self.assertEqual(list((Path(tmp) / ".claude/commands").iterdir()), [])
                    self.assertIsNotNone(process.returncode)
                    process.stdout.close.assert_called_once()
                command = popen.call_args.args[0]
                self.assertEqual(command[command.index("--tools") + 1], "Skill,Read")
                self.assertEqual(command[command.index("--permission-mode") + 1], "manual")
                self.assertEqual(command[command.index("--permission-prompts") + 1], "none")
                self.assertIn("--strict-mcp-config", command)
                self.assertEqual(json.loads(command[command.index("--mcp-config") + 1]), {"mcpServers": {}})
                self.assertEqual(json.loads(command[command.index("--settings") + 1]),
                                 {"disableAllHooks": True, "disableSkillShellExecution": True})
                self.assertIn("--no-session-persistence", command)
                self.assertIn("--no-chrome", command)
                self.assertNotIn("--bare", command)
                self.assertNotIn("--safe-mode", command)
                self.assertEqual(popen.call_args.kwargs["stdin"], run_eval.subprocess.DEVNULL)
                return outcome, process

    def test_valid_negative_requires_success_result(self):
        outcome, _ = self.probe([tool("Read", {"file_path": "/tmp/other.txt"}), success()])
        self.assertIs(outcome, False)

    def test_auth_nonzero_missing_result_and_timeout_are_errors(self):
        cases = [
            ([{"type": "result", "subtype": "error_during_execution", "is_error": True}], {}),
            ([success()], {"exitcode": 1}),
            ([{"type": "result", "subtype": "success"}], {}),
            ([tool("Read", {"file_path": "/tmp/other.txt"})], {}),
            ([], {"timeout": 0}),
        ]
        for events, kwargs in cases:
            with self.subTest(events=events, kwargs=kwargs):
                with self.assertRaises(run_eval.QueryEvaluationError):
                    self.probe(events, **kwargs)

    def test_unrelated_first_tool_message_stop_and_read_do_not_hide_later_trigger(self):
        events = [
            tool("Bash", {"command": "ignored fixture only"}),
            stream("message_stop"),
            tool("Read", {"file_path": "/tmp/other.txt"}),
            stream("message_stop"),
            tool("Skill", {"skill": candidate()}),
        ]
        outcome, process = self.probe(events)
        self.assertIs(outcome, True)
        self.assertTrue(process.killed)

    def test_full_assistant_message_scans_all_tools(self):
        message = tool("Read", {"file_path": "/tmp/other.txt"})
        message["message"]["content"].extend(tool("Skill", {"skill": candidate()})["message"]["content"])
        self.assertIs(self.probe([message])[0], True)

    def test_exited_process_and_final_line_without_newline_are_parsed(self):
        encoded = event_bytes([tool("Skill", {"skill": candidate()})]).rstrip(b"\n")
        self.assertIs(self.probe([], chunks=[encoded, b""], exited_first=True)[0], True)

    def test_streamed_input_is_complete_and_exact_not_a_name_substring(self):
        def read_events(filename):
            return [
                stream("content_block_start", content_block={"type": "tool_use", "name": "Read", "input": {}}),
                stream("content_block_delta", delta={"type": "input_json_delta", "partial_json": json.dumps({"file_path": filename})}),
                stream("content_block_stop"),
                success(),
            ]
        self.assertIs(self.probe(read_events("/tmp/demo-notes.txt"))[0], False)
        self.assertIs(self.probe(lambda path: read_events(str(path)))[0], True)
        self.assertIs(self.probe([tool("Skill", {"skill": candidate() + "-other"}), success()])[0], False)
        self.assertIs(self.probe([tool("Skill", {"skill": "namespace:" + candidate()})])[0], True)
        with self.assertRaises(run_eval.QueryEvaluationError):
            self.probe([
                stream("content_block_start", content_block={"type": "tool_use", "name": "Skill", "input": {}}),
                stream("content_block_delta", delta={"type": "input_json_delta", "partial_json": '{"skill":"demo'}),
                success(),
            ])

    def test_utf8_split_between_chunks_preserves_target_skill(self):
        payload = event_bytes([tool("Skill", {"skill": candidate("测试")})])
        split = payload.index("测".encode()) + 1
        self.assertIs(self.probe([], chunks=[payload[:split], payload[split:], b""], skill="测试")[0], True)

    def test_installed_original_is_not_candidate_evidence(self):
        def installed_only(command_file):
            original = command_file.parents[1] / "skills/demo/SKILL.md"
            original.parent.mkdir(parents=True)
            original.write_text("---\nname: demo\ndescription: original description\n---\n")
            return [tool("Skill", {"skill": "demo"}),
                    tool("Skill", {"skill": "namespace:demo"}),
                    tool("Read", {"file_path": str(original)}), success()]
        self.assertIs(self.probe(installed_only)[0], False)

    def test_only_current_candidate_name_or_exact_absolute_file_counts(self):
        self.assertIs(self.probe(lambda path: [tool("Read", {"file_path": str(path)}), success()])[0], True)
        for make_events in [
            lambda path: [tool("Read", {"file_path": str(Path("/other-project/.claude/commands") / path.name)}), success()],
            lambda path: [tool("Read", {"file_path": str(Path(".claude/commands") / path.name)}), success()],
            lambda path: [tool("Skill", {"skill": "demo-skill-other-run"}), success()],
        ]:
            with self.subTest(make_events=make_events):
                self.assertIs(self.probe(make_events)[0], False)

    def test_malformed_output_is_not_a_negative_pass(self):
        with self.assertRaises(run_eval.QueryEvaluationError):
            self.probe([], chunks=[b"not-json\n", b""])


class ImmediateExecutor:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def submit(self, *args):
        future = Future()
        value = next(self.outcomes)
        if isinstance(value, Exception):
            future.set_exception(value)
        else:
            future.set_result(value)
        return future


class AggregationTests(unittest.TestCase):
    def evaluate(self, outcomes, *, expected=False):
        with patch.object(run_eval, "ProcessPoolExecutor", return_value=ImmediateExecutor(outcomes)):
            return run_eval.run_eval([{"query": "query", "should_trigger": expected}], "demo", "desc", 1, 2, Path("/unused"), runs_per_query=len(outcomes))

    def test_exception_cannot_make_a_negative_pass(self):
        output = self.evaluate([run_eval.QueryEvaluationError("authentication failed")])
        result = output["results"][0]
        self.assertFalse(result["pass"])
        self.assertIsNone(result["trigger_rate"])
        self.assertEqual((result["runs"], result["valid_runs"], result["error_runs"]), (1, 0, 1))
        self.assertEqual(output["summary"], {"total": 1, "passed": 0, "failed": 1, "errors": 1})

    def test_mixed_valid_and_error_samples_do_not_pass(self):
        result = self.evaluate([False, run_eval.QueryEvaluationError("timeout")])["results"][0]
        self.assertFalse(result["pass"])
        self.assertEqual(result["trigger_rate"], 0)
        self.assertEqual((result["runs"], result["valid_runs"], result["error_runs"]), (2, 1, 1))
        self.assertTrue(self.evaluate([False])["results"][0]["pass"])
        self.assertTrue(self.evaluate([True], expected=True)["results"][0]["pass"])

    def test_invalid_empty_or_duplicate_evaluation_is_rejected_before_launch(self):
        valid = {"query": "query", "should_trigger": False}
        for eval_set, kwargs in [([], {}), ([valid, valid], {}), ([valid], {"runs_per_query": 0}), ([valid], {"timeout": 0}), ([{"query": "query", "should_trigger": "false"}], {})]:
            with self.subTest(eval_set=eval_set, kwargs=kwargs), patch.object(run_eval, "ProcessPoolExecutor") as executor:
                options = dict(num_workers=1, timeout=2, project_root=Path("/unused"))
                options.update(kwargs)
                with self.assertRaises(ValueError):
                    run_eval.run_eval(eval_set, "demo", "desc", **options)
                executor.assert_not_called()

    def test_legacy_fields_normal_loop_and_report_remain_compatible(self):
        output = self.evaluate([False])
        legacy = {"query", "should_trigger", "trigger_rate", "triggers", "runs", "pass"}
        self.assertTrue(legacy <= set(output["results"][0]))
        with patch.object(run_loop, "find_project_root", return_value=Path("/unused")), \
             patch.object(run_loop, "parse_skill_md", return_value=("demo", "desc", "body")), \
             patch.object(run_loop, "run_eval", return_value=output), \
             patch.object(run_loop, "improve_description") as improve:
            result = run_loop.run_loop([{"query": "query", "should_trigger": False}], Path("/unused"), None, 1, 2, 1, 1, 0.5, 0, "unused-model", False)
            self.assertEqual(result["best_score"], "1/1")
            self.assertIn("all_passed", result["exit_reason"])
            html = generate_html(result)
            self.assertIn('<td class="description">desc</td>', html)
            self.assertIn('<span class="score score-good">1/1</span>', html)
            self.assertIn('<span class="score score-bad">0/0</span>', html)
            self.assertIn('<td class="result pass">✓', html)
            improve.assert_not_called()

    def test_cli_arguments_and_failure_exit_status_remain_visible_in_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "SKILL.md").write_text("fixture only")
            eval_file = root / "eval.json"
            eval_file.write_text(json.dumps([{"query": "query", "should_trigger": False}]))
            argv = ["run_eval.py", "--eval-set", str(eval_file), "--skill-path", str(root),
                    "--num-workers", "1", "--runs-per-query", "1", "--timeout", "90", "--model", "fixture-model"]
            for errors, passed, expected_exit in [(0, 1, 0), (0, 0, 1), (1, 0, 1)]:
                output = {"results": [], "summary": {"total": 1, "passed": passed, "failed": 1-passed, "errors": errors}}
                stdout = io.StringIO()
                with self.subTest(errors=errors, passed=passed), \
                     patch.object(sys, "argv", argv), \
                     patch.object(run_eval, "parse_skill_md", return_value=("demo", "desc", "body")), \
                     patch.object(run_eval, "find_project_root", return_value=root), \
                     patch.object(run_eval, "run_eval", return_value=output) as evaluate, \
                     patch.object(sys, "stdout", stdout):
                    self.assertEqual(run_eval.main(), expected_exit)
                    self.assertEqual(json.loads(stdout.getvalue()), output)
                    self.assertEqual(evaluate.call_args.kwargs["num_workers"], 1)
                    self.assertEqual(evaluate.call_args.kwargs["runs_per_query"], 1)
                    self.assertEqual(evaluate.call_args.kwargs["timeout"], 90)
                    self.assertEqual(evaluate.call_args.kwargs["model"], "fixture-model")

    def test_loop_aborts_invalid_measurements_before_improving_description(self):
        output = self.evaluate([run_eval.QueryEvaluationError("auth failed")])
        with patch.object(run_loop, "find_project_root", return_value=Path("/unused")), \
             patch.object(run_loop, "parse_skill_md", return_value=("demo", "desc", "body")), \
             patch.object(run_loop, "run_eval", return_value=output), \
             patch.object(run_loop, "improve_description") as improve:
            with self.assertRaisesRegex(RuntimeError, "invalid runs"):
                run_loop.run_loop([{"query": "query", "should_trigger": False}], Path("/unused"), None, 1, 2, 2, 1, 0.5, 0, "unused-model", False)
            improve.assert_not_called()


if __name__ == "__main__":
    unittest.main()
