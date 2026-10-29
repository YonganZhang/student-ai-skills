"""Training-loop sanity checks for a model you are about to train, fine-tune or graft a component into (PyTorch).

Import as a library; the CLI only runs a self-test on toy models:

  python train_sanity_checks.py --selftest      prints a JSON result per check; exit 0 when every check behaves as
                                                expected (healthy toy passes, planted fault is detected), 1 otherwise;
                                                without --selftest prints help and exits 2

Functions:
  strict_reload_roundtrip(build_fn, model, x)   save state_dict -> fresh build_fn() -> strict load -> same outputs?
  eval_mode_consistency(model, x)               eval() deterministic? how far does train() (BN/dropout) move outputs?
  optimizer_covers_trainable(model, optimizer)  every requires_grad parameter in exactly one param group?
  frozen_audit(model, input_size=None)          trainable/frozen counts per top-level module (+ torchinfo rows if installed)
  overfit_under_training_transforms(...)        generic overfit loop over user callbacks; metric curve + target reached?
  debug_locals(fn)                              decorator: summaries of fn's locals at return (shape/dtype/min/max)
All checks report; none of them raises on a failed check. Raising is reserved for misuse or unsupported outputs.
"""
from __future__ import annotations

import argparse
import functools
import json
import reprlib
import sys
import tempfile
from pathlib import Path

import torch
from torch import nn


def _flatten(out, path: str = 'output') -> list:
    """[(path, tensor)] for every tensor leaf; dict keys in sorted order so two outputs pair up leaf by leaf."""
    if torch.is_tensor(out):
        return [(path, out)]
    if isinstance(out, dict):
        return [t for k in sorted(out) for t in _flatten(out[k], f'{path}[{k!r}]')]
    if isinstance(out, (list, tuple)):
        return [t for i, o in enumerate(out) for t in _flatten(o, f'{path}[{i}]')]
    raise TypeError(f'unsupported model output type: {type(out).__name__}')


def _compare(a, b, names: tuple) -> tuple:
    """(max |a - b| over all leaves, non-finite locations). A location is 'NAME:PATH' for a NaN/Inf leaf of either
    output, or 'diff(A,B):PATH' when both leaves are finite but their difference is not (overflow). max_abs is None
    when any location is non-finite: a NaN must fail the check, and max() over floats would silently drop it."""
    ta, tb = _flatten(a), _flatten(b)
    if len(ta) != len(tb) or any(pa != pb or x.shape != y.shape for (pa, x), (pb, y) in zip(ta, tb)):
        raise ValueError('outputs differ in structure or shape')
    worst, bad = 0.0, []
    for (path, x), (_, y) in zip(ta, tb):
        x, y = x.detach().float(), y.detach().float()
        leaf_bad = [f'{n}:{path}' for n, t in zip(names, (x, y)) if not bool(torch.isfinite(t).all())]
        bad += leaf_bad
        if leaf_bad or not x.numel():
            continue
        d = (x - y).abs()
        if not bool(torch.isfinite(d).all()):
            bad.append(f'diff({names[0]},{names[1]}):{path}')
            continue
        worst = max(worst, float(d.max()))
    return (None if bad else worst), bad


def _modes(model: nn.Module) -> list:
    return [(m, m.training) for m in model.modules()]


def _restore_modes(saved: list):
    for m, training in saved:                     # per module: model.train(was) would also flip frozen eval() layers
        m.training = training


def strict_reload_roundtrip(build_fn, model: nn.Module, example_input, *, atol: float = 1e-6) -> dict:
    """Save model.state_dict(), build a fresh model with build_fn(), load strictly, compare eval outputs.

    missing = keys the fresh model expects but the checkpoint lacks; unexpected = checkpoint keys the fresh model does
    not have (typical cause: a buffer or submodule added at training time but not in the constructor). Outputs are only
    compared when the key sets match and the strict load succeeded; a NaN/Inf in any output leaf (or in a difference)
    fails the check and is listed in `nonfinite`. Every submodule's train/eval flag is restored afterwards, also when
    forward raises. Idea (strict load reporting missing/unexpected keys)
    from timm models/_helpers.py, Apache-2.0; implementation is ours.
    """
    device = next(model.parameters()).device
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / 'state.pt'
        torch.save(model.state_dict(), path)
        state = torch.load(path, map_location='cpu', weights_only=True)
    fresh = build_fn().to(device)
    expected = set(fresh.state_dict())
    res = dict(missing=sorted(expected - set(state)), unexpected=sorted(set(state) - expected), max_abs=None, error=None,
               nonfinite=[])
    if res['missing'] or res['unexpected']:
        res['ok'] = False
        return res
    try:
        fresh.load_state_dict(state, strict=True)
    except RuntimeError as exc:                     # e.g. size mismatch: reported as the check result
        res.update(error=str(exc), ok=False)
        return res
    saved = _modes(model)
    try:
        model.eval(); fresh.eval()
        with torch.no_grad():
            res['max_abs'], res['nonfinite'] = _compare(model(example_input), fresh(example_input), ('model', 'reloaded'))
    finally:
        _restore_modes(saved)
    res['ok'] = not res['nonfinite'] and res['max_abs'] <= atol
    return res


def eval_mode_consistency(model: nn.Module, x, *, atol: float = 0.0) -> dict:
    """Two eval() forwards must agree (deterministic inference); also report the train() vs eval() gap.

    A large train/eval gap is not an error by itself (BatchNorm statistics, dropout) but it is the number to look at
    when validation under eval() disagrees with the training loss. Buffers (BN running stats) and every submodule's
    train/eval flag are restored afterwards, also when forward raises. Every NaN/Inf output leaf or difference (of the two
    eval() forwards or of the train() forward) is listed in `nonfinite` and makes the corresponding max_abs None;
    `deterministic` is about the two eval() forwards only, so a non-finite train() forward leaves it True -- callers
    check `nonfinite` as well.
    """
    modes = _modes(model)
    saved = {n: b.detach().clone() for n, b in model.named_buffers()}
    kinds = sorted({type(m).__name__ for m in model.modules()
                    if isinstance(m, (nn.modules.batchnorm._BatchNorm, nn.modules.dropout._DropoutNd))})
    try:
        with torch.no_grad():
            model.eval()
            a, b = model(x), model(x)
            model.train()
            c = model(x)
    finally:
        with torch.no_grad():
            for n, buf in model.named_buffers():
                if n in saved:
                    buf.copy_(saved[n])
        _restore_modes(modes)
    repeat, bad_repeat = _compare(a, b, ('eval1', 'eval2'))
    gap, bad_gap = _compare(a, c, ('eval1', 'train'))
    nonfinite = bad_repeat + [p for p in bad_gap if p not in bad_repeat]
    return dict(eval_repeat_max_abs=repeat, deterministic=not bad_repeat and repeat <= atol,
                train_vs_eval_max_abs=gap, nonfinite=nonfinite, mode_dependent_modules=kinds)


def optimizer_covers_trainable(model: nn.Module, optimizer) -> dict:
    """Every requires_grad parameter must be in some param group exactly once.

    The timm optim/_param_groups.py pitfall: an optimizer built from `filter(requires_grad)` while the backbone is
    frozen never receives the backbone parameters, so unfreezing later updates nothing. Run this after every
    unfreeze/freeze change. `foreign` counts optimizer params that are not (trainable) model parameters.
    """
    names = {id(p): n for n, p in model.named_parameters()}
    seen: dict[int, int] = {}
    for g in optimizer.param_groups:
        for p in g['params']:
            seen[id(p)] = seen.get(id(p), 0) + 1
    trainable = {id(p): n for n, p in model.named_parameters() if p.requires_grad}
    missing = sorted(n for i, n in trainable.items() if i not in seen)
    duplicates = sorted(names.get(i, f'<foreign {i}>') for i, k in seen.items() if k > 1)
    foreign = sum(1 for i in seen if i not in trainable)
    return dict(missing=missing, duplicates=duplicates, foreign=foreign, ok=not missing and not duplicates)


def frozen_audit(model: nn.Module, input_size=None) -> dict:
    """Trainable vs frozen parameter counts (elements) per top-level child; parameters owned directly by the root
    module are listed under '<root>'. With torchinfo installed, `torchinfo` holds its per-layer rows (trainable column
    'True'/'False'/'Partial'); input_size is passed through so rows also carry output shapes. Without torchinfo the
    key is None and `torchinfo_note` says so.
    """
    rows = {}
    for n, p in model.named_parameters():
        top = n.split('.', 1)[0] if '.' in n else '<root>'
        r = rows.setdefault(top, dict(trainable=0, frozen=0))
        r['trainable' if p.requires_grad else 'frozen'] += p.numel()
    out = dict(modules=rows, trainable=sum(r['trainable'] for r in rows.values()),
               frozen=sum(r['frozen'] for r in rows.values()), torchinfo=None, torchinfo_note=None)
    try:
        import torchinfo
    except ImportError:
        out['torchinfo_note'] = 'torchinfo not installed'
        return out
    stats = torchinfo.summary(model, input_size=input_size, verbose=0)
    out['torchinfo'] = [dict(name=r.get_layer_name(False, True), depth=r.depth, params=r.num_params,
                             trainable_params=r.trainable_params, trainable=r.trainable,
                             output_size=r.output_size or None) for r in stats.summary_list]
    return out


def overfit_under_training_transforms(train_step_fn, eval_fn, steps: int, eval_every: int, *, target: float,
                                      higher_is_better: bool = True, stop_at_target: bool = True) -> dict:
    """Overfit probe: call train_step_fn(step) for step = 1..steps, eval_fn() -> float every eval_every steps.

    Evaluate under the SAME transforms used for the overfit training: a probe trained without flips must not be
    scored with flip-TTA, and one trained on crops must be scored on the same crops; otherwise a correct pipeline can
    look broken. Soft targets (Gaussian heatmaps, label smoothing) give the loss a floor > 0, so judge by the task
    metric reaching `target`, not by 'the loss halves'. Returns the curve, the best value and the first step that met
    the target (None if never).
    """
    better = (lambda m: m >= target) if higher_is_better else (lambda m: m <= target)
    curve, reached_at = [], None
    for step in range(1, steps + 1):
        train_step_fn(step)
        if step % eval_every == 0 or step == steps:
            m = float(eval_fn())
            curve.append(dict(step=step, metric=m))
            if better(m) and reached_at is None:
                reached_at = step
                if stop_at_target:
                    break
    vals = [r['metric'] for r in curve]
    best = (max if higher_is_better else min)(vals) if vals else None
    return dict(curve=curve, best=best, target=target, reached=reached_at is not None, reached_at_step=reached_at)


_repr = reprlib.Repr()
_repr.maxstring, _repr.maxother, _repr.maxlist, _repr.maxdict = 80, 80, 6, 6


def summarize(value) -> dict:
    """shape/dtype/min/max (and whether all values are finite) for tensors and numpy arrays; a short repr otherwise."""
    np = sys.modules.get('numpy')                    # an ndarray can only exist if numpy is already imported
    if torch.is_tensor(value) or (np is not None and isinstance(value, np.ndarray)):
        t = torch.as_tensor(value) if not torch.is_tensor(value) else value.detach()
        d = dict(type=type(value).__name__, shape=list(t.shape), dtype=str(value.dtype), min=None, max=None, finite=None)
        if t.numel() and not t.is_complex():
            f = t.float()
            d.update(min=float(f.min()), max=float(f.max()), finite=bool(torch.isfinite(f).all()))
        return d
    return dict(type=type(value).__name__, repr=_repr.repr(value))


def debug_locals(fn):
    """Decorator: when fn returns (or raises), store summaries of its local variables in `wrapper.last_locals`.

    Uses sys.setprofile (call/return events only, no per-line tracing) and restores any previous profiler.
    Adapted from RD-Agent `debug_info_print` (MIT License, Copyright (c) Microsoft Corporation),
    https://github.com/microsoft/RD-Agent/blob/main/rdagent/components/coder/data_science/model/eval_tests/model_test.txt
    -- the original prints reprs of all locals via sys.settrace; this version records shape/dtype/min/max summaries.
    For recursive fn the outermost call's locals are kept (it returns last).
    """
    code = fn.__code__

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        captured = {}

        def profiler(frame, event, arg):
            if event == 'return' and frame.f_code is code:
                captured.clear()
                captured.update({k: summarize(v) for k, v in frame.f_locals.items()})

        previous = sys.getprofile()
        sys.setprofile(profiler)
        try:
            return fn(*args, **kwargs)
        finally:
            sys.setprofile(previous)
            wrapper.last_locals = dict(captured)

    wrapper.last_locals = {}
    return wrapper


def _selftest() -> dict:
    torch.manual_seed(0)

    def build():
        return nn.Sequential(nn.Conv2d(1, 4, 3, padding=1), nn.BatchNorm2d(4), nn.ReLU(), nn.Conv2d(4, 1, 1))

    x = torch.randn(2, 1, 8, 8)
    model = build()
    bad = build()
    bad.register_buffer('extra', torch.zeros(1))
    backbone = model[:3]
    for p in backbone.parameters():
        p.requires_grad_(False)
    opt = torch.optim.SGD([p for p in model.parameters() if p.requires_grad], lr=0.1)
    for p in backbone.parameters():
        p.requires_grad_(True)
    w = torch.zeros(1, requires_grad=True)
    sgd = torch.optim.SGD([w], lr=0.5)

    def step(_):
        sgd.zero_grad(); ((w - 1) ** 2).sum().backward(); sgd.step()

    @debug_locals
    def probe(t):
        y = t * 2
        return y.sum()

    probe(x)
    res = dict(reload_ok=strict_reload_roundtrip(build, model, x),
               reload_extra_buffer=strict_reload_roundtrip(build, bad, x),
               eval_mode=eval_mode_consistency(model, x),
               optimizer_after_unfreeze=optimizer_covers_trainable(model, opt),
               frozen=frozen_audit(model),
               overfit=overfit_under_training_transforms(step, lambda: -float(((w.detach() - 1) ** 2).sum()), 50, 5,
                                                         target=-1e-4),
               debug_locals=probe.last_locals)
    res['frozen'].pop('torchinfo')
    res['passed'] = bool(res['reload_ok']['ok'] and res['reload_extra_buffer']['unexpected'] == ['extra']
                         and res['eval_mode']['deterministic'] and not res['optimizer_after_unfreeze']['ok']
                         and res['overfit']['reached']
                         and res['debug_locals']['y']['shape'] == [2, 1, 8, 8])
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--selftest', action='store_true', help='run every check on toy models and print JSON')
    a = ap.parse_args(argv)
    if not a.selftest:
        ap.print_help()
        return 2
    res = _selftest()
    print(json.dumps(res, indent=1, default=str))
    return 0 if res['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
