"""Tests for run_manifest.py, selection_exposure_check.py, hpo_study.py and the integration_gate triage profile.

  python3 -m unittest discover -s skills/share-autoresearch-engine/tests -v
hpo_study tests need optuna: they use ARIS_TEST_PYTHON when set, else the current interpreter if it has optuna, and
skip otherwise.
"""
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
GATE = SCRIPTS / "integration_gate.py"
MANIFEST = SCRIPTS / "run_manifest.py"
EXPOSURE = SCRIPTS / "selection_exposure_check.py"
HPO = SCRIPTS / "hpo_study.py"
IDS = ("interface", "training_path", "data_semantics", "baseline_control", "checkpoint")
TRIAGE_IDS = ("evaluator_selftest", "input_alignment", "augmentation_sync", "overfit_train_transforms",
              "positive_control", "selection_exposure")
HPO_PY = os.environ.get("ARIS_TEST_PYTHON") or (sys.executable if importlib.util.find_spec("optuna") else None)

sys.path.insert(0, str(SCRIPTS))
import run_manifest  # noqa: E402

FAKE_TRAIN = """
import json, os, sys, time
p = json.load(open(os.environ['HPO_PARAMS_JSON']))
hang = os.environ.get('HANG_FILE')
while hang and os.path.exists(hang):
    time.sleep(0.05)
if os.environ.get('FAIL_ODD') and int(os.environ['HPO_TRIAL_NUMBER']) % 2:
    print('planted failure', file=sys.stderr)
    sys.exit(3)
if os.environ.get('NO_METRIC'):
    sys.exit(0)
json.dump({'loss': (p['x'] - 0.3) ** 2}, open(os.environ['HPO_METRICS_JSON'], 'w'))
"""


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_py(self, script, *args, py=sys.executable, env=None, timeout=60):
        return subprocess.run([py, str(script), *map(str, args)], capture_output=True, text=True, timeout=timeout,
                              cwd=self.root, env=env)


class RunManifestTest(TempDirTest):
    def test_config_identity_ignores_outputs_and_seed_only(self):
        base = {"lr": 1e-3, "model": {"depth": 4, "act": "gelu"}, "seed": 1, "output": "/a"}
        same = {"output": "/b", "seed": 7, "model": {"act": "gelu", "depth": 4}, "lr": 1e-3, "log_dir": "x"}
        changed = dict(base, lr=2e-3)
        nested = dict(base, model={"depth": 5, "act": "gelu"})
        ident = run_manifest.config_identity
        self.assertEqual(ident(base), ident(same))
        self.assertNotEqual(ident(base), ident(changed))
        self.assertNotEqual(ident(base), ident(nested))
        self.assertNotEqual(ident(base, drop=()), ident(same, drop=()))

    def test_manifest_records_identity_and_ignored_code_and_refuses_overwrite(self):
        repo = self.root / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        (repo / ".gitignore").write_text("sandbox/\n")
        (repo / "sandbox").mkdir()
        (repo / "sandbox/model.py").write_text("x = 1\n")
        (repo / "cfg.json").write_text(json.dumps({"lr": 0.1, "seed": 3, "out": "runs/a"}))
        out = self.root / "m/run_manifest.json"
        args = ["--project", repo, "--out", out, "--code", repo / "sandbox/model.py", "--config-json", repo / "cfg.json",
                "--seed", 3, "--", "python", "train.py"]
        r = self.run_py(MANIFEST, *args)
        self.assertEqual(r.returncode, 0, r.stderr)
        man = json.loads(out.read_text())
        self.assertEqual(man["config_json"]["identity"], run_manifest.config_identity({"lr": 0.1}))
        self.assertEqual(man["config_json"]["identity_dropped"], ["out", "seed"])
        self.assertEqual(man["code"][str(repo / "sandbox/model.py")]["git"], "ignored")
        self.assertIn("ignored", r.stderr)
        self.assertEqual(man["command"], ["python", "train.py"])
        self.assertEqual(self.run_py(MANIFEST, *args).returncode, 2)          # never overwrites

    def test_only_the_cli_separator_is_stripped_from_the_command(self):
        for i, (pre, cmd) in enumerate(((["--"], ["python", "train.py", "--", "-x"]),
                                        ([], ["python", "train.py", "--", "-x"]),
                                        (["--"], ["--", "-x"]))):
            out = self.root / f"m{i}.json"
            r = self.run_py(MANIFEST, "--project", self.root, "--out", out, *pre, *cmd)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(out.read_text())["command"], cmd, (pre, cmd))

    def test_config_json_must_be_object(self):
        (self.root / "cfg.json").write_text("[1, 2]")
        r = self.run_py(MANIFEST, "--project", self.root, "--out", self.root / "m.json", "--config-json",
                        self.root / "cfg.json")
        self.assertEqual(r.returncode, 2)
        self.assertFalse((self.root / "m.json").exists())


class SelectionExposureTest(TempDirTest):
    def check(self, rows, *args, jsonl=False):
        path = self.root / ("curve.jsonl" if jsonl else "curve.json")
        path.write_text("\n".join(json.dumps(r) for r in rows) if jsonl else json.dumps(rows))
        r = self.run_py(EXPOSURE, path, *args)
        return r.returncode, json.loads(r.stdout)

    def test_selected_at_first_eligible_is_untested(self):
        rows = [{"step": s, "value": v} for s, v in ((0, 1.0), (50, 0.5), (100, 0.6), (150, 0.7))]
        code, out = self.check(rows, "--first-eligible", 50)
        self.assertEqual((code, out["verdict"], out["selected_step"]), (3, "untested", 50))

    def test_later_selection_after_unlock_is_tested_and_jsonl_accepted(self):
        rows = [{"step": s, "value": v, "effective": 0.1} for s, v in ((0, 1.0), (50, 0.8), (100, 0.4), (150, 0.7))]
        code, out = self.check(rows, "--first-eligible", 50, "--unlock-step", 60, jsonl=True)
        self.assertEqual((code, out["verdict"]), (0, "tested"))
        self.assertTrue(out["effective_checked"])

    def test_before_unlock_and_dead_branch_are_untested(self):
        rows = [{"step": s, "value": v, "effective": e} for s, v, e in ((50, 0.8, 0.1), (100, 0.4, 1e-5), (150, 0.7, 0.1))]
        code, out = self.check(rows, "--first-eligible", 50, "--unlock-step", 120)
        self.assertEqual(code, 3)
        self.assertEqual(len(out["reasons"]), 2)

    def test_higher_is_better_uses_score_and_reports_ties(self):
        rows = [{"step": s, "score": v} for s, v in ((50, 0.2), (100, 0.9), (150, 0.9))]
        code, out = self.check({"rows": rows}, "--first-eligible", 50, "--higher-is-better")
        self.assertEqual((code, out["selected_step"], out["tied_steps"]), (0, 100, [100, 150]))

    def test_unsorted_ties_go_to_earliest_step(self):
        code, out = self.check([{"step": 100, "value": 1.0}, {"step": 50, "value": 1.0}], "--first-eligible", 50)
        self.assertEqual((code, out["verdict"], out["selected_step"], out["tied_steps"]), (3, "untested", 50, [50, 100]))
        rows = [{"step": 150, "score": 0.9}, {"step": 100, "score": 0.9}, {"step": 50, "score": 0.2}]
        code, out = self.check(rows, "--first-eligible", 50, "--higher-is-better")
        self.assertEqual((code, out["selected_step"], out["tied_steps"]), (0, 100, [100, 150]))

    def test_min_effective_must_be_finite_and_nonnegative(self):
        rows = [{"step": 10, "value": 1.0, "effective": 0.0}]
        for bad in ("nan", "inf", "-inf", "-0.001"):
            code, out = self.check(rows, "--first-eligible", 0, f"--min-effective={bad}")
            self.assertEqual((code, out["verdict"]), (2, "error"), bad)
            self.assertIn("--min-effective", out["error"])
        self.assertEqual(self.check(rows, "--first-eligible", 0, "--min-effective", 0)[0], 0)  # 0 = rule switched off

    def test_bad_input_exits_2(self):
        self.assertEqual(self.check([{"step": 1, "value": "x"}], "--first-eligible", 0)[0], 2)
        self.assertEqual(self.check([{"step": 1, "value": 1.0}, {"step": 1, "value": 2.0}], "--first-eligible", 0)[0], 2)
        self.assertEqual(self.check([{"step": 1, "score": 1.0}], "--first-eligible", 0)[0], 2)   # no "value"
        self.assertEqual(self.check([{"step": 5, "value": 1.0}], "--first-eligible", 0, "--min-effective", 0.01)[0], 2)
        self.assertEqual(self.check([], "--first-eligible", 0)[0], 2)


class TriageProfileTest(TempDirTest):
    def plan(self, profile=True, skip=()):
        checks = [{"id": i, "command": [sys.executable, "-c", "print('ok')"]} for i in IDS]
        if profile:
            checks += [{"id": i, "not_applicable": "no augmentation in this pipeline"} if i in skip else
                       {"id": i, "command": [sys.executable, "-c", "print('ok')"]} for i in TRIAGE_IDS]
        plan = {"schema_version": 1, "checks": checks}
        if profile:
            plan["profile"] = "triage"
        return plan

    def gate(self, plan):
        (self.root / "plan.json").write_text(json.dumps(plan))
        return self.run_py(GATE, self.root / "plan.json", "--project", self.root, "--output", self.root / "run")

    def test_triage_plan_passes_with_all_checks(self):
        r = self.gate(self.plan(skip=("augmentation_sync", "positive_control")))
        self.assertEqual(r.returncode, 0, r.stdout)
        report = json.loads((self.root / "run/report.json").read_text())
        self.assertEqual(len(report["checks"]), 11)

    def test_triage_requires_extra_checks(self):
        plan = self.plan()
        plan["checks"] = [c for c in plan["checks"] if c["id"] != "selection_exposure"]
        r = self.gate(plan)
        self.assertEqual(r.returncode, 2)
        self.assertIn("missing checks: selection_exposure", r.stdout)

    def test_triage_core_checks_cannot_be_skipped(self):
        for name in ("evaluator_selftest", "input_alignment", "overfit_train_transforms", "selection_exposure"):
            r = self.gate(self.plan(skip=(name,)))
            self.assertEqual(r.returncode, 2, name)
            self.assertIn(f"invalid not_applicable: {name}", r.stdout)

    def test_unknown_profile_rejected_and_default_rejects_triage_ids(self):
        plan = self.plan()
        plan["profile"] = "full"
        self.assertEqual(self.gate(plan).returncode, 2)
        plan = self.plan(profile=False)
        plan["checks"].append({"id": "input_alignment", "command": [sys.executable, "-c", "pass"]})
        r = self.gate(plan)
        self.assertEqual(r.returncode, 2)
        self.assertIn("each check id must name a required check", r.stdout)

    def test_default_plan_unchanged(self):
        self.assertEqual(self.gate(self.plan(profile=False)).returncode, 0)


@unittest.skipUnless(HPO_PY, "optuna not importable; set ARIS_TEST_PYTHON to an interpreter with optuna")
class HpoStudyTest(TempDirTest):
    def setUp(self):
        super().setUp()
        (self.root / "space.json").write_text(json.dumps({
            "x": {"type": "float", "low": 0.0, "high": 1.0},
            "k": {"type": "categorical", "choices": ["a", "b"]}}))
        (self.root / "train.py").write_text(FAKE_TRAIN)
        self.storage = f"sqlite:///{self.root / 'hpo.db'}"

    def hpo(self, *args, env=None, timeout=120):
        return self.run_py(HPO, *args, py=HPO_PY, env=dict(os.environ, **(env or {})), timeout=timeout)

    def create(self, budget, *extra):
        r = self.hpo("create", "--storage", self.storage, "--study", "s", "--space", self.root / "space.json",
                     "--metric", "loss", "--direction", "minimize", "--budget", budget, "--n-qmc", 2, *extra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def run_args(self, *extra, grace=2, command=None):
        return ("run", "--storage", self.storage, "--study", "s", "--log-dir", self.root / "logs",
                "--heartbeat-interval", 1, "--grace-period", grace, *extra, "--",
                *(command or (sys.executable, self.root / "train.py")))

    def report(self):
        r = self.hpo("report", "--storage", self.storage, "--study", "s")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def test_search_fixed_param_enqueue_and_report(self):
        (self.root / "base.json").write_text(json.dumps({"x": 0.9, "k": "b"}))
        out = self.create(6, "--fixed", 'k="b"', "--enqueue", self.root / "base.json")
        self.assertEqual(out["waiting"], 1)
        self.create(6, "--fixed", 'k="b"', "--enqueue", self.root / "base.json")   # restart: not queued twice
        r = self.hpo(*self.run_args())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rep = self.report()
        self.assertEqual([t["state"] for t in rep["trials"]], ["COMPLETE"] * 6)
        self.assertEqual(rep["trials"][0]["params"], {"x": 0.9, "k": "b"})
        self.assertTrue(all(t["params"]["k"] == "b" for t in rep["trials"]))
        self.assertLess(rep["best"]["value"], (0.9 - 0.3) ** 2)
        self.assertIn("x", rep["importance"].get("values", {}), rep["importance"])
        self.assertNotIn("k", rep["importance"].get("values", {}))

    def test_bad_settings_rejected(self):
        self.create(4)
        r = self.hpo("create", "--storage", self.storage, "--study", "s", "--space", self.root / "space.json",
                     "--metric", "loss", "--direction", "minimize", "--budget", 9)
        self.assertEqual(r.returncode, 2)
        self.assertIn("different settings", r.stdout)
        for extra in (["--fixed", "x=2.0"], ["--fixed", "nope=1"]):
            r = self.hpo("create", "--storage", self.storage, "--study", "t", "--space", self.root / "space.json",
                         "--metric", "loss", "--direction", "minimize", "--budget", 4, *extra)
            self.assertEqual(r.returncode, 2, extra)
        (self.root / "q.json").write_text(json.dumps({"k": "a"}))
        r = self.hpo("create", "--storage", self.storage, "--study", "u", "--space", self.root / "space.json",
                     "--metric", "loss", "--direction", "minimize", "--budget", 4, "--fixed", 'k="b"',
                     "--enqueue", self.root / "q.json")
        self.assertEqual(r.returncode, 2)
        self.assertIn("contradicts", r.stdout)
        self.assertEqual(self.hpo(*self.run_args()[:4], "missing", *self.run_args()[5:]).returncode, 2)

    def test_failing_command_is_fail_with_log_and_spends_budget(self):
        self.create(4)
        r = self.hpo(*self.run_args(), env={"FAIL_ODD": "1"})
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["states"], {"COMPLETE": 2, "FAIL": 2})
        self.assertEqual(out["remaining"], 0)
        rep = self.report()
        failed = [t for t in rep["trials"] if t["state"] == "FAIL"]
        self.assertEqual([t["failure"] for t in failed], ["command exited with 3"] * 2)
        self.assertIn("planted failure", Path(failed[0]["log"]).read_text())
        r = self.hpo(*self.run_args())                     # budget spent, failures included: nothing more runs
        self.assertEqual(json.loads(r.stdout)["requested_now"], 0)
        self.assertEqual(len(self.report()["trials"]), 4)

    def test_missing_metric_and_timeout_are_failures(self):
        self.create(2)
        r = self.hpo(*self.run_args("--n-trials", 1), env={"NO_METRIC": "1"})
        self.assertEqual(r.returncode, 1)
        hang = self.root / "hang"
        hang.write_text("")
        r = self.hpo(*self.run_args("--timeout-per-trial", 1), env={"HANG_FILE": str(hang)})
        self.assertEqual(r.returncode, 1)
        reasons = [t["failure"] for t in self.report()["trials"]]
        self.assertIn("not readable", reasons[0])
        self.assertEqual(reasons[1], "timeout after 1.0s")

    def kill_runner_during_third_trial(self, budget):
        self.create(budget)
        r = self.hpo(*self.run_args("--n-trials", 2))
        self.assertEqual(json.loads(r.stdout)["counted"], 2)
        hang = self.root / "hang"
        hang.write_text("")
        proc = subprocess.Popen([HPO_PY, str(HPO), *map(str, self.run_args())], cwd=self.root,
                                env=dict(os.environ, HANG_FILE=str(hang)),
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 60
        while not (self.root / "logs/trial_00002/params.json").exists():
            self.assertLess(time.monotonic(), deadline, "trial 2 never started")
            time.sleep(0.05)
        time.sleep(1.5)                                     # at least one heartbeat recorded
        os.kill(proc.pid, signal.SIGKILL)                   # runner dies mid-trial; trial 2 stays RUNNING
        proc.wait()
        hang.unlink()                                       # the orphaned child finishes on its own
        time.sleep(3)                                       # > grace period
        r = self.hpo(*self.run_args())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rep = self.report()
        self.assertEqual(rep["trials"][2]["state"], "FAIL")
        self.assertIn(2, [t["retried_from"] for t in rep["trials"]])   # re-queued once by the heartbeat callback
        self.assertEqual(json.loads(self.hpo(*self.run_args()).stdout)["requested_now"], 0)
        return json.loads(r.stdout)

    def plant_live_running_trial(self):
        """A dead runner's trial whose heartbeat is still fresh (the reviewer's reproducer)."""
        code = ("import optuna, sys; st = optuna.load_study(study_name='s', storage=sys.argv[1]); t = st.ask(); "
                "st._storage.record_heartbeat(t._trial_id)")
        subprocess.run([HPO_PY, "-c", code, self.storage], check=True, capture_output=True, timeout=60)

    def test_running_trial_with_fresh_heartbeat_occupies_budget(self):
        self.create(1)
        self.plant_live_running_trial()
        for _ in range(3):                                  # repeated quick resumes inside the grace period
            r = self.hpo(*self.run_args(grace=30))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            out = json.loads(r.stdout)
            self.assertEqual((out["requested_now"], out["counted"], out["states"]), (0, 1, {"RUNNING": 1}))
        self.assertFalse((self.root / "logs").exists())     # no trial was started
        time.sleep(3)                                       # > grace period of the next run: RUNNING -> FAIL + retry
        out = json.loads(self.hpo(*self.run_args()).stdout)
        self.assertEqual((out["requested_now"], out["counted"]), (0, 1))
        self.assertEqual(out["states"], {"FAIL": 1, "WAITING": 1})   # the retry needs a free slot; there is none

    def test_runner_dead_before_first_heartbeat_is_failed_after_grace(self):
        self.create(1)
        code = "import optuna, sys; optuna.load_study(study_name='s', storage=sys.argv[1]).ask()"   # no heartbeat row
        subprocess.run([HPO_PY, "-c", code, self.storage], check=True, capture_output=True, timeout=60)
        out = json.loads(self.hpo(*self.run_args(grace=30)).stdout)          # inside the grace period: untouched
        self.assertEqual((out["states"], out["failed_unbeaten_now"], out["requested_now"]), ({"RUNNING": 1}, [], 0))
        time.sleep(3)
        r = self.hpo(*self.run_args())                                      # grace 2 s: dead runner's trial -> FAIL
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual((out["states"], out["failed_unbeaten_now"], out["counted"], out["requested_now"]),
                         ({"FAIL": 1}, [0], 1, 0))
        self.assertFalse((self.root / "logs").exists())

    def test_kill_in_last_slot_then_immediate_resumes_do_not_overshoot(self):
        self.create(3)
        self.hpo(*self.run_args("--n-trials", 2))
        hang = self.root / "hang"
        hang.write_text("")
        proc = subprocess.Popen([HPO_PY, str(HPO), *map(str, self.run_args())], cwd=self.root,
                                env=dict(os.environ, HANG_FILE=str(hang)),
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 60
        while not (self.root / "logs/trial_00002/params.json").exists():
            self.assertLess(time.monotonic(), deadline, "trial 2 never started")
            time.sleep(0.05)
        time.sleep(1.5)
        os.kill(proc.pid, signal.SIGKILL)                   # killed during the last budgeted trial
        proc.wait()
        hang.unlink()
        for _ in range(2):                                  # resume immediately, twice, inside the grace period
            out = json.loads(self.hpo(*self.run_args(grace=30)).stdout)
            self.assertEqual((out["requested_now"], out["counted"]), (0, 3))
            self.assertEqual(out["states"], {"COMPLETE": 2, "RUNNING": 1})
        self.assertFalse((self.root / "logs/trial_00003").exists())
        time.sleep(3)
        out = json.loads(self.hpo(*self.run_args()).stdout)
        self.assertEqual((out["requested_now"], out["counted"]), (0, 3))
        self.assertEqual(out["states"], {"COMPLETE": 2, "FAIL": 1, "WAITING": 1})

    def test_child_command_keeps_its_own_separator(self):
        self.create(1)
        check = ("import os, json, sys; assert sys.argv[1:] == ['--', '-x'], sys.argv[1:]; "
                 "json.dump({'loss': 1}, open(os.environ['HPO_METRICS_JSON'], 'w'))")
        r = self.hpo(*self.run_args(command=(sys.executable, "-c", check, "--", "-x")))
        self.assertEqual(r.returncode, 0, r.stdout + (self.root / "logs/trial_00000/command.log").read_text())
        self.assertEqual(self.report()["trials"][0]["state"], "COMPLETE")

    def test_resume_after_killed_runner_runs_retry_within_budget(self):
        out = self.kill_runner_during_third_trial(5)
        self.assertEqual((out["counted"], out["states"]), (5, {"COMPLETE": 4, "FAIL": 1}))

    def test_killed_last_trial_spends_budget_without_overshoot(self):
        out = self.kill_runner_during_third_trial(3)       # the stale FAIL is the last budgeted trial
        self.assertEqual((out["counted"], out["requested_now"]), (3, 0))
        self.assertEqual(out["states"], {"COMPLETE": 2, "FAIL": 1, "WAITING": 1})

if __name__ == "__main__":
    unittest.main()
