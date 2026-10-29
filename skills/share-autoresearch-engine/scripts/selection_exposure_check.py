#!/usr/bin/env python3
"""Was the selected checkpoint ever exposed to the new component? Verdict from a validation curve (stdlib only).

  python3 selection_exposure_check.py CURVE --first-eligible STEP [--unlock-step STEP] [--min-effective X]
                                      [--higher-is-better]

CURVE is a JSON list of rows, a JSON object {"rows": [...]}, or JSONL (one row per line). Each row has an int "step"
and "value" (lower is better; default) or "score" (higher is better; with --higher-is-better), and optionally
"effective" (the branch's effective contribution, e.g. RMS(s*branch(x))/RMS(x), at that step). The selected row is the
best one by (value, step) -- rows may come in any order, ties go to the earliest step -- and all tied steps are
listed.

The verdict is 'untested' when any of these holds (the same rules as
mlgain-integrate-component/scripts/module_probe.py `selection_exposure`):
  - the selected step is at or before the first eligible validation (--first-eligible);
  - the selected step precedes the step at which the branch was unlocked (--unlock-step);
  - the selected row's "effective" is below --min-effective (default 1e-3; checked only when the row has "effective",
    but an explicit --min-effective requires it). --min-effective must be finite and >= 0 (exit 2 otherwise);
    0 switches the dead-branch rule off.
'untested' means the comparison never measured the component; it is not evidence that the component does not help.

Prints one JSON object. Exit 0 = tested, 3 = untested, 2 = bad input.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

DEFAULT_MIN_EFFECTIVE = 1e-3


def load_rows(path: Path) -> list:
    text = path.read_text()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = [json.loads(line) for line in text.splitlines() if line.strip()]
    if isinstance(data, dict):
        data = [data] if 'step' in data else data.get('rows')   # a one-line JSONL file parses as one object
    if not isinstance(data, list) or not data:
        raise ValueError('expected a nonempty list of rows (JSON list, {"rows": [...]} or JSONL)')
    return data


def number(row: dict, key: str) -> float:
    v = row.get(key)
    if type(v) not in (int, float) or not math.isfinite(v):
        raise ValueError(f'row {row!r}: "{key}" must be a finite number')
    return float(v)


def verdict(rows: list, first_eligible: int, unlock_step: int | None = None, min_effective: float | None = None,
            higher_is_better: bool = False) -> dict:
    key = 'score' if higher_is_better else 'value'
    if min_effective is not None and (type(min_effective) not in (int, float) or not math.isfinite(min_effective)
                                      or min_effective < 0):
        raise ValueError(f'--min-effective must be a finite number >= 0, got {min_effective!r}')
    steps = set()
    for r in rows:
        if not isinstance(r, dict) or type(r.get('step')) is not int:
            raise ValueError(f'row {r!r}: "step" must be an int')
        if r['step'] in steps:
            raise ValueError(f'duplicate step {r["step"]}')
        steps.add(r['step'])
        number(r, key)
    sign = -1 if higher_is_better else 1
    best = min(rows, key=lambda r: (sign * r[key], r['step']))      # same rule as module_probe.selection_exposure
    tied = sorted(r['step'] for r in rows if r[key] == best[key])
    reasons = []
    if best['step'] <= first_eligible:
        reasons.append(f"selected at the first eligible validation (step {best['step']})")
    if unlock_step is not None and best['step'] < unlock_step:
        reasons.append(f"selected (step {best['step']}) before the branch unlocked (step {unlock_step})")
    threshold = DEFAULT_MIN_EFFECTIVE if min_effective is None else min_effective
    effective = number(best, 'effective') if 'effective' in best else None
    if effective is None and min_effective is not None:
        raise ValueError(f"--min-effective given but the selected row (step {best['step']}) has no \"effective\"")
    if effective is not None and effective < threshold:
        reasons.append(f'effective contribution {effective:.2e} < {threshold:g} at the selected step')
    return dict(selected_step=best['step'], selected_value=best[key], tied_steps=tied, effective_at_selected=effective,
                effective_checked=effective is not None, verdict='untested' if reasons else 'tested', reasons=reasons)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('curve', type=Path)
    ap.add_argument('--first-eligible', type=int, required=True, help='step of the first validation that may be selected')
    ap.add_argument('--unlock-step', type=int, help='step at which the new branch started training')
    ap.add_argument('--min-effective', type=float, help=f'default {DEFAULT_MIN_EFFECTIVE:g} when rows carry "effective"')
    ap.add_argument('--higher-is-better', action='store_true', help='rank by "score" (max) instead of "value" (min)')
    a = ap.parse_args(argv)
    try:
        out = verdict(load_rows(a.curve), a.first_eligible, a.unlock_step, a.min_effective, a.higher_is_better)
    except (OSError, ValueError) as exc:
        print(json.dumps({'verdict': 'error', 'error': str(exc)}))
        return 2
    print(json.dumps(out))
    return 0 if out['verdict'] == 'tested' else 3


if __name__ == '__main__':
    sys.exit(main())
