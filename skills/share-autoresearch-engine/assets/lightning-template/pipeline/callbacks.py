"""Callbacks that turn selection hygiene into visible artifacts."""
from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
from pathlib import Path

import lightning as L
import torch
import yaml


def _as_float(value) -> float | None:
    if value is None:
        return None
    if hasattr(value, "detach"):
        return float(value.detach().cpu())
    return float(value)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _atomic_json(path: Path, payload: dict) -> None:
    _atomic_write(path, json.dumps(payload, indent=2, ensure_ascii=False))


def classify(history: list[dict], best_at_cap: bool) -> str:
    """Classify a validation curve. Lower is better; UNKNOWN means not proven."""
    if len(history) < 3:
        return "INSUFFICIENT"
    steps: list[float] = []
    losses: list[float] = []
    for row in history:
        try:
            step = float(row["step"])
            loss = float(row["val_loss"])
        except (KeyError, TypeError, ValueError):
            return "INVALID"
        if not math.isfinite(step) or not math.isfinite(loss):
            return "INVALID"
        steps.append(step)
        losses.append(loss)
    if any(later < earlier for earlier, later in zip(steps, steps[1:])):
        return "INVALID"
    best_loss = min(losses)
    last = losses[-1]
    if best_at_cap:
        return "BEST_AT_CAP"
    scale = max(abs(best_loss), 1e-6)
    tol = scale * 0.01
    tail = losses[-3:]
    if last > best_loss + tol:
        return "TURNED_UP"
    if max(tail) - min(tail) <= tol:
        return "PLATEAU"
    if tail[0] - last > tol and last < losses[0]:
        return "STILL_DECREASING"
    return "UNKNOWN"



class BudgetGuard(L.Callback):
    """Track the best validation loss and whether it sits at the step cap."""

    def __init__(self, out_dir: str | Path):
        super().__init__()
        self.out_dir = Path(out_dir)
        self.best_loss = float("inf")
        self.best_step = 0
        self.history: list[dict] = []

    def state_dict(self) -> dict:
        """Persist the selected point with the checkpoint (needed on resume)."""
        return {
            "best_loss": self.best_loss,
            "best_step": self.best_step,
            "history": list(self.history),
        }

    def load_state_dict(self, state_dict: dict) -> None:
        self.best_loss = float(state_dict.get("best_loss", float("inf")))
        self.best_step = int(state_dict.get("best_step", 0))
        self.history = list(state_dict.get("history", []))

    def on_train_start(self, trainer: L.Trainer, pl_module: L.LightningModule) -> None:
        # Legacy checkpoints may not contain callback state; recover the visible
        # artifact rather than silently resetting the historical best.
        if self.history:
            return
        path = self.out_dir / "budget_guard.json"
        if not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.best_loss = float(payload.get("best_val_loss", float("inf")))
        self.best_step = int(payload.get("best_step", 0))
        self.history = list(payload.get("history", []))

    def on_validation_end(self, trainer: L.Trainer, pl_module: L.LightningModule) -> None:
        if not trainer.is_global_zero:
            return
        loss = _as_float(trainer.callback_metrics.get("val/loss"))
        if loss is None:
            return
        step = int(trainer.global_step)
        self.history.append({"step": step, "val_loss": loss})
        if loss < self.best_loss:
            self.best_loss = loss
            self.best_step = step
        self._write(trainer)

    def on_train_end(self, trainer: L.Trainer, pl_module: L.LightningModule) -> None:
        self._write(trainer)

    def _write(self, trainer: L.Trainer) -> None:
        if not trainer.is_global_zero:
            return
        max_steps = int(trainer.max_steps) if trainer.max_steps is not None else -1
        best_at_cap = bool(max_steps > 0 and self.best_step >= max_steps)
        payload = {
            "best_step": self.best_step,
            "best_val_loss": None if self.best_loss == float("inf") else self.best_loss,
            "max_steps": max_steps,
            "best_at_cap": best_at_cap,
            "history": self.history,
        }
        _atomic_json(self.out_dir / "budget_guard.json", payload)


class CurveAudit(L.Callback):
    """Classify the validation curve after training; never selects a checkpoint."""

    def __init__(self, out_dir: str | Path):
        super().__init__()
        self.out_dir = Path(out_dir)

    def on_train_end(self, trainer: L.Trainer, pl_module: L.LightningModule) -> None:
        if not trainer.is_global_zero:
            return
        path = self.out_dir / "budget_guard.json"
        if not path.exists():
            return
        payload = json.loads(path.read_text(encoding="utf-8"))
        history = payload.get("history", [])
        verdict = classify(history, bool(payload.get("best_at_cap")))
        audit = {
            "verdict": verdict,
            "n_validations": len(history),
            "best_step": payload.get("best_step"),
            "best_val_loss": payload.get("best_val_loss"),
            "last_val_loss": history[-1]["val_loss"] if history else None,
        }
        _atomic_json(self.out_dir / "curve_audit.json", audit)


class ManifestCallback(L.Callback):
    """Write a once-only run manifest; test_read comes from the DataModule state."""

    def __init__(
        self,
        out_dir: str | Path,
        config_path: str | Path,
        data_path: str | Path,
        split_seed: int | None = None,
        train_seed: int | None = None,
        deployment_metric_name: str = "",
        resume: bool = False,
        resumed_from: str | None = None,
        resolved_config_path: str | Path | None = None,
        structure_mode: str = "",
    ):
        super().__init__()
        self.out_dir = Path(out_dir)
        self.config_path = Path(config_path)
        self.data_path = Path(data_path)
        self.split_seed = split_seed
        self.train_seed = train_seed
        self.deployment_metric_name = deployment_metric_name
        self.resume = resume
        self.resumed_from = resumed_from
        self.resolved_config_path = Path(resolved_config_path) if resolved_config_path else None
        self.structure_mode = structure_mode

    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _git_state() -> tuple[str, bool]:
        try:
            commit = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
            ).strip()
            dirty = bool(
                subprocess.check_output(
                    ["git", "status", "--porcelain"], text=True, stderr=subprocess.DEVNULL
                ).strip()
            )
            return commit, dirty
        except Exception:
            return "unknown", True

    def _backup_existing(self) -> None:
        path = self.out_dir / "manifest.yaml"
        if not path.exists():
            return
        index = 1
        while True:
            suffix = "" if index == 1 else f"-{index}"
            backup = self.out_dir / f"manifest.previous{suffix}.yaml"
            if not backup.exists():
                path.replace(backup)
                return
            index += 1

    def on_train_start(self, trainer: L.Trainer, pl_module: L.LightningModule) -> None:
        if not trainer.is_global_zero:
            return
        path = self.out_dir / "manifest.yaml"
        if not path.exists():
            return
        if not self.resume:
            raise RuntimeError(f"manifest already exists (write-once): {path}")
        self._backup_existing()

    def on_train_end(self, trainer: L.Trainer, pl_module: L.LightningModule) -> None:
        if not trainer.is_global_zero:
            return
        path = self.out_dir / "manifest.yaml"
        if path.exists():
            raise RuntimeError(f"manifest already exists (write-once): {path}")
        guard_path = self.out_dir / "budget_guard.json"
        guard = json.loads(guard_path.read_text(encoding="utf-8")) if guard_path.exists() else {}
        audit_path = self.out_dir / "curve_audit.json"
        audit = json.loads(audit_path.read_text(encoding="utf-8")) if audit_path.exists() else {}
        datamodule = getattr(trainer, "datamodule", None)
        test_read = bool(getattr(datamodule, "test_was_read", False))
        commit, dirty = self._git_state()
        if self.resolved_config_path is None:
            resolved_manifest_path = None
        else:
            try:
                resolved_manifest_path = str(self.resolved_config_path.relative_to(self.out_dir))
            except ValueError:
                resolved_manifest_path = str(self.resolved_config_path)
        manifest = {
            "git_commit": commit,
            "git_dirty": dirty,
            "config_path": str(self.config_path),
            "config_sha256": self._sha256(self.config_path),
            "resolved_config_path": resolved_manifest_path,
            "resolved_config_sha256": self._sha256(self.resolved_config_path) if self.resolved_config_path else None,
            "data_path": str(self.data_path),
            "data_sha256": self._sha256(self.data_path),
            "split_seed": self.split_seed,
            "train_seed": self.train_seed,
            "budget_max_steps": int(trainer.max_steps) if trainer.max_steps is not None else -1,
            "validation_interval": trainer.val_check_interval,
            "best_step": guard.get("best_step"),
            "best_val_loss": guard.get("best_val_loss"),
            "best_at_cap": guard.get("best_at_cap"),
            "curve_verdict": audit.get("verdict"),
            "structure_mode": self.structure_mode,
            "deployment_metric_name": self.deployment_metric_name,
            "deployment_metric_value": None,
            "threshold": None,
            "test_read": test_read,
            "resumed_from": self.resumed_from,
            "notes": "template manifest; fill deployment metric after frozen validation",
        }
        _atomic_write(path, yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True))


class GPUReceipt(L.Callback):
    """Write proof that training actually ran on an accelerator.

    CPU is allowed only by an explicit test entry; the receipt marks that as
    ``CPU_WIRING_ONLY`` so a smoke cannot be mistaken for a training result.
    """

    def __init__(self, out_dir: str | Path):
        super().__init__()
        self.out_dir = Path(out_dir)

    def on_train_end(self, trainer: L.Trainer, pl_module: L.LightningModule) -> None:
        if not trainer.is_global_zero:
            return
        device = str(getattr(trainer.strategy, "root_device", "unknown"))
        cuda = device.startswith("cuda") and torch.cuda.is_available()
        payload = {
            "schema": "accelerator-receipt/v1",
            "device": device,
            "accelerator": type(trainer.accelerator).__name__,
            "gpu_name": torch.cuda.get_device_name(torch.cuda.current_device()) if cuda else None,
            "total_memory_bytes": int(torch.cuda.get_device_properties(torch.cuda.current_device()).total_memory) if cuda else None,
            "peak_allocated_bytes": int(torch.cuda.max_memory_allocated()) if cuda else 0,
            "global_step": int(trainer.global_step),
            "torch": torch.__version__,
            "lightning": L.__version__,
            "status": "GPU" if cuda else "CPU_WIRING_ONLY",
        }
        _atomic_json(self.out_dir / "accelerator_receipt.json", payload)
