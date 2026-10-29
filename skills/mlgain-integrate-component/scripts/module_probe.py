"""Residual-socket probes for grafting a module into a trained network (generalised from the 1号 R13 harness).

Import in the training script; no CLI. Functions:
  ResidualSocket(branch, *, scale_init=0.0)   y = x + s * branch(x); s zero-initialised; `hard_off()` skips the branch
  bypassed(model, sockets)                     context manager: hard bypass of the given sockets (branch not executed)
  step0_parity(model, sockets, x)              max |f(x) - f_bypassed(x)| at initialisation (must be 0 for exact identity)
  optimizer_membership(model, optimizer)       trainable params missing from / duplicated in the optimizer
  EffectiveContribution(sockets)               hooks recording RMS(s*branch(x)) / RMS(x) per socket on chosen batches
  UpdateMeter(params)                          relative parameter change since the last call (are the new parts learning?)
  selection_exposure(curve, first_eligible, unlock_step, effective_at_best)  verdict for the selected checkpoint
Zero-initialised branches have zero first-step gradients behind the zero factor: check after several steps.
Only one factor may be zero (a zero gate times a zero last layer never trains).
"""
from __future__ import annotations

import contextlib
import math

import torch
from torch import nn


class ResidualSocket(nn.Module):
    def __init__(self, branch: nn.Module, *, scale_init: float = 0.0):
        super().__init__()
        self.branch = branch
        self.scale = nn.Parameter(torch.tensor(float(scale_init)))
        self.register_buffer('enabled', torch.tensor(1.0))
        self._record = None

    def hard_off(self, off: bool = True):
        self.enabled.fill_(0.0 if off else 1.0)

    def forward(self, x):
        if self.enabled.item() == 0:
            return x
        delta = self.scale * self.branch(x)
        if self._record is not None:
            with torch.no_grad():
                self._record.append(float(delta.float().pow(2).mean().sqrt() / x.float().pow(2).mean().sqrt().clamp_min(1e-12)))
        return x + delta


@contextlib.contextmanager
def bypassed(model: nn.Module, sockets):
    saved = [(s, s.enabled.clone()) for s in sockets]
    try:
        for s in sockets:
            s.hard_off(True)
        yield model
    finally:
        for s, v in saved:
            s.enabled.copy_(v)


@torch.no_grad()
def step0_parity(model: nn.Module, sockets, x) -> float:
    """Runs in eval(); every submodule's train/eval flag (and the sockets' enabled buffers) is restored exactly
    afterwards, also when forward raises -- model.train(was) would also flip frozen layers kept in eval()."""
    modes = [(m, m.training) for m in model.modules()]
    try:
        model.eval()
        a = model(x)
        with bypassed(model, sockets):
            b = model(x)
    finally:
        for m, training in modes:
            m.training = training
    ta = a if torch.is_tensor(a) else torch.cat([t.flatten() for t in a.values()]) if isinstance(a, dict) else torch.cat([t.flatten() for t in a])
    tb = b if torch.is_tensor(b) else torch.cat([t.flatten() for t in b.values()]) if isinstance(b, dict) else torch.cat([t.flatten() for t in b])
    return float((ta - tb).abs().max())


def optimizer_membership(model: nn.Module, optimizer) -> dict:
    in_opt = [id(p) for g in optimizer.param_groups for p in g['params']]
    trainable = {id(p): n for n, p in model.named_parameters() if p.requires_grad}
    return dict(missing=sorted(n for i, n in trainable.items() if i not in set(in_opt)),
                duplicated=len(in_opt) - len(set(in_opt)),
                foreign=len(set(in_opt) - set(trainable)))


class EffectiveContribution:
    """with EffectiveContribution(sockets) as ec: model(batch) -> ec.values() {i: [ratios]}"""

    def __init__(self, sockets):
        self.sockets = list(sockets)

    def __enter__(self):
        for s in self.sockets:
            s._record = []
        return self

    def __exit__(self, *exc):
        self._vals = {i: list(s._record) for i, s in enumerate(self.sockets)}
        for s in self.sockets:
            s._record = None

    def values(self):
        return self._vals


class UpdateMeter:
    def __init__(self, params):
        self.params = list(params)
        self.prev = [p.detach().clone() for p in self.params]

    def __call__(self) -> float:
        num = sum(float((p.detach() - q).float().pow(2).sum()) for p, q in zip(self.params, self.prev))
        den = sum(float(q.float().pow(2).sum()) for q in self.prev)
        self.prev = [p.detach().clone() for p in self.params]
        return math.sqrt(num) / max(math.sqrt(den), 1e-12)


def selection_exposure(curve, first_eligible: int, unlock_step: int | None, effective_at_best: float | None,
                       min_effective: float = 1e-3) -> dict:
    """curve: [{'step', 'value'}] (lower is better), in any order. The selected row is the minimum of (value, step):
    ties go to the earliest step, as in share-autoresearch-engine/scripts/selection_exposure_check.py. Verdict
    'untested' when the selected checkpoint is the first eligible validation, precedes the branch unlock, or the branch
    contributes nothing at the selected step. Raises ValueError on malformed input (empty curve, non-int or duplicate
    step, non-finite value or effective_at_best, non-finite or negative min_effective)."""
    if type(min_effective) not in (int, float) or not math.isfinite(min_effective) or min_effective < 0:
        raise ValueError(f'min_effective must be a finite number >= 0, got {min_effective!r}')
    if effective_at_best is not None and (type(effective_at_best) not in (int, float)
                                          or not math.isfinite(effective_at_best)):
        raise ValueError(f'effective_at_best must be a finite number or None, got {effective_at_best!r}')
    if not isinstance(curve, (list, tuple)) or not curve:
        raise ValueError('curve must be a nonempty list of {"step", "value"} rows')
    steps = set()
    for r in curve:
        if not isinstance(r, dict) or type(r.get('step')) is not int:
            raise ValueError(f'row {r!r}: "step" must be an int')
        if r['step'] in steps:
            raise ValueError(f'duplicate step {r["step"]}')
        steps.add(r['step'])
        v = r.get('value')
        if type(v) not in (int, float) or not math.isfinite(v):
            raise ValueError(f'row {r!r}: "value" must be a finite number')
    best = min(curve, key=lambda r: (r['value'], r['step']))
    reasons = []
    if best['step'] <= first_eligible:
        reasons.append(f"selected at the first eligible validation (step {best['step']})")
    if unlock_step is not None and best['step'] < unlock_step:
        reasons.append(f"selected (step {best['step']}) before the branch unlocked (step {unlock_step})")
    if effective_at_best is not None and effective_at_best < min_effective:
        reasons.append(f'effective contribution {effective_at_best:.2e} < {min_effective:g} at the selected step')
    return dict(selected_step=best['step'], verdict='untested' if reasons else 'tested', reasons=reasons)
