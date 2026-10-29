"""CPU wiring test only: image-like/series/multitask through the same loop.

This is not a training acceptance run; real training must use CUDA with
``pipeline.train --accelerator gpu`` and produce ``accelerator_receipt.json``.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import torch
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.models import build_model, build_multitask_model


def make_points(path: Path, n_train: int = 32, n_val: int = 8) -> None:
    rng = np.random.default_rng(7)
    total = n_train + n_val
    x = rng.normal(size=(total, 1, 32, 32)).astype(np.float32)
    y = (0.5 * x + 0.05 * rng.normal(size=x.shape)).astype(np.float32)
    np.savez(
        path,
        x_train=x[:n_train],
        y_train=y[:n_train],
        x_val=x[n_train:],
        y_val=y[n_train:],
    )


def make_series(path: Path, n_train: int = 32, n_val: int = 8) -> None:
    rng = np.random.default_rng(11)
    total = n_train + n_val
    x = rng.normal(size=(total, 16, 2)).astype(np.float32)
    y = x.mean(axis=(1, 2), keepdims=False).reshape(-1, 1).astype(np.float32)
    np.savez(
        path,
        x_train=x[:n_train],
        y_train=y[:n_train],
        x_val=x[n_train:],
        y_val=y[n_train:],
    )


def make_multitask(path: Path, n_train: int = 32, n_val: int = 8) -> None:
    rng = np.random.default_rng(23)
    total = n_train + n_val
    x = rng.normal(size=(total, 1, 32, 32)).astype(np.float32)
    recon = (0.5 * x + 0.05 * rng.normal(size=x.shape)).astype(np.float32)
    edge = np.abs(x).astype(np.float32)
    np.savez(
        path,
        x_train=x[:n_train],
        y_train_recon=recon[:n_train],
        y_train_edge=edge[:n_train],
        x_val=x[n_train:],
        y_val_recon=recon[n_train:],
        y_val_edge=edge[n_train:],
    )


def run_case(name: str, config: Path, data: Path, out: Path) -> None:
    cmd = [
        sys.executable,
        "-m",
        "pipeline.train",
        "--config",
        str(config),
        "--data-path",
        str(data),
        "--output-dir",
        str(out),
        "--max-steps",
        "20",
        "--accelerator",
        "cpu",
    ]
    subprocess.run(cmd, cwd=ROOT, check=True)
    for filename in ("best.ckpt", "last.ckpt", "manifest.yaml", "budget_guard.json", "curve_audit.json"):
        path = out / "checkpoints" / filename if filename.endswith(".ckpt") else out / filename
        assert path.exists(), f"{name}: missing {path}"
    manifest = yaml.safe_load((out / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["test_read"] is False, manifest
    assert manifest["best_step"] > 0, manifest
    audit = yaml.safe_load((out / "curve_audit.json").read_text(encoding="utf-8"))
    assert audit["verdict"] in {"TURNED_UP", "STILL_DECREASING", "PLATEAU", "BEST_AT_CAP"}, audit

    cfg = yaml.safe_load(config.read_text(encoding="utf-8"))
    model_cfg = dict(cfg["model"])
    model_name = model_cfg.pop("name")
    if model_name == "multitask":
        kwargs = dict(model_cfg.get("kwargs", {}))
        model = build_multitask_model(kwargs.get("backbone", {}), kwargs.get("heads", {}))
        ckpt = torch.load(out / "checkpoints" / "best.ckpt", map_location="cpu")
        state = {k: v for k, v in ckpt["state_dict"].items() if k.startswith(("backbone.", "heads."))}
        model.load_state_dict(state)
        csv = sorted((out / "logs" / "csv").rglob("metrics.csv"))[-1].read_text(encoding="utf-8")
        header = csv.splitlines()[0]
        for column in ("train/recon_loss", "train/edge_loss", "val/recon_mae", "val/edge_mae"):
            assert column in header, f"{name}: missing per-task log column {column}"
    else:
        model = build_model(model_name, **model_cfg.get("kwargs", {}))
        ckpt = torch.load(out / "checkpoints" / "best.ckpt", map_location="cpu")
        state = {k.removeprefix("model."): v for k, v in ckpt["state_dict"].items() if k.startswith("model.")}
        model.load_state_dict(state)

    gate = subprocess.run([sys.executable, str(ROOT.parent.parent / "scripts" / "check_run.py"), str(out)], capture_output=True)
    assert gate.returncode == 2, f"{name}: BEST_AT_CAP must be blocked, got {gate.returncode}"
    print(f"ok {name}: step={manifest['best_step']} loss={manifest['best_val_loss']:.4f} audit={audit['verdict']} reload=ok gate=blocked")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="dl-pipeline-smoke-") as tmp:
        tmp_path = Path(tmp)
        points_data = tmp_path / "points.npz"
        series_data = tmp_path / "series.npz"
        multitask_data = tmp_path / "multitask.npz"
        make_points(points_data)
        make_series(series_data)
        make_multitask(multitask_data)
        run_case("points", ROOT / "configs" / "points.yaml", points_data, tmp_path / "points_run")
        run_case("series", ROOT / "configs" / "series.yaml", series_data, tmp_path / "series_run")
        run_case("multitask", ROOT / "configs" / "multitask.yaml", multitask_data, tmp_path / "multitask_run")


if __name__ == "__main__":
    main()
