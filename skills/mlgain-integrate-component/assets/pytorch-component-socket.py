"""Reference implementation of the ComponentSocket pattern.

See references/function-preserving-socket-protocol.md for the full S0-S4
verification protocol this class is designed to support, and
references/residual-gating-safe-integration.md for when RESIDUAL mode is
(and is not) an appropriate default.

This file is a TEMPLATE to copy and adapt, not a library to import as-is:
real projects must replace **context with an explicit, named signature
(mask/lengths/etc per your task's contract) instead of blind-passing kwargs,
and must pick the scale's broadcast dimension from the component's actual
contract rather than assuming channel is the last dim.
"""
from enum import Enum

import torch
from torch import nn


def _assert_contract(z: torch.Tensor, base: torch.Tensor, where: str) -> None:
    """Shape-only checking silently passes a dtype/device mismatch: verified
    a float32 base + float64 candidate passes `z.shape == base.shape` and
    the socket then silently returns float64 (the base's precision is lost,
    not an error). Also checks device and memory layout for the same reason
    — none of these are implied by shape equality.
    """
    if z.shape != base.shape:
        raise RuntimeError(f"{where}: shape mismatch {z.shape=} != {base.shape=}")
    if z.dtype != base.dtype:
        raise RuntimeError(f"{where}: dtype mismatch {z.dtype=} != {base.dtype=}")
    if z.device != base.device:
        raise RuntimeError(f"{where}: device mismatch {z.device=} != {base.device=}")
    if z.layout != base.layout:
        raise RuntimeError(f"{where}: layout mismatch {z.layout=} != {base.layout=}")


class SocketMode(str, Enum):
    BASELINE = "baseline"  # candidate is not executed at all (hard bypass, S1)
    REPLACE = "replace"    # candidate's output replaces the base path entirely
    RESIDUAL = "residual"  # base + scale(candidate) — only for same-shape additive corrections


class ResidualScale(nn.Module):
    """Zero- or small-epsilon-initialized learnable scale for safe residual
    integration. init=0.0 reproduces ReZero (exact identity at init, first-step
    gradient to the candidate's own parameters is zero by design — see the
    ⚠️ note in mechanistic-diagnosis.md before treating that as a wiring bug).
    A small positive init (e.g. 1e-4 to 1e-6) with channels=<feature_dim>
    reproduces LayerScale (not exactly zero, but gives the branch a nonzero
    gradient from step 0).
    """

    def __init__(self, channels: int | None = None, init: float = 0.0):
        super().__init__()
        shape = () if channels is None else (channels,)
        self.value = nn.Parameter(torch.full(shape, init))

    def forward(self, z: torch.Tensor) -> torch.Tensor:
        scale = self.value
        while scale.ndim < z.ndim:
            scale = scale.unsqueeze(0)
        return z * scale


class ComponentSocket(nn.Module):
    """base_path and candidate must satisfy the same output contract
    (shape/dtype) — this is NOT auto-detected; state it explicitly in your
    project's contract doc and let `assert z.shape == base.shape` below
    catch violations at forward time (it is not a substitute for the
    construction-time assert required by framework-placement-conventions.md
    — add that too, in your subclass).
    """

    def __init__(
        self,
        base_path: nn.Module,
        candidate: nn.Module,
        pre_adapter: nn.Module | None = None,
        post_adapter: nn.Module | None = None,
        scale: nn.Module | None = None,
    ):
        super().__init__()
        self.base_path = base_path
        self.candidate = candidate
        self.pre_adapter = pre_adapter or nn.Identity()
        self.post_adapter = post_adapter or nn.Identity()
        self.scale = scale or ResidualScale(init=0.0)
        self._mode = SocketMode.BASELINE

    @property
    def mode(self) -> SocketMode:
        return self._mode

    @mode.setter
    def mode(self, value) -> None:
        # Coerce through SocketMode(...) rather than comparing with `is`:
        # SocketMode inherits (str, Enum), so a plain string like "baseline"
        # is == SocketMode.BASELINE but is NOT the same object — an `is`
        # comparison against a caller-supplied string silently falls through
        # to the RESIDUAL branch below instead of hard-bypassing, which
        # defeats the whole point of S1. Coercing here means every read of
        # self.mode downstream is guaranteed a real SocketMode member, and an
        # unrecognized string fails loudly at assignment time instead of
        # silently misrouting at forward time.
        self._mode = SocketMode(value)

    def forward(self, x: torch.Tensor, **context) -> torch.Tensor:
        # Do NOT call base_path before checking mode. REPLACE mode discards
        # base's output, but EXECUTING it still has side effects: verified
        # that nn.BatchNorm1d(4) as base_path moves running_mean from
        # [0,0,0,0] to [0.0194,-0.0342,0.0237,-0.0063] and
        # num_batches_tracked 0->1 after a single REPLACE forward pass; a
        # dropout layer in base_path would likewise consume RNG state, making
        # REPLACE's output != a standalone call to candidate (same seed).
        # Both effects silently break the single-variable premise that
        # function-preserving-socket-protocol.md's S2/S3 depend on.
        if self.mode == SocketMode.BASELINE:
            return self.base_path(x, **context)  # hard bypass: candidate never runs
        z = self.post_adapter(self.candidate(self.pre_adapter(x), **context))
        if self.mode == SocketMode.REPLACE:
            return z  # base_path deliberately NOT executed: no state/RNG side effects
        base = self.base_path(x, **context)
        _assert_contract(z, base, "forward/RESIDUAL")
        out = base + self.scale(z)
        if out.shape != base.shape:
            raise RuntimeError(
                f"scale broadcast changed the socket's output shape: "
                f"{base.shape=} -> {out.shape=} (scale param shape "
                f"{tuple(self.scale.value.shape)}). The z/base contract check "
                f"above runs BEFORE the scale is applied, so it cannot catch "
                f"this: verified 2026-08-29 that a 0-dim base output with "
                f"ResidualScale(channels=4) passes the check and then returns "
                f"a (4,) tensor, breaking S1 identity even at init=0.0."
            )
        return out

    @torch.no_grad()
    def check_contract(self, x: torch.Tensor, **context) -> None:
        """forward() no longer runs base_path in REPLACE mode, so the shape
        contract between candidate and base_path is not checked on every
        forward call in that mode. Call this once during S7 integration
        coding to verify it explicitly — do not call it inside a training
        loop.

        Forces the WHOLE socket (base_path, candidate and adapters) to
        eval() — a BatchNorm in the *candidate* updates its running stats too
        (verified `running_mean [0,0,0,0] -> [-0.0608, 0.0714, -0.0351,
        -0.0056]` under an earlier base-only guard). Restores each
        submodule's training flag individually, because a recursive
        `.train(was_training)` silently un-freezes a deliberately frozen
        BatchNorm nested inside base_path (standard in finetuning/detection
        backbones). Saves/restores the global RNG state, because a Dropout
        anywhere in the socket otherwise consumes RNG and breaks the
        same-seed single-variable premise S2/S3 depend on (verified same-seed
        forward divergence of max|Δ|=3.4741 from a single check_contract()
        call). Also mirrors torch.cuda.get_rng_state_all()/set_rng_state_all()
        when CUDA is available — an earlier version had this sentence in the
        docstring but never actually called the CUDA RNG functions, so a
        stochastic candidate running on GPU still leaked CUDA RNG state
        despite the CPU RNG being correctly saved/restored.
        """
        prev = {mod: mod.training for mod in self.modules()}
        rng = torch.get_rng_state()
        cuda_rng = torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None
        self.eval()  # base_path AND candidate/adapters
        try:
            base = self.base_path(x, **context)
            z = self.post_adapter(self.candidate(self.pre_adapter(x), **context))
            _assert_contract(z, base, "check_contract")
            out = base + self.scale(z)
            if out.shape != base.shape:
                raise RuntimeError(
                    f"scale broadcast changed the socket's output shape: "
                    f"{base.shape=} -> {out.shape=} (scale param shape "
                    f"{tuple(self.scale.value.shape)})."
                )
        finally:
            for mod, was in prev.items():
                mod.training = was  # per-module, not recursive .train()
            torch.set_rng_state(rng)
            if cuda_rng is not None:
                torch.cuda.set_rng_state_all(cuda_rng)
