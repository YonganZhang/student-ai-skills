"""LightningModule wrapper. Model/loss/metric are injected; the loop is fixed."""
from __future__ import annotations

import math
from typing import Callable

import lightning as L
import torch
from torch import nn


class SupervisedModule(L.LightningModule):
    def __init__(
        self,
        model: nn.Module,
        loss_fn: Callable[[torch.Tensor, torch.Tensor], torch.Tensor],
        metrics: dict[str, Callable[[torch.Tensor, torch.Tensor], torch.Tensor]] | None = None,
        lr: float = 1e-3,
        weight_decay: float = 0.0,
        scheduler: dict | None = None,
    ) -> None:
        super().__init__()
        self.save_hyperparameters(ignore=["model", "loss_fn", "metrics"])
        self.model = model
        self.loss_fn = loss_fn
        self.metrics = metrics or {}
        self.lr = lr
        self.weight_decay = weight_decay
        self.scheduler_cfg = scheduler

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.model(x)

    def _shared_step(self, batch: dict, stage: str) -> torch.Tensor:
        pred = self(batch["x"])
        target = batch["y"]
        loss = self.loss_fn(pred, target)
        batch_size = batch["x"].shape[0]
        self.log(
            f"{stage}/loss",
            loss,
            on_step=(stage == "train"),
            on_epoch=True,
            prog_bar=True,
            batch_size=batch_size,
            sync_dist=(stage == "val"),
        )
        for name, fn in self.metrics.items():
            value = fn(pred.detach(), target.detach())
            self.log(
                f"{stage}/{name}",
                value,
                on_step=False,
                on_epoch=True,
                prog_bar=False,
                batch_size=batch_size,
                sync_dist=(stage == "val"),
            )
        return loss

    def training_step(self, batch: dict, batch_idx: int) -> torch.Tensor:
        return self._shared_step(batch, "train")

    def validation_step(self, batch: dict, batch_idx: int) -> torch.Tensor:
        return self._shared_step(batch, "val")

    def test_step(self, batch: dict, batch_idx: int) -> torch.Tensor:
        return self._shared_step(batch, "test")

    def predict_step(self, batch: dict, batch_idx: int, dataloader_idx: int = 0) -> dict:
        return {"pred": self(batch["x"]), "sample_id": batch["sample_id"]}

    def configure_optimizers(self):
        optimizer = torch.optim.AdamW(
            self.parameters(),
            lr=self.lr,
            weight_decay=self.weight_decay,
        )
        if not self.scheduler_cfg:
            return optimizer
        name = self.scheduler_cfg.get("name", "step")
        if name != "step":
            raise ValueError(f"unsupported scheduler {name!r}; add it explicitly")
        scheduler = torch.optim.lr_scheduler.StepLR(
            optimizer,
            step_size=int(self.scheduler_cfg.get("step_size", 1000)),
            gamma=float(self.scheduler_cfg.get("gamma", 0.1)),
        )
        return {"optimizer": optimizer, "lr_scheduler": {"scheduler": scheduler, "interval": "step"}}

class MultiTaskModule(L.LightningModule):
    """Shared backbone with one head, loss and metric set per task.

    The template selects the lowest weighted ``val/loss`` for every run. That
    is a declared common compromise, not each task's independently best step.
    """

    def __init__(
        self,
        backbone: nn.Module,
        heads: dict[str, nn.Module],
        losses: dict[str, Callable[[torch.Tensor, torch.Tensor], torch.Tensor]],
        loss_weights: dict[str, float],
        metrics: dict[str, dict[str, Callable[[torch.Tensor, torch.Tensor], torch.Tensor]]] | None = None,
        lr: float = 1e-3,
        weight_decay: float = 0.0,
        scheduler: dict | None = None,
    ) -> None:
        super().__init__()
        if not heads:
            raise ValueError("multi-task module needs at least one head")
        if set(heads) != set(losses) or set(heads) != set(loss_weights):
            raise ValueError("heads, losses and loss_weights must have identical task keys")
        for task, weight in loss_weights.items():
            if not math.isfinite(float(weight)) or float(weight) < 0:
                raise ValueError(f"loss weight for {task!r} must be finite and >= 0")
        if sum(float(v) for v in loss_weights.values()) <= 0:
            raise ValueError("at least one loss weight must be positive")
        self.save_hyperparameters(ignore=["backbone", "heads", "losses", "metrics"])
        self.backbone = backbone
        self.heads = nn.ModuleDict(heads)
        self.losses = losses
        self.loss_weights = {k: float(v) for k, v in loss_weights.items()}
        self.metrics = metrics or {}
        unknown_metrics = set(self.metrics) - set(heads)
        if unknown_metrics:
            raise ValueError(f"metrics for unknown tasks: {sorted(unknown_metrics)}")
        self.lr = lr
        self.weight_decay = weight_decay
        self.scheduler_cfg = scheduler

    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        features = self.backbone(x)
        return {task: head(features) for task, head in self.heads.items()}

    def _shared_step(self, batch: dict, stage: str) -> torch.Tensor:
        prediction = self(batch["x"])
        target = batch["y"]
        if set(prediction) != set(target):
            raise ValueError(
                f"prediction/target task mismatch: {sorted(prediction)} != {sorted(target)}"
            )
        if set(prediction) != set(self.losses):
            raise ValueError(
                f"prediction/loss task mismatch: {sorted(prediction)} != {sorted(self.losses)}"
            )
        task_losses = {
            task: self.losses[task](prediction[task], target[task]) for task in prediction
        }
        for task, value in task_losses.items():
            if not torch.isfinite(value):
                raise ValueError(f"non-finite loss for task {task!r}: {value}")
        total = sum(self.loss_weights[task] * task_losses[task] for task in task_losses)
        batch_size = batch["x"].shape[0]
        self.log(
            f"{stage}/loss",
            total,
            on_step=(stage == "train"),
            on_epoch=True,
            prog_bar=True,
            batch_size=batch_size,
            sync_dist=(stage == "val"),
        )
        for task, value in task_losses.items():
            self.log(
                f"{stage}/{task}_loss",
                value,
                on_step=(stage == "train"),
                on_epoch=True,
                prog_bar=False,
                batch_size=batch_size,
                sync_dist=(stage == "val"),
            )
            for name, fn in self.metrics.get(task, {}).items():
                metric_value = fn(prediction[task].detach(), target[task].detach())
                self.log(
                    f"{stage}/{task}_{name}",
                    metric_value,
                    on_step=False,
                    on_epoch=True,
                    prog_bar=False,
                    batch_size=batch_size,
                    sync_dist=(stage == "val"),
                )
        return total

    def training_step(self, batch: dict, batch_idx: int) -> torch.Tensor:
        return self._shared_step(batch, "train")

    def validation_step(self, batch: dict, batch_idx: int) -> torch.Tensor:
        return self._shared_step(batch, "val")

    def test_step(self, batch: dict, batch_idx: int) -> torch.Tensor:
        return self._shared_step(batch, "test")

    def predict_step(self, batch: dict, batch_idx: int, dataloader_idx: int = 0) -> dict:
        return {"pred": self(batch["x"]), "sample_id": batch["sample_id"]}

    def configure_optimizers(self):
        optimizer = torch.optim.AdamW(
            self.parameters(),
            lr=self.lr,
            weight_decay=self.weight_decay,
        )
        if not self.scheduler_cfg:
            return optimizer
        name = self.scheduler_cfg.get("name", "step")
        if name != "step":
            raise ValueError(f"unsupported scheduler {name!r}; add it explicitly")
        scheduler = torch.optim.lr_scheduler.StepLR(
            optimizer,
            step_size=int(self.scheduler_cfg.get("step_size", 1000)),
            gamma=float(self.scheduler_cfg.get("gamma", 0.1)),
        )
        return {"optimizer": optimizer, "lr_scheduler": {"scheduler": scheduler, "interval": "step"}}
