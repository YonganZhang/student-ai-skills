"""Template test suite for a ComponentSocket integration point.

Copy this file to your project's tests/, replace the `TODO` fixtures with
your actual base_path/candidate/socket, and delete any test that genuinely
does not apply (e.g. test_future_perturbation_does_not_change_past_outputs
only applies to causal/sequential tasks) — do not delete a test just
because it currently fails; a failing test here means the socket is not
correctly wired, not that the test is wrong.

Run with: pytest test_component_socket.py -v
"""
import pytest
import torch

# TODO: replace with your real modules and socket.
# from my_project.sockets import build_socket
# from pytorch_component_socket import SocketMode


@pytest.fixture
def socket_and_input():
    raise NotImplementedError(
        "TODO: return (socket, x) where socket is a ComponentSocket wired "
        "with your real base_path/candidate, and x is a representative "
        "input batch."
    )


def test_baseline_mode_does_not_call_candidate(socket_and_input):
    """S1 hard bypass: candidate must not even be invoked."""
    socket, x = socket_and_input
    calls = {"n": 0}
    original_forward = socket.candidate.forward

    def counting_forward(*a, **kw):
        calls["n"] += 1
        return original_forward(*a, **kw)

    socket.candidate.forward = counting_forward
    socket.mode = "baseline"
    socket(x)
    assert calls["n"] == 0, "candidate was invoked in BASELINE mode"


def test_same_checkpoint_bypass_output_parity(socket_and_input):
    """S1 parity: bypass output must exactly match base_path alone.

    Calls `.eval()` before comparing: `torch.no_grad()` alone does not
    disable Dropout or freeze BatchNorm running stats, so calling the socket
    and then base_path again — two SEPARATE forward passes — draws two
    independent dropout masks even for a genuinely correct socket. Verified:
    a correct socket with an `nn.Dropout` inside base_path failed this
    parity check with max|Δ|=2.0 purely from that, with no wiring bug at
    all. This test is about structural identity (does BASELINE mode really
    just call base_path), not about reproducing stochastic behavior — eval()
    removes the confound.
    """
    socket, x = socket_and_input
    socket.mode = "baseline"
    socket.eval()
    with torch.no_grad():
        out = socket(x)
        base_out = socket.base_path(x)
    assert torch.allclose(out, base_out, atol=1e-6)


def test_zero_merge_initial_output_parity(socket_and_input):
    """S2 enabled no-op: with a zero-initialized gate/scale, RESIDUAL mode
    must reproduce the baseline output at init (ReZero property).

    Calls `.eval()` for the same reason as test_same_checkpoint_bypass_
    output_parity above — two separate stochastic forward passes will
    disagree even when the socket is wired correctly.
    """
    socket, x = socket_and_input
    socket.mode = "residual"
    socket.eval()
    with torch.no_grad():
        out = socket(x)
        base_out = socket.base_path(x)
    assert torch.allclose(out, base_out, atol=1e-3), (
        "residual merge with zero-init scale did not reproduce baseline — "
        "check that the gate/scale parameter is actually initialized to zero "
        "and that no other layer (e.g. a norm inside the candidate) is "
        "silently contributing."
    )


def test_batch_axis_does_not_mix_samples(socket_and_input):
    """A change to sample i's input must not change sample j's output —
    catches accidental cross-batch mixing (e.g. a misplaced reshape/transpose,
    or a normalization computed over the wrong axis).

    Runs in REPLACE mode, not RESIDUAL: a zero-initialized residual gate
    (the RESIDUAL-mode default per residual-gating-safe-integration.md)
    would multiply the candidate's output by ~0, so a real cross-batch-mixing
    bug inside the candidate would be masked and this test would pass for
    the wrong reason. REPLACE mode exercises the candidate's raw output
    directly.
    """
    socket, x = socket_and_input
    socket.mode = "replace"
    with torch.no_grad():
        out_full = socket(x)
        x_perturbed = x.clone()
        x_perturbed[0] = torch.randn_like(x_perturbed[0])
        out_perturbed = socket(x_perturbed)
    assert torch.allclose(out_full[1:], out_perturbed[1:], atol=1e-5), (
        "perturbing sample 0 changed other samples' outputs — batch axis is "
        "being mixed somewhere in the candidate or its adapters."
    )


def test_padding_values_do_not_change_valid_outputs():
    raise NotImplementedError(
        "TODO: project-specific — pad a batch, change only the padded "
        "positions' values, assert valid-position outputs are unchanged."
    )


def test_future_perturbation_does_not_change_past_outputs():
    raise NotImplementedError(
        "TODO: causal tasks only — perturb a future timestep's input, "
        "assert earlier timesteps' outputs are unchanged. See "
        "borrow-existing-pipeline.md P4's leakage/causal probe for the "
        "same idea applied at the pipeline level."
    )


def test_expected_first_step_gradient_pattern(socket_and_input):
    """See residual-gating-safe-integration.md: zero-init schemes have a
    KNOWN first-step gradient pattern (e.g. ReZero's alpha has a gradient,
    F's own params do not, yet). Assert the pattern you expect, not a blanket
    "no gradients should be zero"."""
    socket, x = socket_and_input
    socket.mode = "residual"
    loss = socket(x).sum()
    loss.backward()
    # TODO: replace with the actual expected pattern for your merge/init scheme
    raise NotImplementedError("TODO: assert the specific expected grad pattern")


def test_branch_gradients_after_gate_unlock(socket_and_input):
    """Run 2-3 optimizer steps, then confirm the candidate's own parameters
    now receive gradient (the gate/scale should have moved away from exact
    zero by then, for schemes that start at zero)."""
    raise NotImplementedError(
        "TODO: project-specific — needs an optimizer wired to the socket's "
        "parameters; run a few steps then re-check .grad on candidate params."
    )


def test_candidate_parameters_are_in_optimizer_once(socket_and_input):
    """P1 from mechanistic-diagnosis.md: every candidate parameter must
    appear in exactly one optimizer param group — not zero (never updated),
    not more than one (double-updated)."""
    raise NotImplementedError(
        "TODO: project-specific — needs the real optimizer; count "
        "occurrences of each candidate parameter's id() across all "
        "optimizer.param_groups[*]['params']."
    )


@pytest.fixture
def fresh_socket_same_architecture():
    raise NotImplementedError(
        "TODO: return a NEW ComponentSocket instance with the same "
        "architecture as socket_and_input's socket, but with independently "
        "(randomly) initialized parameters — e.g. re-run the same "
        "construction code with a different seed. This must be a distinct "
        "object with different starting weights, not the same instance."
    )


def test_train_eval_and_state_dict_roundtrip(socket_and_input, fresh_socket_same_architecture):
    """A socket's state_dict() must be loadable into a FRESH, differently
    initialized instance of the same architecture and reproduce identical
    output — not just survive a save/load cycle on the same object (which is
    close to tautological, since the object's parameters never left memory).
    Also exercises .train()/.eval() switching around the load.
    """
    socket, x = socket_and_input
    other = fresh_socket_same_architecture
    socket.mode = "residual"
    other.mode = "residual"
    socket.eval()
    other.eval()
    # Check the STATE DICTS differ, not the outputs: in RESIDUAL mode with a
    # zero-initialized gate/scale, the candidate's output is deliberately
    # multiplied by ~0 (S1/ReZero property) — an independently-initialized
    # `other` whose base_path happens to match `socket`'s can legitimately
    # produce an IDENTICAL output before loading even though its candidate's
    # weights genuinely differ, which would make an output-based precondition
    # check falsely fire (or falsely pass) depending on which parameters
    # happened to be shared. Comparing tensors directly is not sensitive to
    # the merge mode at all.
    socket_sd, other_sd = socket.state_dict(), other.state_dict()
    assert set(socket_sd) == set(other_sd), "fixtures must share the same architecture (state_dict keys differ)"
    assert any(not torch.equal(socket_sd[k], other_sd[k]) for k in socket_sd), (
        "the fresh instance's state_dict is identical to socket's before "
        "loading — it isn't actually independently initialized, so this "
        "test can't detect a broken roundtrip either way."
    )
    with torch.no_grad():
        out_before = socket(x)
    other.load_state_dict(socket.state_dict())
    other.eval()
    with torch.no_grad():
        out_after = other(x)
    assert torch.allclose(out_before, out_after, atol=1e-6)


def test_fp32_and_amp_contract():
    raise NotImplementedError(
        "TODO: project-specific — run once under plain fp32 and once under "
        "torch.autocast; assert no dtype-mismatch error and outputs agree "
        "within a loose tolerance (autocast intentionally changes numerics)."
    )


def test_v1_v2_share_identical_adapter_and_merge_manifest():
    raise NotImplementedError(
        "TODO: project-specific — load component-integration-manifest.yaml "
        "for both v1 and v2 of the candidate, assert `adapter` and `merge` "
        "sections are byte-identical. If they differ, the v1-vs-v2 "
        "comparison is confounded by the adapter/merge change, not just the "
        "component's own version — see controlled-comparison.md."
    )
