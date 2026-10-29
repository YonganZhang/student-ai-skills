"""Behaviour tests for module_probe.py, alignment_probe.py and train_sanity_checks.py on toy models (CPU, seconds).

Run (any interpreter with torch, numpy and scipy; tests skip cleanly when they are missing):
  CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=4 <python> -m unittest discover -s skills/mlgain-integrate-component/tests -v
"""
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
EXPOSURE_CLI_DIR = Path(__file__).resolve().parents[2] / 'share-autoresearch-engine' / 'scripts'
HAS_TORCH = importlib.util.find_spec('torch') is not None
HAS_NUMPY = all(importlib.util.find_spec(m) is not None for m in ('numpy', 'scipy'))

if HAS_TORCH:
    import torch
    from torch import nn

    import module_probe as mp
    import train_sanity_checks as tsc
if HAS_NUMPY:
    import numpy as np

    import alignment_probe as ap


def toy(scale_init=0.0):
    torch.manual_seed(0)
    sock = mp.ResidualSocket(nn.Sequential(nn.Conv2d(4, 4, 3, padding=1), nn.ReLU(), nn.Conv2d(4, 4, 1)),
                             scale_init=scale_init)
    model = nn.Sequential(nn.Conv2d(1, 4, 3, padding=1), sock, nn.Conv2d(4, 1, 1))
    return model, sock


def modes(model):
    return [m.training for m in model.modules()]


def mixed_mode(build):
    """A model in the common fine-tuning state: train() overall, one frozen BatchNorm kept in eval()."""
    model = build().train()
    bn = next(m for m in model.modules() if isinstance(m, nn.modules.batchnorm._BatchNorm))
    bn.eval()
    return model


class Boom(nn.Module):
    """Raises in forward; only in train() mode when train_only is set (after earlier layers updated BN buffers)."""

    def __init__(self, train_only=False):
        super().__init__()
        self.train_only = train_only

    def forward(self, x):
        if self.training or not self.train_only:
            raise RuntimeError('boom')
        return x


@unittest.skipUnless(HAS_TORCH, 'torch not installed')
class ModuleProbeTest(unittest.TestCase):
    def test_parity_zero_at_init_and_nonzero_when_open(self):
        model, sock = toy(0.0)
        x = torch.randn(2, 1, 16, 16)
        self.assertEqual(mp.step0_parity(model, [sock], x), 0.0)
        model2, sock2 = toy(0.5)
        self.assertGreater(mp.step0_parity(model2, [sock2], x), 0.0)

    def test_bypass_skips_branch_and_restores(self):
        model, sock = toy(0.5)
        called = []
        sock.branch.register_forward_hook(lambda *a: called.append(1))
        with mp.bypassed(model, [sock]):
            model(torch.randn(1, 1, 8, 8))
        self.assertEqual(called, [])
        self.assertEqual(sock.enabled.item(), 1.0)

    def test_optimizer_membership_detects_missing_and_duplicates(self):
        model, _ = toy()
        params = [p for n, p in model.named_parameters() if not n.startswith('1.')]
        m = mp.optimizer_membership(model, torch.optim.SGD(params + params[:1], lr=0.1))
        self.assertTrue(any(n.startswith('1.') for n in m['missing']))
        self.assertEqual(m['duplicated'], 1)

    def test_zero_init_branch_unlocks_and_contributes_after_training(self):
        model, sock = toy(0.0)
        opt = torch.optim.Adam(model.parameters(), lr=1e-2)
        meter = mp.UpdateMeter(sock.parameters())
        x, y = torch.randn(8, 1, 16, 16), torch.randn(8, 1, 16, 16)
        for _ in range(30):
            opt.zero_grad(); nn.functional.mse_loss(model(x), y).backward(); opt.step()
        self.assertGreater(meter(), 0)
        with mp.EffectiveContribution([sock]) as ec:
            model(x)
        self.assertGreater(ec.values()[0][0], 1e-3)

    def test_double_zero_never_trains(self):
        torch.manual_seed(0)
        last = nn.Conv2d(4, 4, 1); nn.init.zeros_(last.weight); nn.init.zeros_(last.bias)
        sock = mp.ResidualSocket(nn.Sequential(nn.Conv2d(4, 4, 3, padding=1), nn.ReLU(), last), scale_init=0.0)
        model = nn.Sequential(nn.Conv2d(1, 4, 3, padding=1), sock, nn.Conv2d(4, 1, 1))
        opt = torch.optim.Adam(model.parameters(), lr=1e-2)
        x, y = torch.randn(4, 1, 8, 8), torch.randn(4, 1, 8, 8)
        for _ in range(20):
            opt.zero_grad(); nn.functional.mse_loss(model(x), y).backward(); opt.step()
        with mp.EffectiveContribution([sock]) as ec:
            model(x)
        self.assertEqual(ec.values()[0][0], 0.0)   # documented trap: gate and last layer both zero -> dead forever

    def test_selection_exposure_verdicts(self):
        curve = [dict(step=s, value=v) for s, v in ((0, 1.0), (50, 0.5), (100, 0.6), (150, 0.7))]
        self.assertEqual(mp.selection_exposure(curve, 50, None, 0.1)['verdict'], 'untested')
        curve2 = [dict(step=s, value=v) for s, v in ((0, 1.0), (50, 0.8), (100, 0.4), (150, 0.7))]
        self.assertEqual(mp.selection_exposure(curve2, 50, 60, 0.1)['verdict'], 'tested')
        self.assertEqual(mp.selection_exposure(curve2, 50, 60, 1e-5)['verdict'], 'untested')
        self.assertEqual(mp.selection_exposure(curve2, 50, 120, 0.1)['verdict'], 'untested')

    def test_step0_parity_restores_mixed_submodule_modes(self):
        model, sock = toy(0.0)
        model = nn.Sequential(model[0], nn.BatchNorm2d(4), sock, model[2]).train()
        model[1].eval()                                          # frozen BN inside a training model
        before = modes(model)
        self.assertEqual(before[:3], [True, True, False])
        self.assertEqual(mp.step0_parity(model, [sock], torch.randn(2, 1, 8, 8)), 0.0)
        self.assertEqual(modes(model), before)

    def test_step0_parity_restores_modes_and_socket_when_forward_raises(self):
        model, sock = toy(0.5)
        model = nn.Sequential(model[0], nn.BatchNorm2d(4), sock, Boom()).train()
        model[1].eval()
        before = modes(model)
        with self.assertRaises(RuntimeError):
            mp.step0_parity(model, [sock], torch.randn(2, 1, 8, 8))
        self.assertEqual(modes(model), before)
        self.assertEqual(sock.enabled.item(), 1.0)

    def test_selection_exposure_ties_go_to_earliest_step_in_any_order(self):
        curve = [dict(step=100, value=1.0), dict(step=50, value=1.0)]
        r = mp.selection_exposure(curve, 50, None, 0.1)
        self.assertEqual((r['selected_step'], r['verdict']), (50, 'untested'))
        self.assertEqual(r, mp.selection_exposure(curve[::-1], 50, None, 0.1))

    @unittest.skipUnless((EXPOSURE_CLI_DIR / 'selection_exposure_check.py').is_file(), 'share-autoresearch-engine absent')
    def test_selection_exposure_library_and_cli_agree_on_unsorted_ties(self):
        sys.path.insert(0, str(EXPOSURE_CLI_DIR))
        import selection_exposure_check as sec
        curve = [dict(step=100, value=1.0), dict(step=150, value=2.0), dict(step=50, value=1.0)]
        for first_eligible, unlock in ((50, None), (10, None), (10, 80)):
            lib = mp.selection_exposure(curve, first_eligible, unlock, 0.1)
            cli = sec.verdict([dict(r, effective=0.1) for r in curve], first_eligible, unlock)
            self.assertEqual((lib['selected_step'], lib['verdict']), (cli['selected_step'], cli['verdict']),
                             (first_eligible, unlock))

    def test_selection_exposure_rejects_bad_input(self):
        for curve in ([], [dict(step=1)], [dict(step=1, value=float('nan'))], [dict(step='1', value=1.0)],
                      [dict(step=1, value=1.0), dict(step=1, value=2.0)]):
            with self.assertRaises(ValueError, msg=json.dumps(curve, default=str)):
                mp.selection_exposure(curve, 0, None, None)
        for bad in (float('nan'), float('inf'), -1e-3):
            with self.assertRaises(ValueError):
                mp.selection_exposure([dict(step=1, value=1.0)], 0, None, 0.1, min_effective=bad)


def spots(rng, n=20, size=64):
    pts = rng.uniform(4, size - 4, size=(n, 2))
    yy, xx = np.mgrid[0:size, 0:size]
    img = sum(np.exp(-((yy - r) ** 2 + (xx - c) ** 2) / 4.5) for r, c in pts) + 0.05 * rng.standard_normal((size, size))
    return img, pts


@unittest.skipUnless(HAS_NUMPY, 'numpy/scipy not installed')
class AlignmentProbeTest(unittest.TestCase):
    def test_correct_labels_pass_and_swapped_labels_fail(self):
        rng = np.random.default_rng(1)
        data = [spots(rng) for _ in range(10)]
        good = ap.point_alignment([d[0] for d in data], [d[1] for d in data])
        bad = ap.point_alignment([d[0] for d in data], [d[1][:, ::-1] for d in data])
        self.assertTrue(good['ok'])
        self.assertFalse(bad['ok'])

    def test_mask_alignment_inside_brighter_than_flipped_control(self):
        img = np.zeros((32, 32)); img[2:10, 3:12] = 1.0
        mask = img > 0
        r = ap.mask_alignment([img], [mask])
        self.assertGreater(r['inside_minus_outside'], 0.5)
        self.assertLess(r['flipped_control'], r['inside_minus_outside'])

    def test_augmentation_sync_detects_flip_applied_to_image_only(self):
        def good(img, pts, k):
            if k % 2:
                img = img[:, ::-1]; pts = np.c_[pts[:, 0], img.shape[1] - 1 - pts[:, 1]]
            return img, pts

        def bad(img, pts, k):
            if k % 2:
                img = img[:, ::-1]                     # image flipped, points not
            return img, pts
        self.assertTrue(ap.augmentation_sync(good, n=10)['ok'])
        self.assertFalse(ap.augmentation_sync(bad, n=10)['ok'])


def small():
    return nn.Sequential(nn.Conv2d(1, 4, 3, padding=1), nn.BatchNorm2d(4), nn.ReLU(), nn.Dropout(0.5),
                         nn.Conv2d(4, 1, 1))


@unittest.skipUnless(HAS_TORCH, 'torch not installed')
class TrainSanityChecksTest(unittest.TestCase):
    def setUp(self):
        torch.manual_seed(0)
        self.x = torch.randn(2, 1, 8, 8)

    def test_strict_reload_ok_and_outputs_equal(self):
        model = small()
        r = tsc.strict_reload_roundtrip(small, model, self.x)
        self.assertTrue(r['ok'], r)
        self.assertEqual(r['max_abs'], 0.0)
        self.assertTrue(model.training)            # mode restored

    def test_strict_reload_detects_unexpected_and_missing_keys(self):
        trained = small()
        trained.register_buffer('extra', torch.zeros(1))   # added at training time, not in the constructor
        r = tsc.strict_reload_roundtrip(small, trained, self.x)
        self.assertFalse(r['ok'])
        self.assertEqual(r['unexpected'], ['extra'])

        def build_with_buffer():
            m = small(); m.register_buffer('calib', torch.ones(1)); return m
        r2 = tsc.strict_reload_roundtrip(build_with_buffer, small(), self.x)
        self.assertFalse(r2['ok'])
        self.assertEqual(r2['missing'], ['calib'])

    def test_strict_reload_reports_size_mismatch(self):
        r = tsc.strict_reload_roundtrip(lambda: nn.Sequential(nn.Conv2d(1, 2, 3)), nn.Sequential(nn.Conv2d(1, 3, 3)),
                                        self.x)
        self.assertFalse(r['ok'])
        self.assertIn('size mismatch', r['error'])

    def test_eval_mode_consistency_reports_bn_dropout_gap_and_restores_buffers(self):
        model = small()
        before = model[1].running_mean.clone()
        r = tsc.eval_mode_consistency(model, self.x)
        self.assertTrue(r['deterministic'])
        self.assertGreater(r['train_vs_eval_max_abs'], 0.0)
        self.assertEqual(r['mode_dependent_modules'], ['BatchNorm2d', 'Dropout'])
        self.assertTrue(torch.equal(before, model[1].running_mean))

    def test_probes_restore_mixed_submodule_modes(self):
        for name, probe in (('reload', lambda m: tsc.strict_reload_roundtrip(small, m, self.x)),
                            ('eval_mode', lambda m: tsc.eval_mode_consistency(m, self.x))):
            model = mixed_mode(small)
            before = modes(model)
            self.assertEqual(before[:3], [True, True, False])
            probe(model)
            self.assertEqual(modes(model), before, name)

    def test_probes_restore_modes_and_buffers_when_forward_raises(self):
        def build():
            return nn.Sequential(nn.Conv2d(1, 4, 3, padding=1), nn.BatchNorm2d(4), nn.BatchNorm2d(4), Boom(True))
        model = build().train()
        model[2].eval()
        before, bufs = modes(model), {n: b.clone() for n, b in model.named_buffers()}
        with self.assertRaises(RuntimeError):                  # BN[1] updated its stats, then Boom raised in train()
            tsc.eval_mode_consistency(model, self.x)
        self.assertEqual(modes(model), before)
        for n, b in model.named_buffers():
            self.assertTrue(torch.equal(bufs[n], b), n)
        model = build().train()
        model[2].eval()
        model[3].train_only = False                           # raises in the eval() forward as well
        with self.assertRaises(RuntimeError):
            tsc.strict_reload_roundtrip(lambda: build(), model, self.x)
        self.assertEqual(modes(model), before)

    def test_nonfinite_output_fails_in_any_key_order(self):
        class TwoHeads(nn.Module):
            def __init__(self, nan_key):
                super().__init__()
                self.scale, self.nan_key = nn.Parameter(torch.ones(1)), nan_key

            def forward(self, x):
                return {k: x * self.scale * (float('nan') if k == self.nan_key else 1.0) for k in ('a', 'z')}
        for nan_key, other in (('z', 'a'), ('a', 'z')):
            r = tsc.strict_reload_roundtrip(lambda: TwoHeads(nan_key), TwoHeads(nan_key), self.x)
            self.assertFalse(r['ok'], r)
            self.assertTrue(any(f"['{nan_key}']" in p for p in r['nonfinite']), r)
            self.assertFalse(any(f"['{other}']" in p for p in r['nonfinite']), r)
            e = tsc.eval_mode_consistency(TwoHeads(nan_key), self.x)
            self.assertFalse(e['deterministic'], e)
            self.assertTrue(e['nonfinite'] and all(f"['{nan_key}']" in p for p in e['nonfinite']), e)

    def test_nonfinite_train_forward_is_listed_but_eval_stays_deterministic(self):
        class TrainNaN(nn.Module):
            def __init__(self):
                super().__init__()
                self.scale = nn.Parameter(torch.ones(1))

            def forward(self, x):
                return {'a': x * self.scale, 'z': x * self.scale * (float('nan') if self.training else 1.0)}
        r = tsc.eval_mode_consistency(TrainNaN(), self.x)
        self.assertTrue(r['deterministic'], r)
        self.assertIsNone(r['train_vs_eval_max_abs'], r)
        self.assertEqual(r['nonfinite'], ["train:output['z']"], r)

    def test_infinite_difference_of_finite_outputs_fails(self):
        class Flip(nn.Module):
            def __init__(self):
                super().__init__()
                self.scale = nn.Parameter(torch.ones(1))
                self.n = 0

            def forward(self, x):
                self.n += 1
                return torch.full((2,), 3e38 if self.n % 2 else -3e38) * self.scale
        r = tsc.eval_mode_consistency(Flip(), self.x)         # each output finite, their difference overflows
        self.assertFalse(r['deterministic'], r)
        self.assertTrue(any(p.startswith('diff') for p in r['nonfinite']), r)

    def test_optimizer_built_while_frozen_misses_unfrozen_params(self):
        model = small()
        for p in model[0].parameters():
            p.requires_grad_(False)
        opt = torch.optim.SGD([p for p in model.parameters() if p.requires_grad], lr=0.1)
        self.assertTrue(tsc.optimizer_covers_trainable(model, opt)['ok'])
        for p in model[0].parameters():
            p.requires_grad_(True)                 # unfreeze after building the optimizer
        r = tsc.optimizer_covers_trainable(model, opt)
        self.assertFalse(r['ok'])
        self.assertEqual(r['missing'], ['0.bias', '0.weight'])

    def test_optimizer_duplicates_named(self):
        model = small()
        ps = list(model.parameters())
        opt = torch.optim.SGD(ps, lr=0.1)
        opt.param_groups[0]['params'].append(model[4].weight)   # torch refuses duplicates at construction
        r = tsc.optimizer_covers_trainable(model, opt)
        self.assertEqual(r['duplicates'], ['4.weight'])
        self.assertFalse(r['ok'])

    def test_frozen_audit_counts_and_works_without_torchinfo(self):
        model = small()
        for p in model[0].parameters():
            p.requires_grad_(False)
        with mock.patch.dict(sys.modules, {'torchinfo': None}):
            r = tsc.frozen_audit(model)
        self.assertEqual(r['modules']['0'], dict(trainable=0, frozen=40))
        self.assertEqual(r['frozen'], 40)
        self.assertIsNone(r['torchinfo'])
        self.assertEqual(r['torchinfo_note'], 'torchinfo not installed')

    @unittest.skipUnless(importlib.util.find_spec('torchinfo'), 'torchinfo not installed')
    def test_frozen_audit_torchinfo_rows(self):
        model = small()
        for p in model[0].parameters():
            p.requires_grad_(False)
        rows = tsc.frozen_audit(model, input_size=(1, 1, 8, 8))['torchinfo']
        self.assertEqual(rows[0]['trainable'], 'Partial')
        self.assertEqual(rows[1]['trainable'], 'False')
        self.assertEqual(rows[1]['output_size'], [1, 4, 8, 8])

    def test_overfit_loop_reaches_target_or_reports_not(self):
        w = torch.zeros(1, requires_grad=True)
        opt = torch.optim.SGD([w], lr=0.1)

        def step(_):
            opt.zero_grad(); ((w - 1) ** 2).sum().backward(); opt.step()
        metric = lambda: float(1 - (w.detach() - 1).abs())            # noqa: E731
        r = tsc.overfit_under_training_transforms(step, metric, 200, 10, target=0.99)
        self.assertTrue(r['reached'])
        self.assertEqual(r['curve'][-1]['step'], r['reached_at_step'])
        w2 = torch.zeros(1)
        r2 = tsc.overfit_under_training_transforms(lambda s: None, lambda: float(w2), 20, 5, target=0.5)
        self.assertFalse(r2['reached'])
        self.assertEqual([c['step'] for c in r2['curve']], [5, 10, 15, 20])

    def test_debug_locals_records_tensor_and_array_summaries_and_restores_profiler(self):
        @tsc.debug_locals
        def f(t):
            arr = np.arange(6.0).reshape(2, 3) if HAS_NUMPY else None
            h = t.clamp(min=0)
            label = 'x' * 500
            return h.sum()
        f(self.x)
        loc = f.last_locals
        self.assertEqual(loc['h']['shape'], [2, 1, 8, 8])
        self.assertEqual(loc['h']['min'], 0.0)
        self.assertLessEqual(len(loc['label']['repr']), 90)
        if HAS_NUMPY:
            self.assertEqual((loc['arr']['min'], loc['arr']['max']), (0.0, 5.0))
        self.assertIsNone(sys.getprofile())

    def test_debug_locals_records_on_exception(self):
        @tsc.debug_locals
        def g():
            bad = torch.tensor([float('nan')])
            raise RuntimeError('boom')
        with self.assertRaises(RuntimeError):
            g()
        self.assertFalse(g.last_locals['bad']['finite'])


if __name__ == '__main__':
    unittest.main()
