"""Unit checks for the multi-task runner's minimum contract."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.data import MultiTaskArrayDataset
from pipeline.models import build_multitask_model
from pipeline.module import MultiTaskModule


def make_model():
    return build_multitask_model(
        {
            "name": "small_unet",
            "kwargs": {"in_channels": 1, "base": 4, "return_features": True},
        },
        {
            "recon": {"type": "conv2d", "kwargs": {"in_channels": 4, "out_channels": 1, "kernel_size": 1}},
            "edge": {"type": "conv2d", "kwargs": {"in_channels": 4, "out_channels": 1, "kernel_size": 1}},
        },
    )


class MultiTaskContractTest(unittest.TestCase):
    def test_all_heads_and_backbone_receive_gradient(self):
        model = make_model()
        module = MultiTaskModule(
            backbone=model.backbone,
            heads=dict(model.heads),
            losses={"recon": torch.nn.functional.mse_loss, "edge": torch.nn.functional.l1_loss},
            loss_weights={"recon": 1.0, "edge": 0.5},
            metrics={"recon": {}, "edge": {}},
        )
        x = torch.randn(2, 1, 8, 8)
        y = {"recon": torch.randn(2, 1, 8, 8), "edge": torch.randn(2, 1, 8, 8)}
        outputs = module(x)
        total = sum(
            module.loss_weights[task] * module.losses[task](outputs[task], y[task])
            for task in outputs
        )
        total.backward()
        for task, head in module.heads.items():
            self.assertIsNotNone(head.weight.grad, task)
            self.assertGreater(float(head.weight.grad.abs().sum()), 0.0, task)
        self.assertIsNotNone(module.backbone.down1.net[0].weight.grad)
        self.assertGreater(float(module.backbone.down1.net[0].weight.grad.abs().sum()), 0.0)

    def test_strict_reload_reproduces_each_task_output(self):
        model = make_model().eval()
        x = torch.randn(2, 1, 8, 8)
        with torch.no_grad():
            before = {k: v.clone() for k, v in model(x).items()}
        state = {k: v.clone() for k, v in model.state_dict().items()}
        clone = make_model().eval()
        clone.load_state_dict(state, strict=True)
        with torch.no_grad():
            after = clone(x)
        self.assertEqual(set(before), set(after))
        for task in before:
            self.assertTrue(torch.equal(before[task], after[task]), task)

    def test_invalid_weight_and_task_keys_fail_closed(self):
        model = make_model()
        base = dict(
            backbone=model.backbone,
            heads=dict(model.heads),
            losses={"recon": torch.nn.functional.mse_loss, "edge": torch.nn.functional.mse_loss},
        )
        with self.assertRaises(ValueError):
            MultiTaskModule(loss_weights={"recon": 1.0, "edge": -1.0}, **base)
        with self.assertRaises(ValueError):
            MultiTaskModule(loss_weights={"recon": 0.0, "edge": 0.0}, **base)
        with self.assertRaises(ValueError):
            MultiTaskModule(loss_weights={"recon": 1.0}, **base)

    def test_target_dtype_and_sample_id_are_checked(self):
        x = np.zeros((3, 1, 4, 4), dtype=np.float32)
        y = {"label": np.zeros((3, 1), dtype=np.int64)}
        ds = MultiTaskArrayDataset(x, y, dtypes={"label": "int64"})
        self.assertEqual(ds[0]["y"]["label"].dtype, torch.long)
        with self.assertRaises(ValueError):
            MultiTaskArrayDataset(x, y, sample_ids=np.arange(2))
        with self.assertRaises(KeyError):
            MultiTaskArrayDataset(x, y, dtypes={"missing": "float32"})


if __name__ == "__main__":
    unittest.main()
