#!/usr/bin/env python3
"""Hyperparameter search around an existing training command, persisted in an Optuna RDB (SQLite) study.

The project's trainer stays the trainer: every trial runs the user's command unchanged and talks to it through two
environment variables.
  HPO_PARAMS_JSON   path of a JSON file with this trial's parameters (written before the command starts)
  HPO_METRICS_JSON  path where the command must write a JSON object containing the --metric key
  (also HPO_TRIAL_NUMBER and HPO_TRIAL_DIR)

  hpo_study.py create --storage sqlite:///S.db --study NAME --space SPACE.json --metric KEY --direction minimize
                      --budget N [--n-qmc 8] [--seed 0] [--fixed NAME=JSON ...] [--enqueue CFG.json ...]
  hpo_study.py run    --storage ... --study NAME --log-dir DIR [--n-trials K] [--timeout-per-trial S]
                      [--heartbeat-interval 60] [--grace-period 180] [--max-retry 1]
                      [--git-repo DIR] [--run-manifest FILE] -- COMMAND [ARGS ...]
  hpo_study.py report --storage ... --study NAME

SPACE.json: {"lr": {"type": "float", "low": 1e-5, "high": 1e-2, "log": true},
             "depth": {"type": "int", "low": 1, "high": 4, "step": 1},
             "act": {"type": "categorical", "choices": ["relu", "gelu"]}}
create stores space, metric, budget, fixed params and sampler settings in the study (user attrs); re-running create
with different settings is refused, so restarts cannot drift. --fixed holds the scientific variable at one value
(PartialFixedSampler); it must name a space parameter and lie inside its range. --enqueue files (a JSON object or a
list of objects: baseline, previous best) are queued once (skip_if_exists) and may not contradict --fixed.

Sampling: Sobol QMC for trials numbered < --n-qmc, then multivariate TPE with constant_liar (parallel `run` workers on
one storage do not all pick the same point). No pruner: a median/percentile pruner kills slow-starting runs such as
zero-initialised branches, and the trainer reports no intermediate values anyway. A WilcoxonPruner would need
per-instance scores of the selection split reported during the trial; it is deliberately not wired in, and must never
see the evaluation split.

Budget: --budget counts COMPLETE + PRUNED + FAIL + RUNNING trials across all restarts (failures spend budget). A
RUNNING trial occupies its slot from the moment it starts: whether its runner is alive (a parallel worker) or was
killed and its heartbeat has not yet expired, `run` cannot tell, so the slot is never handed out twice -- a resume
inside the grace period starts nothing if the budget is otherwise spent. WAITING trials (--enqueue configs and
heartbeat re-queues) do not count until they start. Heartbeats (RDBStorage heartbeat_interval/grace_period) mark
trials of a killed runner FAIL once the grace period has passed and re-queue them once
(RetryHeartbeatStaleTrialCallback(max_retry)); the stale FAIL keeps its slot, and the re-queued copy needs a free slot
of its own (otherwise it stays WAITING and is listed by report). Optuna's stale check skips a RUNNING trial that never
recorded a heartbeat (runner killed between ask() and its first heartbeat, which a live runner records immediately), so
`run` marks such a trial FAIL itself once it started more than --grace-period seconds ago (listed in
failed_unbeaten_now; it keeps its slot and is not re-queued). `run` starts only the remaining number and stops
after any trial once the count reaches the budget; the count and the start of the next trial are not one atomic
step, so W workers that read the count at the same moment can overshoot by at most W-1 in total (a single worker,
including any sequence of restarts, never overshoots). A runner killed with SIGKILL cannot stop its child;
SIGTERM/SIGINT stop the child's process group and mark the trial FAIL.

Trial failure is never swallowed: exit code != 0, timeout, a missing/non-finite metric -> trial FAIL with the reason
and the log path in user attrs. git HEAD (--git-repo) and the run manifest path + sha256 (--run-manifest) are recorded
per trial.

Output: one JSON object on stdout. Exit codes: 0 success (run: no trial of this invocation failed), 1 run finished but
some trial of this invocation failed, 2 bad input / unknown study / settings mismatch, 130 interrupted.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import warnings
from pathlib import Path

import optuna
from optuna.samplers import BaseSampler, PartialFixedSampler, QMCSampler, TPESampler
from optuna.storages import RDBStorage, RetryHeartbeatStaleTrialCallback
from optuna.study import MaxTrialsCallback
from optuna.trial import TrialState

# RUNNING occupies a budget slot: a killed runner's trial stays RUNNING until its heartbeat expires (then FAIL, still
# counted); not counting it would let a resume inside the grace period start one trial too many.
COUNTED = (TrialState.COMPLETE, TrialState.PRUNED, TrialState.FAIL, TrialState.RUNNING)
SETTINGS = ('space', 'metric', 'budget', 'n_qmc', 'seed', 'fixed')
# QMCSampler, PartialFixedSampler, heartbeats and their retry callback are flagged experimental in Optuna 5.0; the
# flag is about API stability, not correctness, and would bury the trial log on stderr.
warnings.filterwarnings('ignore', category=optuna.exceptions.ExperimentalWarning)


class TrialFailed(Exception):
    """The user command did not produce a usable metric; Optuna records the trial as FAIL."""


class QmcThenTpe(BaseSampler):
    """Trials numbered < n_qmc are sampled by Sobol QMC, later ones by multivariate TPE (constant_liar).

    Routing by trial number keeps every call of one trial on the same sampler and survives restarts.
    """

    def __init__(self, n_qmc: int, seed: int):
        self.n_qmc = n_qmc
        self.qmc = QMCSampler(qmc_type='sobol', scramble=True, seed=seed, warn_independent_sampling=False)
        self.tpe = TPESampler(multivariate=True, constant_liar=True, n_startup_trials=n_qmc)

    def _pick(self, trial):
        return self.qmc if trial.number < self.n_qmc else self.tpe

    def reseed_rng(self):
        self.qmc.reseed_rng(); self.tpe.reseed_rng()

    def infer_relative_search_space(self, study, trial):
        return self._pick(trial).infer_relative_search_space(study, trial)

    def sample_relative(self, study, trial, search_space):
        return self._pick(trial).sample_relative(study, trial, search_space)

    def sample_independent(self, study, trial, param_name, param_distribution):
        return self._pick(trial).sample_independent(study, trial, param_name, param_distribution)

    def before_trial(self, study, trial):
        self._pick(trial).before_trial(study, trial)

    def after_trial(self, study, trial, state, values):
        self._pick(trial).after_trial(study, trial, state, values)


def distribution(name: str, spec: dict):
    d = optuna.distributions
    t = spec.get('type') if isinstance(spec, dict) else None
    keys = {'float': {'type', 'low', 'high', 'log', 'step'}, 'int': {'type', 'low', 'high', 'log', 'step'},
            'categorical': {'type', 'choices'}}
    if t not in keys or set(spec) - keys[t]:
        raise ValueError(f'space[{name!r}]: type must be float/int/categorical with keys {sorted(keys.get(t, []))}')
    if t == 'categorical':
        if not isinstance(spec.get('choices'), list) or not spec['choices']:
            raise ValueError(f'space[{name!r}]: choices must be a nonempty list')
        return d.CategoricalDistribution(spec['choices'])
    if any(type(spec.get(k)) not in (int, float) for k in ('low', 'high')):
        raise ValueError(f'space[{name!r}]: low and high must be numbers')
    cls = d.FloatDistribution if t == 'float' else d.IntDistribution
    kw = dict(low=spec.get('low'), high=spec.get('high'), log=bool(spec.get('log', False)))
    if t == 'int':
        kw['step'] = spec.get('step', 1)
    elif spec.get('step') is not None:
        kw['step'] = spec['step']
    return cls(**kw)


def parse_space(space: dict) -> dict:
    if not isinstance(space, dict) or not space:
        raise ValueError('search space must be a nonempty JSON object')
    return {name: distribution(name, spec) for name, spec in space.items()}


def suggest(trial, name: str, dist):
    d = optuna.distributions
    if isinstance(dist, d.CategoricalDistribution):
        return trial.suggest_categorical(name, dist.choices)
    if isinstance(dist, d.IntDistribution):
        return trial.suggest_int(name, dist.low, dist.high, step=dist.step, log=dist.log)
    return trial.suggest_float(name, dist.low, dist.high, step=dist.step, log=dist.log)


def check_value(dists: dict, name: str, value, what: str):
    if name not in dists:
        raise ValueError(f'{what}: {name!r} is not in the search space')
    dist = dists[name]
    try:
        inside = dist._contains(dist.to_internal_repr(value))
    except (ValueError, TypeError):
        inside = False
    if not inside:
        raise ValueError(f'{what}: {name}={value!r} is outside {dist}')


def open_storage(url: str, a=None) -> RDBStorage:
    if a is None:
        return RDBStorage(url)
    return RDBStorage(url, heartbeat_interval=a.heartbeat_interval, grace_period=a.grace_period,
                      heartbeat_stale_trial_callback=RetryHeartbeatStaleTrialCallback(max_retry=a.max_retry))


def load(storage, name: str) -> optuna.Study:
    try:
        return optuna.load_study(study_name=name, storage=storage)
    except KeyError:
        raise ValueError(f'study {name!r} does not exist in this storage (run create first)')


def cmd_create(a) -> dict:
    space = json.loads(Path(a.space).read_text())
    dists = parse_space(space)
    fixed = {}
    for item in a.fixed:
        name, sep, raw = item.partition('=')
        if not sep:
            raise ValueError(f'--fixed {item!r}: expected NAME=JSON_VALUE')
        try:
            fixed[name] = json.loads(raw)
        except json.JSONDecodeError:
            fixed[name] = raw
        check_value(dists, name, fixed[name], '--fixed')
    if a.budget < 1 or a.n_qmc < 0:
        raise ValueError('--budget must be >= 1 and --n-qmc >= 0')
    settings = dict(space=space, metric=a.metric, budget=a.budget, n_qmc=a.n_qmc, seed=a.seed, fixed=fixed)
    queued = []
    for path in a.enqueue:
        data = json.loads(Path(path).read_text())
        for cfg in data if isinstance(data, list) else [data]:
            if not isinstance(cfg, dict):
                raise ValueError(f'--enqueue {path}: each config must be a JSON object')
            for k, v in cfg.items():
                check_value(dists, k, v, f'--enqueue {path}')
                if k in fixed and v != fixed[k]:
                    raise ValueError(f'--enqueue {path}: {k}={v!r} contradicts --fixed {k}={fixed[k]!r}')
            queued.append((cfg, path))
    storage = open_storage(a.storage)
    study = optuna.create_study(storage=storage, study_name=a.study, direction=a.direction, load_if_exists=True,
                                pruner=optuna.pruners.NopPruner())
    old = {k: study.user_attrs[k] for k in SETTINGS if k in study.user_attrs}
    if old and old != settings:
        raise ValueError(f'study {a.study!r} exists with different settings: {old}')
    if study.direction.name.lower() != a.direction:
        raise ValueError(f'study {a.study!r} exists with direction {study.direction.name.lower()}')
    for k, v in settings.items():
        study.set_user_attr(k, v)
    for cfg, path in queued:
        study.enqueue_trial(cfg, user_attrs={'enqueued_from': str(path)}, skip_if_exists=True)
    waiting = len(study.get_trials(deepcopy=False, states=(TrialState.WAITING,)))
    return dict(study=a.study, storage=a.storage, direction=a.direction, settings=settings, waiting=waiting)


def git_head(repo) -> dict | None:
    if not repo:
        return None
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo, capture_output=True, text=True, timeout=60)
    if head.returncode != 0:
        raise ValueError(f'--git-repo {repo}: {head.stderr.strip()}')
    dirty = subprocess.run(['git', 'status', '--porcelain'], cwd=repo, capture_output=True, text=True, timeout=60)
    return dict(head=head.stdout.strip(), dirty=bool(dirty.stdout.strip()))


def stop_group(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait()


def interrupt(signum, frame):
    raise KeyboardInterrupt(f'signal {signum}')


def make_objective(study, a, command, failures: list):
    dists = parse_space(study.user_attrs['space'])
    metric = study.user_attrs['metric']
    manifest = None
    if a.run_manifest:
        p = Path(a.run_manifest)
        manifest = dict(path=str(p.resolve()), sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    log_dir = Path(a.log_dir).resolve()

    def objective(trial):
        params = {name: suggest(trial, name, dist) for name, dist in dists.items()}
        tdir = log_dir / f'trial_{trial.number:05d}'
        tdir.mkdir(parents=True, exist_ok=False)     # never reuse another trial's outputs
        (tdir / 'params.json').write_text(json.dumps(params, indent=1))
        metrics_path, log_path = tdir / 'metrics.json', tdir / 'command.log'
        for k, v in dict(trial_dir=str(tdir), log=str(log_path), command=command, git=git_head(a.git_repo),
                         run_manifest=manifest).items():
            trial.set_user_attr(k, v)
        env = dict(os.environ, HPO_PARAMS_JSON=str(tdir / 'params.json'), HPO_METRICS_JSON=str(metrics_path),
                   HPO_TRIAL_NUMBER=str(trial.number), HPO_TRIAL_DIR=str(tdir))
        reason = None
        with log_path.open('wb') as log:
            proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, env=env,
                                    start_new_session=True)
            try:
                code = proc.wait(timeout=a.timeout_per_trial)
            except subprocess.TimeoutExpired:
                stop_group(proc)
                code, reason = proc.returncode, f'timeout after {a.timeout_per_trial}s'
            except KeyboardInterrupt:
                stop_group(proc)
                trial.set_user_attr('failure', 'interrupted')
                raise
        trial.set_user_attr('exit_code', code)
        if reason is None and code != 0:
            reason = f'command exited with {code}'
        if reason is None:
            try:
                value = json.loads(metrics_path.read_text())[metric]
            except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
                reason = f'metric {metric!r} not readable from {metrics_path}: {exc!r}'
            else:
                if type(value) not in (int, float) or not math.isfinite(value):
                    reason = f'metric {metric!r} is not a finite number: {value!r}'
        if reason is not None:
            trial.set_user_attr('failure', reason)
            failures.append(dict(trial=trial.number, reason=reason, log=str(log_path)))
            raise TrialFailed(f'{reason}; log: {log_path}')
        return float(value)

    return objective


def counted(study) -> int:
    return len(study.get_trials(deepcopy=False, states=COUNTED))


def fail_unbeaten(storage: RDBStorage, study, grace: int) -> list:
    """RUNNING trials without any heartbeat row that started more than `grace` seconds ago -> FAIL (slot stays spent).
    optuna.storages.fail_stale_trials skips them, so they would hold their budget slot forever. Reads Optuna's RDB
    heartbeat table (private models module, checked against optuna 5.0)."""
    from optuna.storages._rdb import models
    session = storage.scoped_session()
    try:
        beaten = {tid for (tid,) in session.query(models.TrialHeartbeatModel.trial_id)}
    finally:
        storage.scoped_session.remove()
    now, failed = datetime.datetime.now(), []
    for t in study.get_trials(deepcopy=False, states=(TrialState.RUNNING,)):
        if t._trial_id in beaten or t.datetime_start is None or (now - t.datetime_start).total_seconds() <= grace:
            continue
        storage.set_trial_user_attr(t._trial_id, 'fail_reason',
                                    f'no heartbeat within {grace}s of start: runner died before its first heartbeat')
        storage.set_trial_state_values(t._trial_id, TrialState.FAIL)
        failed.append(t.number)
    return failed


def cmd_run(a) -> tuple[dict, int]:
    command = a.command[1:] if a.command[:1] == ['--'] else list(a.command)   # only the CLI's own separator
    if not command:
        raise ValueError('missing training command after --')
    storage = open_storage(a.storage, a)
    study = load(storage, a.study)
    if 'space' not in study.user_attrs:
        raise ValueError(f'study {a.study!r} was not created by hpo_study.py create')
    attrs = study.user_attrs
    study.sampler = PartialFixedSampler(attrs['fixed'], QmcThenTpe(attrs['n_qmc'], attrs['seed']))
    git_head(a.git_repo)                                 # fail before any trial if the repo is unusable
    optuna.storages.fail_stale_trials(study)              # a killed runner's RUNNING trial -> FAIL (+ re-queue)
    unbeaten = fail_unbeaten(storage, study, a.grace_period)
    budget = attrs['budget']
    remaining = budget - counted(study)
    n = remaining if a.n_trials is None else min(remaining, a.n_trials)
    failures: list = []
    if n > 0:
        objective = make_objective(study, a, command, failures)
        signal.signal(signal.SIGTERM, interrupt)
        study.optimize(objective, n_trials=n, timeout=None, catch=(TrialFailed,),
                       callbacks=[MaxTrialsCallback(budget, states=COUNTED)])
    by_state = {s.name: len(study.get_trials(deepcopy=False, states=(s,))) for s in TrialState}
    done = counted(study)
    return dict(study=a.study, budget=budget, counted=done, remaining=max(budget - done, 0), requested_now=max(n, 0),
                states={k: v for k, v in by_state.items() if v}, failures_now=failures,
                failed_unbeaten_now=unbeaten), 1 if failures else 0


def importance(study, names: list) -> dict:
    try:
        from optuna.importance import PedAnovaImportanceEvaluator
    except ImportError:
        return dict(skipped='PedAnovaImportanceEvaluator not available in this optuna version')
    if not names:
        return dict(skipped='no free parameters')
    try:
        return dict(method='ped-anova', values=optuna.importance.get_param_importances(
            study, evaluator=PedAnovaImportanceEvaluator(), params=names))
    except (ValueError, RuntimeError) as exc:   # too few completed trials etc.; reported, not hidden
        return dict(skipped=f'ped-anova failed: {exc}')


def cmd_report(a) -> dict:
    study = load(open_storage(a.storage), a.study)
    attrs = study.user_attrs
    rows = []
    for t in study.get_trials(deepcopy=False):
        dur = (t.datetime_complete - t.datetime_start).total_seconds() if t.datetime_complete and t.datetime_start \
            else None
        rows.append(dict(number=t.number, state=t.state.name, value=t.value, params=t.params, duration_s=dur,
                         failure=t.user_attrs.get('failure'), log=t.user_attrs.get('log'),
                         enqueued_from=t.user_attrs.get('enqueued_from'),
                         retried_from=t.system_attrs.get('failed_trial')))
    complete = study.get_trials(deepcopy=False, states=(TrialState.COMPLETE,))
    best = None
    if complete:
        b = study.best_trial
        best = dict(number=b.number, value=b.value, params=b.params, git=b.user_attrs.get('git'),
                    trial_dir=b.user_attrs.get('trial_dir'))
    free = [k for k in attrs.get('space', {}) if k not in attrs.get('fixed', {})]
    return dict(study=a.study, direction=study.direction.name.lower(), metric=attrs.get('metric'),
                budget=attrs.get('budget'), counted=counted(study), fixed=attrs.get('fixed'), best=best, trials=rows,
                importance=importance(study, free) if len(complete) >= 2 else dict(skipped='fewer than 2 completed'))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('create', 'run', 'report'):
        p = sub.add_parser(name)
        p.add_argument('--storage', required=True, help='RDB URL, e.g. sqlite:///hpo.db')
        p.add_argument('--study', required=True)
        if name == 'create':
            p.add_argument('--space', required=True, help='JSON search-space file')
            p.add_argument('--metric', required=True, help='key in the metrics JSON written by the command')
            p.add_argument('--direction', required=True, choices=('minimize', 'maximize'))
            p.add_argument('--budget', required=True, type=int,
                           help='total trials incl. failures and running ones, across restarts')
            p.add_argument('--n-qmc', type=int, default=8, help='trials numbered below this use Sobol QMC')
            p.add_argument('--seed', type=int, default=0, help='QMC scramble seed (TPE is unseeded)')
            p.add_argument('--fixed', action='append', default=[], help='NAME=JSON_VALUE held fixed')
            p.add_argument('--enqueue', action='append', default=[], help='JSON config(s) to try first')
        if name == 'run':
            p.add_argument('--log-dir', required=True, help='per-trial directories trial_NNNNN/ are created here')
            p.add_argument('--n-trials', type=int, help='cap for this invocation (budget still applies)')
            p.add_argument('--timeout-per-trial', type=float, help='seconds; the command group is killed after it')
            p.add_argument('--heartbeat-interval', type=int, default=60)
            p.add_argument('--grace-period', type=int, default=180)
            p.add_argument('--max-retry', type=int, default=1, help='re-queues of a trial whose runner died')
            p.add_argument('--git-repo', help='record git HEAD and dirty flag of this repo per trial')
            p.add_argument('--run-manifest', help='record this manifest path and sha256 per trial')
            p.add_argument('command', nargs=argparse.REMAINDER, help='-- COMMAND [ARGS ...]')
    a = ap.parse_args(argv)
    code = 0
    try:
        if a.cmd == 'create':
            out = cmd_create(a)
        elif a.cmd == 'run':
            out, code = cmd_run(a)
        else:
            out = cmd_report(a)
    except KeyboardInterrupt as exc:
        print(json.dumps(dict(status='interrupted', error=str(exc))))
        return 130
    except (ValueError, OSError) as exc:
        print(json.dumps(dict(status='error', error=str(exc))))
        return 2
    print(json.dumps(out, indent=1, default=str))
    return code


if __name__ == '__main__':
    sys.exit(main())
