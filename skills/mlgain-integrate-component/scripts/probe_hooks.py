#!/usr/bin/env python3
"""Instrument-then-diff probe skeleton for mechanistic-diagnosis.md.

Not a CLI — import these helpers into your own training/debug script.
Core pattern: register forward/backward hooks on baseline and modified
models, run each once on the SAME seed and SAME batch, diff the collected
stats by module name, and look at the module with the largest |log ratio| —
that is almost always the causal entry point of whatever changed.

Usage sketch:
    from probe_hooks import instrument, diff_stats, assert_new_params_registered

    stats_a, handles_a = instrument(baseline_model)
    baseline_model(x); loss_a.backward()
    for h in handles_a: h.remove()

    stats_b, handles_b = instrument(candidate_model)
    candidate_model(x); loss_b.backward()
    for h in handles_b: h.remove()

    for name, ratio in diff_stats(stats_a, stats_b)[:10]:
        print(name, ratio)

⚠️ Sharded backends (FSDP/DeepSpeed ZeRO-3): the raw-.grad/.data functions
below (sgd_update_proxy, snapshot_params, measure_real_update,
assert_gradients_reach, assert_zero_init_unlocked) now call
`_refuse_if_sharded()` first and RAISE rather than silently returning a
shard-local number — this used to be prose-only ("you must gather first")
with nothing actually enforcing it; 2026-08-29 found that gap via
independent review and closed it. Detection is real but best-effort (see
`detect_sharded_backend()`'s own docstring for exactly what it can and
cannot see) — a caught case is caught for real, but an uncaught case is not
proof of safety. You must still gather the full parameter/gradient first
(see P16 in mechanistic-diagnosis.md) and never gate only rank 0 (the
gather calls are collective and will hang the whole job if only one rank
enters them).

⚠️ torch.compile: see instrument()'s allow_compiled guard and
mechanistic-diagnosis.md's tool-selection notes. Short version: register
hooks BEFORE compiling, not after — hooks registered on an already-compiled,
already-called module fire zero times (silently), which is indistinguishable
from "no difference between the two models".

2026-08-29, round 1-2: found and fixed five real bugs (all independently
reproduced): instrument() silently blind to torch.compile'd models and to
functional activations (F.relu written inline instead of nn.ReLU);
diff_stats()'s old fixed 1e-12 floor could invert a ranking in the
vanishing-gradient regime; sgd_update_proxy()/measure_real_update() divided
by a near-zero floor for legitimately zero-initialized parameters (ReZero
alpha, LoRA B) and reported nonsense ratios like 7.7e11.

2026-08-29, round 3 (adversarial hostile-input hunt + real CUDA-graph/compile
execution): found and fixed four more in the same "degenerate input ->
silently legal but wrong number" family: diff_stats() ranked a fully-NaN'd
layer LAST via silent NaN propagation through math.log + Python's sort;
instrument()'s compile guard was top-level-only and missed a per-submodule
torch.compile() under a plain parent (11/13 modules reported — incomplete but
non-empty, so the empty-input ValueError couldn't catch it either); no guard
against a hook firing during CUDA graph capture (fires once at capture, zero
times on every replay(), can silently alias a "per-step" buffer); the three
zero-init probes (assert_zero_init_unlocked/assert_gradients_reach/
sgd_update_proxy) returned confident-looking "all healthy" or "confirmed
bug" verdicts for a typo'd/nonexistent parameter name. Also adversarially
re-tested and CONFIRMED correct: _flatten_tensors() against hostile nested
inputs (duck-typed .detach objects, numel==0 leaves, a real nn.LSTM) — both
hostile cases fail loud; do not re-audit it. See git history / skill
changelog for the reproduction numbers if you need them.

2026-08-29, round 4 (independent Codex review, not self-found): fixed five
more, all confirmed by direct reproduction before fixing. instrument()'s
forward hook silently overwrote (not accumulated) stats for a module called
more than once per forward pass (shared/recurrent/weight-tied layers) —
now tracks `_n_calls`/`_n_bwd_calls` so this is visible instead of invisible.
Its backward hook checked only `grad_output[0] is None` and returned early,
silently dropping gradient info for any module whose FIRST returned tensor
doesn't require grad but a later one does (verified: `(aux_no_grad,
main_with_grad)` produced grad_output `(None, tensor)` and the whole module
was skipped) — now every non-None entry is recorded. diff_stats() ranked a
module whose stat was EXACTLY 0.0 in both runs (e.g. a dead unit that
stayed dead) as float('inf'), tying it with genuine explosions — now
both-exactly-zero reports 0.0 (unchanged), only an asymmetric zero is inf.
effective_rank() silently broadcast over a batch dimension and combined all
matrices' singular values into one distribution before normalizing — 3
identical rank-2 (4x4) matrices stacked into a (3,4,4) batch returned
6.000001 instead of 2.0; now raises ValueError on non-2D input instead of
returning a plausible-looking wrong number. snapshot_params() silently
dropped a typo'd parameter name instead of raising (same failure family as
the three zero-init probes fixed in round 3) — now raises KeyError, closing
the gap for real since measure_real_update() only iterates names present in
the snapshot. Also closed the sharded-backend gap described above (was
prose-only, now enforced by detect_sharded_backend()/_refuse_if_sharded()).
ComponentSocket (assets/pytorch-component-socket.py) gained a dtype/device/
layout check alongside the existing shape check (a float32 base + float64
candidate previously passed silently and returned float64), and
check_contract() now actually mirrors CUDA RNG state as its own docstring
already claimed but the implementation never did.
"""
from __future__ import annotations

import math


def detect_sharded_backend(model):
    """Best-effort detection of FSDP/DeepSpeed ZeRO-3 wrapping, used by
    `_refuse_if_sharded()` below to turn the "you must gather first" warning
    from prose into an actual raise. Returns a backend name string, or None.

    ⚠️ A None result does NOT prove the model is unsharded — it only means
    this cheap check found nothing. FSDP1 with `use_orig_params=True`
    exposes ordinary nn.Parameter objects whose `.data` is a view into a
    flattened per-rank shard buffer; there is no distinct Python type for
    this case, only "is some ancestor module an FSDP instance", which this
    function does check. If you wrap only an inner submodule and pass a
    different (unwrapped) submodule into these probes, this detector will
    not see the FSDP ancestor and will not fire. Treat a None here as "this
    particular check found nothing", not as "this model is safe".
    """
    try:
        from torch.distributed.fsdp import FullyShardedDataParallel as _FSDP
        for m in model.modules():
            if isinstance(m, _FSDP):
                return "FSDP1"
    except ImportError:
        pass
    try:
        from torch.distributed.tensor import DTensor as _DTensor
        for p in model.parameters():
            if isinstance(p, _DTensor):
                return "DTensor (FSDP2/fully_shard or tensor-parallel)"
    except ImportError:
        pass
    if type(model).__name__ == "DeepSpeedEngine" or hasattr(model, "zero_optimization_stage"):
        return "DeepSpeed"
    return None


def _refuse_if_sharded(model, fn_name):
    """Call at the top of any function that reads raw .grad/.data on
    `model`'s parameters. Raises instead of letting the caller silently get
    back a shard-local number that is legal-looking but meaningless on a
    multi-rank job — per the official FSDP docs, an original parameter may
    expose all, some, or none of its data on a given rank, and its sharded
    form may be flattened.
    """
    backend = detect_sharded_backend(model)
    if backend is not None:
        raise RuntimeError(
            f"{fn_name}() called on a model wrapped by {backend}. This "
            f"function reads raw .grad/.data, which under {backend} is "
            f"shard-local — a legal-looking but meaningless number, not an "
            f"error you'd otherwise see. Gather the full parameter/gradient "
            f"first via P16 in mechanistic-diagnosis.md (FSDP.summon_full_"
            f"params / DeepSpeed's safe_get_full_grad), on EVERY rank (these "
            f"gathers are collective and will hang the job if only one rank "
            f"enters them), before calling this function."
        )


def _flatten_tensors(obj, prefix=""):
    """Yield (path, tensor) for every tensor leaf in a nested output —
    handles a bare tensor, or arbitrary nesting of tuple/list/dict (e.g. the
    dict outputs common in detectron2/pytorch-forecasting/HF models). A
    module that returns a dict was previously silently skipped entirely by
    this file's forward hook — that is exactly the kind of "looks instrumented
    but isn't" gap this skill exists to catch, so it is fixed here rather than
    left as a known limitation.
    """
    if hasattr(obj, "detach"):
        yield prefix or "0", obj
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _flatten_tensors(v, f"{prefix}.{k}" if prefix else str(k))
        return
    if isinstance(obj, (tuple, list)):
        for i, v in enumerate(obj):
            yield from _flatten_tensors(v, f"{prefix}[{i}]" if prefix else f"[{i}]")
        return
    # not a tensor and not a known container (e.g. None, a config object) — skip


def instrument(model, allow_compiled=False):
    """Register forward + full-backward hooks on every named module.

    Returns (stats, handles). stats[name] is itself a dict keyed by the
    flattened output path (see _flatten_tensors) whose values accumulate:
      mean, std, zero_frac, absmax, _n_calls (from the forward output)
      grad_norm (from the backward hook, filled in after .backward(),
      keyed under path "0", "1", ... by position in PyTorch's flat
      grad_output tuple — NOT the original nested structure the forward
      returned; a module returning `(aux, main)` with only `main` requiring
      grad reports at path "1", not "0")
    Caller is responsible for calling handle.remove() for every handle in
    `handles` after the pass — probes must not leak into training.

    ⚠️ A module invoked MORE THAN ONCE per forward pass (weight-tied/shared
    layers, an RNN cell called once per timestep in a hand-written loop)
    only reports the LAST call's numbers — earlier calls are silently
    overwritten, not accumulated or averaged. Verified: a shared Linear
    called 3 times in a loop reports only the 3rd call's mean/std/grad_norm.
    Check `stats[name][path]["_n_calls"]` (forward) / `["_n_bwd_calls"]`
    (backward, tracked separately since both hooks can write the same path):
    if either is >1, the reported numbers characterize only the final
    invocation, not the whole sequence — do not read them as "this layer's
    behavior" for a recurrent/shared module without accounting for this.

    ⚠️ A module returning multiple outputs where only a NON-FIRST one
    requires grad used to report NOTHING for grad_norm (the backward hook
    checked only `grad_output[0] is None` and returned early) — verified:
    `forward() -> (aux_no_grad, main_with_grad)` produced grad_output
    `(None, tensor)` and the old hook silently skipped it entirely. Fixed:
    every non-None entry in grad_output is now recorded, at path "0", "1", …
    matching its position in the tuple.

    ⚠️ Only nn.Module submodules are visible here. An activation written as
    a functional call inline in forward() (F.relu(x), F.gelu(x),
    torch.sigmoid(x)) produces NO hook and is invisible to this function —
    and the failure is silent, not an error. Verified: `return
    F.relu(self.lin(x))` yields zero_frac {'lin': 0.0}; the byte-identical
    model written as `self.act = nn.ReLU(); ... return self.act(self.lin(x))`
    yields {'lin': 0.0, 'act': 0.4961} on the same input. A 0.0 zero_frac
    from the F.relu version means "the activation was never observed", not
    "no dead units". Call assert_activation_modules_visible() before trusting
    a P4 dead-unit/saturation reading, or convert functional activations to
    nn.Module members before instrumenting.

    ⚠️ In-place ops (`nn.ReLU(inplace=True)`, `x += y`, etc.) anywhere in the
    model crash `register_full_backward_hook` with `RuntimeError: Output 0
    of BackwardHookFunction is a view and is being modified inplace` —
    verified this is a real PyTorch constraint (full-backward hooks wrap
    outputs in a view that in-place ops then corrupt), not a bug in this
    file, and there is no workaround here: temporarily instantiate the
    module with `inplace=False` while instrumenting, or accept forward-only
    stats (register_forward_hook alone, skip grad_norm) for that module.

    ⚠️ torch.compile: hooks registered on a model AFTER it has already been
    compiled-and-called once fire ZERO times by default (PyTorch's
    `skip_nnmodule_hook_guards` defaults to True to avoid guard overhead),
    and this is indistinguishable from "no differences to report" — verified:
    stats comes back {} and diff_stats() on two such {} dicts returns [].
    By default this function refuses to instrument an already-compiled
    module and raises RuntimeError with the fix. Pass allow_compiled=True
    only after you have verified hooks actually fire for your case (e.g. you
    registered them before the first compiled call).
    """
    try:
        import torch._dynamo.eval_frame as _ef
        _hit = None
        for _n, _sub in model.named_modules():
            if isinstance(_sub, _ef.OptimizedModule) or "_orig_mod" in getattr(_sub, "_modules", {}):
                _hit = _n or "<root>"
                break
        # NOTE: the top-level hasattr(model, "_orig_mod") fallback is load-bearing
        # for FSDP(torch.compile(m)) -- FSDP.__getattr__ forwards to the wrapped
        # module so isinstance() is False there but hasattr() is True. Verified
        # 2026-08-29 on 2 GPUs. Do NOT "simplify" this to isinstance-only.
        is_compiled = _hit is not None or hasattr(model, "_orig_mod")
    except ImportError:
        is_compiled = False
        _hit = None

    if is_compiled and not allow_compiled:
        raise RuntimeError(
            "instrument() called on a torch.compile'd model "
            f"(compiled module found at: {_hit}). Hooks registered after the "
            "first compiled call fire ZERO times and this function would "
            "silently return an INCOMPLETE stats dict — verified: a single "
            "compiled submodule under a plain parent passes a naive "
            "top-level-only guard and still returns a non-empty dict (11 "
            "modules vs 13 for the identical uncompiled control), which "
            "diff_stats()'s empty-input ValueError cannot catch either "
            "(PyTorch's skip_nnmodule_hook_guards defaults to True). Fix, in "
            "order of preference: (1) register hooks BEFORE calling "
            "torch.compile(); (2) torch._dynamo.reset() then set "
            "torch._dynamo.config.skip_nnmodule_hook_guards = False (adds "
            "guard overhead); (3) instrument model._orig_mod in eager instead. "
            "Pass allow_compiled=True only once you have verified hooks "
            "actually fire for your case."
        )

    stats = {}
    handles = []

    def _forward_hook(name):
        def hook(module, inputs, output):
            import torch
            if torch.cuda.is_available() and torch.cuda.is_current_stream_capturing():
                raise RuntimeError(
                    "instrument()'s hook fired during a CUDA graph capture. Hooks "
                    "fire exactly once (now) and ZERO times on every g.replay() — "
                    "any per-step numbers you collect will be a single aliased "
                    "buffer from the last replay, not observations. Take probe "
                    "readings from a separate eager forward outside the graph. "
                    "(make_graphed_callables is NOT a fix: its hook guard only "
                    "checks the top-level module, not named_modules().)"
                )
            for path, tensor in _flatten_tensors(output):
                t = tensor.detach().float()
                stats.setdefault(name, {}).setdefault(path, {})
                entry = stats[name][path]
                entry["_n_calls"] = entry.get("_n_calls", 0) + 1
                entry["mean"] = t.mean().item()
                entry["std"] = t.std().item() if t.numel() > 1 else 0.0
                entry["zero_frac"] = (t == 0).float().mean().item()
                entry["absmax"] = t.abs().max().item()
        return hook

    def _backward_hook(name):
        def hook(module, grad_input, grad_output):
            import torch
            if torch.cuda.is_available() and torch.cuda.is_current_stream_capturing():
                raise RuntimeError(
                    "instrument()'s hook fired during a CUDA graph capture. Hooks "
                    "fire exactly once (now) and ZERO times on every g.replay() — "
                    "any per-step numbers you collect will be a single aliased "
                    "buffer from the last replay, not observations. Take probe "
                    "readings from a separate eager forward outside the graph. "
                    "(make_graphed_callables is NOT a fix: its hook guard only "
                    "checks the top-level module, not named_modules().)"
                )
            if not grad_output:
                return
            # Iterate every entry, not just index 0: a module returning
            # (aux, main) where only main requires grad produces grad_output
            # = (None, tensor) — checking only grad_output[0] silently
            # skipped the whole module. Verified 2026-08-29.
            for i, g in enumerate(grad_output):
                if g is None:
                    continue
                path = str(i)
                stats.setdefault(name, {}).setdefault(path, {})
                entry = stats[name][path]
                # Separate counter from the forward hook's _n_calls: they
                # can share this same dict (path "0" is the common case for
                # a single-tensor-output module) and forward/backward fire
                # independently, so a single shared counter would conflate
                # "called 3 times forward" with "+3 more from backward" into
                # a confusing 6.
                entry["_n_bwd_calls"] = entry.get("_n_bwd_calls", 0) + 1
                entry["grad_norm"] = g.detach().float().norm().item()
        return hook

    for name, module in model.named_modules():
        if name == "":
            continue
        handles.append(module.register_forward_hook(_forward_hook(name)))
        handles.append(module.register_full_backward_hook(_backward_hook(name)))

    return stats, handles


_ACTIVATION_MODULE_TYPES = None  # populated lazily in assert_activation_modules_visible


def assert_activation_modules_visible(model, stats):
    """P4 pre-flight guard: refuse to let a caller read dead-unit/saturation
    numbers off a model whose activations were never observed because they
    are written as functional calls (F.relu etc.) rather than nn.Module
    members. See the ⚠️ note in instrument()'s docstring for the verified
    repro. Call this once after instrument() + a forward pass, before
    trusting any zero_frac/absmax reading from `stats`.

    ⚠️ This only asserts that AT LEAST ONE activation nn.Module was
    instrumented somewhere in the model — it does NOT verify that the
    SPECIFIC activation you care about is visible. Verified: a model with
    one real nn.ReLU elsewhere and the target activation written as F.relu
    passes this assert (because the unrelated nn.ReLU was seen) while the
    target's zero_frac is still silently 0.0/meaningless. Always check that
    your specific module name is IN the returned `seen` list, don't just
    check this function didn't raise.
    """
    import torch.nn as nn

    global _ACTIVATION_MODULE_TYPES
    if _ACTIVATION_MODULE_TYPES is None:
        _ACTIVATION_MODULE_TYPES = (
            nn.ReLU, nn.GELU, nn.SiLU, nn.Sigmoid, nn.Tanh, nn.LeakyReLU, nn.ELU,
        )
    seen = [
        n for n, m in model.named_modules()
        if isinstance(m, _ACTIVATION_MODULE_TYPES) and n in stats
    ]
    assert seen, (
        "No activation nn.Modules were instrumented. Every zero_frac in this "
        "stats dict is 0.0 because the activation was never observed, not "
        "because the units are alive. Convert F.relu/F.gelu/etc. calls to "
        "nn.ReLU/nn.GELU/etc. members before reading P4 dead-unit numbers."
    )
    return seen


def diff_stats(stats_a, stats_b, key="std", path="0"):
    """Rank modules by |log ratio| of `key` (under output path `path`,
    default "0" — the first/only tensor leaf; pass e.g. "logits" or "[0]"
    for a module whose forward returns a dict/tuple with that key) between
    two stats dicts.

    Modules present in only one dict (new/removed modules) sort first —
    that alone often IS the finding (the module isn't in the other run at all).

    Raises ValueError if both dicts are empty rather than returning [] —
    an empty ranking from two genuinely-instrumented models and an empty
    ranking from two models neither of which got instrumented at all (e.g.
    both were torch.compile'd and hooks silently never fired) look
    IDENTICAL as a bare [], and the second case must not be readable as
    "no differences found".

    ⚠️ Non-finite values (NaN/Inf, i.e. a diverged or exploded module) are
    also reported as float('inf') and sort first. They are NOT run through
    the log ratio: math.log(nan) returns nan silently and Python's sort
    places NaN arbitrarily, which was verified to rank a fully-NaN'd layer
    LAST, below a layer whose std barely moved.

    ⚠️ Both-exactly-zero (e.g. a dead unit that stayed dead in both runs)
    reports 0.0 (unchanged), not float('inf') — an earlier version treated
    any zero on either side as maximally different, which put an unchanged
    dead/frozen layer at the very top of the ranking alongside genuine
    explosions. Only an ASYMMETRIC zero (one side zero, the other not) is
    reported as float('inf').

    ⚠️ Does NOT clamp small values to a fixed epsilon floor. An earlier
    version used `max(abs(v), 1e-12)` before taking the ratio; verified on
    real vanishing-gradient data (18-layer sigmoid MLP, true grad norms down
    to 1e-18) that this floor collapsed 7 of 19 layers to the same clamped
    value and INVERTED the ranking — the reported #1 was a mid-depth layer
    (true rank 5/8) while the genuinely worst layer (input layer) was ranked
    7th/8th. Values at or below `eps` (default 0, meaning "only exact zero
    is special-cased") are reported as float('inf') and sort first — visibly
    flagged as "at the edge of measurability", not silently re-scaled into
    the middle of the ranking. Pass a larger eps only if you have a specific,
    justified noise floor for your measurement.
    """
    names = set(stats_a) | set(stats_b)
    if not names:
        raise ValueError(
            "Both stats dicts are empty — this could mean the two models "
            "genuinely produced no observable difference, OR it could mean "
            "neither model was actually instrumented (e.g. both were "
            "torch.compile'd and hooks silently never fired — see "
            "instrument()'s torch.compile guard). Verify stats_a/stats_b are "
            "non-empty before calling diff_stats(), do not treat this as a "
            "negative result."
        )
    ranked = []
    for name in names:
        va = stats_a.get(name, {}).get(path, {}).get(key)
        vb = stats_b.get(name, {}).get(path, {}).get(key)
        if va is None or vb is None:
            ranked.append((name, float("inf")))
            continue
        # A NaN/Inf stat is the most severe finding available, never a
        # comparable ratio. math.log(nan) returns nan SILENTLY, and Python's
        # sort places NaN arbitrarily (all NaN comparisons are False), so a
        # fully-NaN'd layer can sort to the BOTTOM of the ranking. Verified
        # 2026-08-29: 4-layer MLP with l2/l3 activations fully NaN ranked l2
        # 4th of 4, below l0 whose std moved only 0.6489 -> 0.5984 (0.081).
        # Inf in stats_a additionally raised a bare "ValueError: math domain
        # error" from math.log(0.0), naming neither the module nor the cause.
        if not (math.isfinite(va) and math.isfinite(vb)):
            ranked.append((name, float("inf")))
            continue
        va, vb = abs(va), abs(vb)
        if va == 0.0 and vb == 0.0:
            # Both exactly zero (e.g. a dead unit / frozen constant in BOTH
            # runs) is the definition of unchanged, not "infinitely
            # different" — verified this was previously indistinguishable
            # from a genuine explosion-from/to-zero and sorted an unchanged
            # constant layer at the very top of the ranking.
            ranked.append((name, 0.0))
            continue
        if va == 0.0 or vb == 0.0:
            ranked.append((name, float("inf")))
            continue
        ranked.append((name, abs(math.log(vb / va))))
    # Keep the sort total even though no NaN can reach here now: a caller
    # injecting one must not silently scramble the whole ranking.
    ranked.sort(key=lambda x: (0 if math.isnan(x[1]) else 1, x[1]), reverse=True)
    return ranked


def assert_new_params_registered(base_model, candidate_model):
    """P1: the new module's parameters must actually be registered.

    ⚠️ base_model and candidate_model must be the SAME architecture except
    for the component under test — e.g. candidate_model = base_model's class
    with the new submodule added, not two unrelated models. If the two
    models differ structurally for any other reason (different attribute
    names for pre-existing layers, etc.), the naive name-set diff below will
    report those unrelated differences as "new parameters" too, which can
    mask the actual bug (verified empirically: comparing a bare
    nn.Sequential(nn.Linear(...)) against a class with a differently-named
    nn.Linear as its first layer makes an unrelated, correctly-registered
    layer look like "the new parameters", swamping a genuinely missing
    registration elsewhere in the diff).

    Raises AssertionError with a diagnostic message rather than returning
    False — a silent False here is exactly the kind of "looks fine" result
    this skill exists to prevent.
    """
    base_names = set(dict(base_model.named_parameters()))
    cand_names = set(dict(candidate_model.named_parameters()))
    new_names = cand_names - base_names
    assert new_names, (
        "No new parameters found on the candidate model. Common cause: the "
        "new submodule is stored in a plain list/dict instead of "
        "nn.ModuleList/nn.ModuleDict, or a raw tensor instead of nn.Parameter — "
        "it will not raise an error, will not appear in state_dict(), and the "
        "optimizer will silently never update it."
    )
    return new_names


def assert_gradients_reach(model, new_param_names):
    """P2: call this AFTER loss.backward() has already run (this function
    does not call backward itself — doing so would try to walk a graph
    whose intermediate tensors have already been freed, and would crash
    with "Trying to backward through the graph a second time").

    Returns the list of new-module parameter names whose .grad is still
    None.

    SCOPE (narrower than it looks — verified against a real LoRA zero-init
    case): this catches only params that never entered the autograd graph
    at all (registered but unused in forward, or detached upstream). It does
    NOT report zero-valued gradients — with LoRA A=random/B=0,
    `grad(A) = s * B^T * G^T * x` is an EXACT ZERO TENSOR (not None) whenever
    B=0, so this function returns [] and never names the A parameter. A None
    grad still does not by itself mean "broken" (ControlNet zero-conv
    upstream can legitimately be None at step 0) — check the ⚠️ zero-init
    note in mechanistic-diagnosis.md. And an EMPTY return does not mean
    "wired correctly" either: verified that a zero-init parameter silently
    left out of the optimizer's param group also returns [] forever while
    the branch stays a permanent no-op (measured: loss bit-identical across
    3 steps, output delta 0.000e+00, this function returning [] every step —
    exactly the same signature as the healthy case). Use
    assert_zero_init_unlocked() below to actually distinguish the two.
    """
    _refuse_if_sharded(model, "assert_gradients_reach")
    known = set(dict(model.named_parameters()))
    unknown = set(new_param_names) - known
    if unknown:
        raise KeyError(
            f"new_param_names not present on the model: {sorted(unknown)}. "
            f"Verified that a typo'd name returns in_optimizer={{}} plus an "
            f"empty grad history — i.e. EXACTLY the signature of the "
            f"permanent-no-op failure these probes exist to detect — while "
            f"assert_gradients_reach() returns [] and sgd_update_proxy() "
            f"returns {{}} ('all healthy') for the same input."
        )
    missing = [
        n for n, p in model.named_parameters()
        if n in new_param_names and p.grad is None
    ]
    return missing


def assert_zero_init_unlocked(model, param_names, optimizer, n_steps, step_fn):
    """Distinguishes "healthy zero-init branch, not yet unlocked" from
    "permanent no-op because a zero-init parameter never entered the
    optimizer" — assert_gradients_reach() alone cannot tell these apart
    (both read as "no None grads reported" / a stable loss).

    step_fn(): a zero-arg callable that runs one full train step (zero_grad,
    forward, backward, optimizer.step()) and returns the scalar loss value.
    Runs it n_steps times (use 2-3, per the "check after a couple of
    optimizer steps" guidance repeated across this skill's references) and
    reports, per named parameter, the gradient norm history and whether the
    optimizer's param groups actually contain that parameter.

    Verified case: a healthy zero-init branch (e.g. LoRA B, or a
    downstream factor that only receives gradient once its own upstream
    zero-init gate moves) shows |grad| becoming nonzero within a few steps
    (measured 5.23e-02 by step 1 in the healthy case); a parameter silently
    missing from the optimizer shows |grad| staying at the SAME value (often
    zero, but not necessarily) across all n_steps AND is absent from
    `in_optimizer`.
    """
    _refuse_if_sharded(model, "assert_zero_init_unlocked")
    known = set(dict(model.named_parameters()))
    unknown = set(param_names) - known
    if unknown:
        raise KeyError(
            f"param_names not present on the model: {sorted(unknown)}. "
            f"Verified that a typo'd name returns in_optimizer={{}} plus an "
            f"empty grad history — i.e. EXACTLY the signature of the "
            f"permanent-no-op failure these probes exist to detect — while "
            f"assert_gradients_reach() returns [] and sgd_update_proxy() "
            f"returns {{}} ('all healthy') for the same input."
        )
    if n_steps < 1:
        raise ValueError("n_steps must be >= 1 — n_steps=0 silently returns a "
                          "fully legal-looking empty-history dict with no warning.")

    tracked_ids = {id(p) for group in optimizer.param_groups for p in group["params"]}
    in_optimizer = {
        n: id(p) in tracked_ids
        for n, p in model.named_parameters() if n in param_names
    }
    grad_norm_history = {n: [] for n in param_names}
    losses = []
    try:
        for _ in range(n_steps):
            losses.append(step_fn())
            for n, p in model.named_parameters():
                if n in param_names:
                    grad_norm_history[n].append(
                        p.grad.norm().item() if p.grad is not None else None
                    )
    except Exception as e:
        # A raising step_fn must still surface the partial history — without
        # this, the caller cannot distinguish "unlocked before the crash"
        # from "never unlocked" (grad_norm_history/losses were function-locals
        # and would simply be discarded by the propagating exception).
        e.partial_result = {
            "in_optimizer": in_optimizer,
            "grad_norm_history": grad_norm_history,
            "losses": losses,
        }
        raise
    return {
        "in_optimizer": in_optimizer,
        "grad_norm_history": grad_norm_history,
        "losses": losses,
    }


def sgd_update_proxy(model, param_names, lr):
    """P3 (approximate, SGD-only): cs231n's update:weight heuristic, computed
    as lr*grad BEFORE optimizer.step() actually runs. This is a proxy, not a
    measurement — for adaptive optimizers (Adam, etc.) the real per-parameter
    step size also depends on the optimizer's running moment estimates, which
    this formula ignores entirely, so it can be wrong by a large factor under
    Adam. Use `measure_real_update()` below when you need a number you can
    trust rather than a quick relative signal. There is no universally "safe"
    threshold across models/optimizers/tasks — treat 1e-3 as a starting point
    to compare against, not a pass/fail line.

    A parameter with weight_norm exactly 0.0 (e.g. ReZero's alpha, LoRA's B,
    a zero-init conv) reports float('inf') rather than dividing by a small
    floor — verified that a `max(weight_norm, 1e-12)` floor reports ~7.7e11
    for a legitimately, healthily zero-initialized parameter, which reads as
    a catastrophic explosion when it is actually the expected starting state.
    update:weight is genuinely undefined at weight_norm=0, not "very large".
    """
    _refuse_if_sharded(model, "sgd_update_proxy")
    known = set(dict(model.named_parameters()))
    unknown = set(param_names) - known
    if unknown:
        raise KeyError(
            f"param_names not present on the model: {sorted(unknown)}. "
            f"Verified that a typo'd name returns in_optimizer={{}} plus an "
            f"empty grad history — i.e. EXACTLY the signature of the "
            f"permanent-no-op failure these probes exist to detect — while "
            f"assert_gradients_reach() returns [] and sgd_update_proxy() "
            f"returns {{}} ('all healthy') for the same input."
        )
    ratios = {}
    for name, p in model.named_parameters():
        if name not in param_names or p.grad is None:
            continue
        weight_norm = p.data.norm().item()
        if weight_norm == 0.0:
            ratios[name] = float("inf")
            continue
        update_norm = (lr * p.grad).norm().item()
        ratios[name] = update_norm / weight_norm
    return ratios


def snapshot_params(model, param_names):
    """First half of measure_real_update(): call before optimizer.step().

    Validates param_names against the model rather than silently dropping
    typos: a typo'd name here vanishes from the returned snapshot, and
    measure_real_update() only iterates names present in the snapshot dict —
    so the missing parameter is skipped with no error, indistinguishable
    from "this parameter didn't need checking" (same failure family as the
    zero-init probes' typo guard above).
    """
    _refuse_if_sharded(model, "snapshot_params")
    known = set(dict(model.named_parameters()))
    unknown = set(param_names) - known
    if unknown:
        raise KeyError(f"param_names not present on the model: {sorted(unknown)}.")
    return {n: p.data.clone() for n, p in model.named_parameters() if n in param_names}


def measure_real_update(model, before_snapshot):
    """P3 (exact, any optimizer): call AFTER optimizer.step(). Returns the
    actual ||update||/||weight|| per parameter, capturing whatever the
    optimizer really did (Adam's per-parameter preconditioning, weight decay,
    gradient clipping, LR schedule) instead of approximating it from the raw
    gradient. Pair with snapshot_params() taken before optimizer.step().

    Same zero-weight handling as sgd_update_proxy(): weight_norm==0.0 (before
    the step) reports float('inf'), not a value computed against a 1e-12
    floor.
    """
    _refuse_if_sharded(model, "measure_real_update")
    ratios = {}
    for name, p in model.named_parameters():
        if name not in before_snapshot:
            continue
        before = before_snapshot[name]
        weight_norm = before.norm().item()
        if weight_norm == 0.0:
            ratios[name] = float("inf")
            continue
        update_norm = (p.data - before).norm().item()
        ratios[name] = update_norm / weight_norm
    return ratios


def effective_rank(z):
    """P7 RankMe (label-free): effective_rank = exp(entropy of normalized
    singular values). Use only as a relative signal between baseline and
    modified runs on the SAME batch — not as an absolute threshold; it is
    less discriminative on datasets with very few classes.

    ⚠️ `z` MUST be a single 2-D matrix (N samples x D features) — this
    function raises ValueError on anything else rather than silently doing
    the wrong thing. Verified: `torch.linalg.svdvals` broadcasts over a
    leading batch dim, and summing across the whole batched result before
    normalizing treats ALL matrices' singular values as one distribution —
    3 identical rank-2 (4x4) matrices stacked into a (3,4,4) batch returned
    6.000001 (a plausible-looking number, not an error) instead of the
    correct per-matrix rank of 2.0. If your hidden states are
    [batch, seq, dim] and you want a single RankMe number over all
    (sample, token) rows, reshape explicitly first:
    `effective_rank(z.reshape(-1, z.shape[-1]))` — that is a real design
    decision (pools tokens and batch into one N x D matrix), not something
    this function should default to silently.

    Degenerate inputs (all-zero, or any non-finite values) return 0.0 rather
    than NaN — an all-zero activation is itself a P4 dead-unit finding, not a
    numerical error, and letting it silently NaN through a downstream
    comparison is worse than making the degenerate case an explicit 0.
    """
    import torch

    if z.dim() != 2:
        raise ValueError(
            f"effective_rank() requires a 2-D (N, D) matrix, got shape "
            f"{tuple(z.shape)}. torch.linalg.svdvals silently broadcasts over "
            f"a leading batch dim and combining the batched singular values "
            f"before normalizing gives a plausible-looking but wrong number "
            f"(verified: 3 identical rank-2 matrices -> 6.000001, not 2.0). "
            f"Reshape explicitly, e.g. z.reshape(-1, z.shape[-1]) if you want "
            f"one RankMe number pooling batch and sequence together."
        )
    s = torch.linalg.svdvals(z)
    total = s.sum()
    if not torch.isfinite(total) or total <= 0:
        return 0.0
    p = s / total
    p = p[p > 0]  # drop exact zeros before log to avoid 0*log(0) -> nan
    return torch.exp(-(p * p.log()).sum()).item()


def attention_entropy(attn_weights, eps=1e-12):
    """P6: per-query-row entropy of an attention probability matrix,
    Ent(A_i) = -sum_j A_ij log A_ij, averaged per head then across heads.

    `attn_weights`: a tensor whose LAST dimension is the softmax'd attention
    distribution over keys (any number of leading dims — batch/head/query
    are all averaged over). Must be actual per-head probabilities, not
    already averaged across heads (see the ⚠️ note below) and must come from
    an eager/math attention implementation — verified that
    F.scaled_dot_product_attention returns only the output tensor (no
    weights) and nn.MultiheadAttention needs attn_implementation="eager" /
    need_weights=True to materialize this at all.

    ⚠️ eps is required, not optional decoration: verified that the naive
    `-(A * A.log()).sum(-1)` returns NaN whenever any row has a probability
    that underflows to exactly 0.0 in floating point — which happens exactly
    in the fully-collapsed regime this probe exists to detect (measured:
    1024/1024 rows NaN at qkv init std=2.0 in fp32; fp16 underflows even
    earlier). The eps-guarded version differs from the true entropy by at
    most ~6e-8 wherever both are finite, so there is no accuracy cost to
    always including it.

    ⚠️ If you only have nn.MultiheadAttention's default
    average_attn_weights=True output, do NOT feed it here as if it were
    per-head: averaging weights before computing entropy is a Jensen's-
    inequality upper bound on the true mean per-head entropy, not the same
    quantity. Verified: a random-init case reads +0.086 nats (+2.6%) high;
    a worst case with several heads each fully collapsed onto a different
    token reads back log(L) (fully "healthy"-looking) when the true per-head
    entropy of every one of those heads is exactly 0 — a completely collapsed
    case reported as maximally healthy. Pass average_attn_weights=False (or
    the equivalent for your attention implementation) and compute entropy
    per head before any averaging.

    Returns entropy in nats. Compare against log(L) (L = number of keys) for
    a fraction-of-maximum reading, but judge by baseline-vs-modified delta,
    not an absolute threshold — a healthy, well-converging model can
    legitimately end training well below its initial entropy (verified: a
    healthy run's entropy fell from 3.41 to 1.67 nats, a 51% drop, with loss
    improving 27x and no divergence).
    ⚠️ Does not silently accept a non-probability input: verified that
    garbage weights like `[-1, 2]` (negative and >1, sum != 1 — e.g. logits
    that were never actually softmax'd, a common mistake when patching in a
    debug hook) fed through unclamped-except-for-eps naive entropy return a
    plausible-looking NEGATIVE number (-1.386) instead of an error — negative
    entropy is meaningless but doesn't look obviously wrong. Now raises
    ValueError if the last-dim rows are not valid probabilities (all in
    [0,1] and summing to ~1) rather than reporting a number that reads as
    "some kind of low entropy" when it's actually "not entropy at all".
    """
    import torch

    if (attn_weights < -1e-6).any() or (attn_weights > 1 + 1e-6).any():
        raise ValueError(
            "attn_weights contains values outside [0,1] — this is not a "
            "softmax'd probability distribution (did you pass raw logits, "
            "or attention scores before softmax?). Entropy on non-"
            "probabilities is meaningless; verified it silently returns a "
            "plausible-looking negative number instead of erroring."
        )
    row_sums = attn_weights.sum(dim=-1)
    if not torch.allclose(row_sums, torch.ones_like(row_sums), atol=1e-3):
        raise ValueError(
            f"attn_weights rows do not sum to ~1 (min={row_sums.min().item():.4f}, "
            f"max={row_sums.max().item():.4f}) — this does not look like a "
            f"softmax'd probability distribution over keys."
        )
    p = attn_weights.clamp(min=eps)
    ent = -(p * p.log()).sum(dim=-1)
    return ent.mean().item()


def ceiling_gap(mse_base, mse_shifted_forward):
    """B4a leakage/causality probe (borrow-existing-pipeline.md): the ONE of
    the three shift probes with real discriminative power, verified on a
    synthetic causal task (1566-6315x for a correctly-wired causal model,
    0.7-1.6x for a model with a real off-by-one leakage bug, 3 seeds, zero
    overlap between the two distributions).

    Shift the target forward by one step so it falls inside the model's own
    input window (the task degenerates toward a copy problem), retrain/
    re-evaluate, and compare MSE before vs after the shift. This measures
    the pipeline's ceiling on this data, not whether the change helped:

    - ceiling_gap >> 1 (orders of magnitude): wiring is causal as intended —
      giving the model the answer inside its own input produces a dramatic,
      measurable improvement, because it genuinely couldn't see it before.
    - ceiling_gap ~= 1: the input window ALREADY contains (a proxy for) the
      target — i.e. leakage. Giving the model an even-more-explicit copy of
      information it already effectively had changes nothing.

    Do NOT use the backward-shift/shuffle variants as a leakage gate: they
    were verified to have the opposite failure directions on the same
    synthetic task — backward-shift can make a CORRECT pipeline degrade far
    short of the trivial baseline (a healthy AR(1) predictor's R^2 dropped
    from 0.629 to only 0.395, nowhere near the trivial-baseline floor) while
    simultaneously making a LEAKY pipeline look healthy (R^2 0.626, nearly
    identical to the correct pipeline's own 0.629) — i.e. it can clear a
    leaky pipeline as clean. Shuffle showed near-zero discriminative power in
    the same experiment (correct -0.021 vs leaky -0.018, smaller than the
    0.005-0.009 seed noise). Both remain useful for calibrating what the
    trivial baseline looks like and confirming the metric is wired to the
    target at all — just not as the leakage judgment itself.

    Raises ValueError on a NaN input rather than silently propagating NaN
    through the division (`NaN / x` and `x / NaN` are both NaN with no
    exception) — a NaN MSE means the eval run itself diverged/crashed, which
    is a different, more urgent finding than "inconclusive ceiling_gap".
    """
    if math.isnan(mse_base) or math.isnan(mse_shifted_forward):
        raise ValueError(
            f"ceiling_gap got a NaN input ({mse_base=}, {mse_shifted_forward=}). "
            f"This means one of the two eval runs diverged/crashed, not that "
            f"the leakage probe is inconclusive — fix the NaN run first, do "
            f"not read a NaN ceiling_gap as any kind of leakage signal."
        )
    if mse_shifted_forward <= 0:
        return float("inf")
    return mse_base / mse_shifted_forward
