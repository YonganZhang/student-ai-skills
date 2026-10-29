"""Loss and metric functions. Add task-specific ones here, not in the loop."""
from __future__ import annotations

from typing import Callable

import torch
from torch.nn import functional as F


def mse(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    return F.mse_loss(pred, target)


def mae(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    return F.l1_loss(pred, target)


def bce_with_logits(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    return F.binary_cross_entropy_with_logits(pred, target)


def cross_entropy(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    return F.cross_entropy(pred, target.long())


LOSSES = {
    "mse": mse,
    "mae": mae,
    "bce_with_logits": bce_with_logits,
    "cross_entropy": cross_entropy,
}


def build_loss(name: str):
    if name not in LOSSES:
        raise KeyError(f"unknown loss {name!r}; choose from {sorted(LOSSES)}")
    return LOSSES[name]


def metric_mae(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    return (pred - target).abs().mean()


def metric_mse(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    return ((pred - target) ** 2).mean()


def metric_accuracy(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    if pred.ndim == target.ndim + 1 and pred.shape[1] == 1:
        pred = pred.squeeze(1)
    if pred.ndim > 1 and pred.shape[1] > 1:
        pred = pred.argmax(dim=1)
    else:
        pred = (pred > 0).long()
    target = target.long()
    if pred.shape != target.shape:
        pred = pred.reshape(target.shape)
    return (pred == target).float().mean()


METRICS = {"mae": metric_mae, "mse": metric_mse, "accuracy": metric_accuracy}


def build_metrics(names: list[str]) -> dict[str, Callable]:
    out = {}
    for name in names:
        if name not in METRICS:
            raise KeyError(f"unknown metric {name!r}; choose from {sorted(METRICS)}")
        out[name] = METRICS[name]
    return out
