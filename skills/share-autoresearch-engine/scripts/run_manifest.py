"""Write a run manifest that lets the exact code, data and environment of an experiment be recovered (stdlib only).

  python3 run_manifest.py --project P --out RUN/run_manifest.json [--code F ...] [--data F ...] [--ckpt F ...]
                          [--config F] [--config-json F] [--seed N] [--split ID] [--env-python PY] [--] [command ...]

Records: git HEAD, branch, `status --porcelain`, sha256 of the staged+unstaged diff, and the sha256 of every --code file
including files that git ignores or does not track (the R13 case: sandbox code ignored by .gitignore still ran); sha256 of
--data / --ckpt / --config files; seed and split id; python version, `pip freeze` hash and torch/CUDA/GPU names from
--env-python; the command line. --config-json F (a JSON object of the run's settings) additionally records
config_identity(): a hash of the settings minus output/log locations and the seed, so repeats of one configuration
across seeds share an identity while any change to what is trained changes it. Environment variables are recorded only
from a whitelist (no secrets). Refuses to overwrite an existing manifest. Exit 0 on success, 2 on bad arguments (missing
file, existing --out, --config-json that is not a JSON object).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

ENV_WHITELIST = ('CUDA_VISIBLE_DEVICES', 'CUBLAS_WORKSPACE_CONFIG', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'PYTHONHASHSEED')
IDENTITY_DROP = ('output', 'out', 'output_dir', 'out_dir', 'log', 'log_dir', 'seed')


def config_identity(cfg: dict, drop=IDENTITY_DROP) -> str:
    """Identity of what a run trains: sha256 (16 hex) of the top-level settings except `drop`.

    Two runs with the same identity differ only in where they write and in their seed. Nested values are compared
    by canonical JSON (sorted keys; non-JSON values via str). Idea from timm sweep.py `job_config_hash`
    (Apache-2.0, https://github.com/huggingface/pytorch-image-models/blob/main/sweep.py); implementation is ours.
    """
    if not isinstance(cfg, dict):
        raise TypeError('config must be a JSON object')
    logical = {k: v for k, v in cfg.items() if k not in drop}
    return hashlib.sha256(json.dumps(logical, sort_keys=True, default=str).encode()).hexdigest()[:16]


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def git(project: Path, *args) -> str:
    r = subprocess.run(['git', *args], cwd=project, capture_output=True, text=True, timeout=60)
    return r.stdout.strip() if r.returncode == 0 else ''


def tracked_state(project: Path, path: Path) -> str:
    rel = str(path.resolve().relative_to(project.resolve()))
    if git(project, 'ls-files', '--', rel):
        return 'modified' if git(project, 'status', '--porcelain', '--', rel) else 'committed'
    ignored = subprocess.run(['git', 'check-ignore', '-q', '--', rel], cwd=project, timeout=60).returncode == 0
    return 'ignored' if ignored else 'untracked'


def env_info(python: str | None) -> dict:
    if not python:
        return dict(python=sys.version.split()[0])
    code = ('import json,sys,platform\nout={"python":sys.version.split()[0]}\n'
            'try:\n import torch\n out.update(torch=torch.__version__, cuda=torch.version.cuda, '
            'gpus=[torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())])\nexcept Exception as e:\n out["torch"]=None\n'
            'print(json.dumps(out))')
    r = subprocess.run([python, '-c', code], capture_output=True, text=True, timeout=120)
    info = json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else dict(error=r.stderr[-300:])
    f = subprocess.run([python, '-c', 'import importlib.metadata as m\nprint("\\n".join(sorted(f"{d.metadata[\'Name\']}=={d.version}" '
                        'for d in m.distributions())))'], capture_output=True, text=True, timeout=120)
    info['packages_sha256'] = hashlib.sha256(f.stdout.encode()).hexdigest() if f.returncode == 0 else None
    info['n_packages'] = len(f.stdout.splitlines()) if f.returncode == 0 else None
    return info


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--project', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--code', nargs='*', default=[], type=Path)
    ap.add_argument('--data', nargs='*', default=[], type=Path)
    ap.add_argument('--ckpt', nargs='*', default=[], type=Path)
    ap.add_argument('--config', type=Path)
    ap.add_argument('--config-json', type=Path, help='JSON object of run settings; records its config_identity()')
    ap.add_argument('--seed', type=int)
    ap.add_argument('--split')
    ap.add_argument('--env-python')
    ap.add_argument('command', nargs=argparse.REMAINDER)
    a = ap.parse_args(argv)
    if a.out.exists():
        print(f'refusing to overwrite {a.out}', file=sys.stderr)
        return 2
    for p in [*a.code, *a.data, *a.ckpt, *([a.config] if a.config else []), *([a.config_json] if a.config_json else [])]:
        if not p.is_file():
            print(f'not a file: {p}', file=sys.stderr)
            return 2
    config_json = None
    if a.config_json:
        try:
            cfg = json.loads(a.config_json.read_text())
            config_json = dict(path=str(a.config_json), sha256=sha(a.config_json), identity=config_identity(cfg),
                               identity_dropped=sorted(k for k in cfg if k in IDENTITY_DROP))
        except (json.JSONDecodeError, TypeError) as exc:
            print(f'bad --config-json {a.config_json}: {exc}', file=sys.stderr)
            return 2
    diff = git(a.project, 'diff', 'HEAD')
    man = dict(created=time.strftime('%Y-%m-%dT%H:%M:%S%z'), host=platform.node(),
               git=dict(head=git(a.project, 'rev-parse', 'HEAD'), branch=git(a.project, 'rev-parse', '--abbrev-ref', 'HEAD'),
                        porcelain=git(a.project, 'status', '--porcelain').splitlines()[:200],
                        diff_sha256=hashlib.sha256(diff.encode()).hexdigest()),
               code={str(p): dict(sha256=sha(p), git=tracked_state(a.project, p)) for p in a.code},
               data={str(p): sha(p) for p in a.data}, checkpoints={str(p): sha(p) for p in a.ckpt},
               config=dict(path=str(a.config), sha256=sha(a.config)) if a.config else None, config_json=config_json,
               seed=a.seed, split=a.split,
               env=env_info(a.env_python), env_vars={k: os.environ.get(k) for k in ENV_WHITELIST},
               command=a.command[1:] if a.command[:1] == ['--'] else a.command)   # keep the command's own '--'
    man['warnings'] = [f'{p} is {v["git"]}: keep this manifest (git cannot restore it)' for p, v in man['code'].items()
                       if v['git'] in ('ignored', 'untracked', 'modified')]
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open('x') as f:
        json.dump(man, f, indent=1)
    for w in man['warnings']:
        print('WARNING', w, file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
