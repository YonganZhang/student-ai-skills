"""Generic array DataModule: the only place that knows about file layout.

Adapt this file, not the training loop, when moving to a new dataset.
Single-task keys: x_train, y_train, x_val, y_val; optional x_test, y_test.
Multi-task keys: x_train, y_train_<task>, x_val, y_val_<task> for each task.
Shapes are preserved exactly as stored, e.g. (N, C, H, W), (N, T, C), (N, D, H, W).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import lightning as L
import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset


class ArrayDataset(Dataset):
    def __init__(self, x: np.ndarray, y: np.ndarray, sample_ids: np.ndarray | None = None):
        if len(x) != len(y):
            raise ValueError(f"x/y length mismatch: {len(x)} != {len(y)}")
        self.x = torch.as_tensor(x, dtype=torch.float32)
        self.y = torch.as_tensor(y, dtype=torch.float32)
        if sample_ids is None:
            sample_ids = np.arange(len(x), dtype=np.int64)
        if len(sample_ids) != len(x):
            raise ValueError(f"sample_ids length mismatch: {len(sample_ids)} != {len(x)}")
        self.sample_ids = torch.as_tensor(sample_ids, dtype=torch.long)

    def __len__(self) -> int:
        return len(self.x)

    def __getitem__(self, index: int) -> dict[str, Any]:
        return {"x": self.x[index], "y": self.y[index], "sample_id": self.sample_ids[index]}


class MultiTaskArrayDataset(Dataset):
    """Return y as a dict so each task keeps its own target tensor."""

    def __init__(
        self,
        x: np.ndarray,
        targets: dict[str, np.ndarray],
        sample_ids: np.ndarray | None = None,
        dtypes: dict[str, str] | None = None,
    ):
        if not targets:
            raise ValueError("multi-task dataset needs at least one target")
        lengths = {len(x), *(len(v) for v in targets.values())}
        if len(lengths) != 1:
            raise ValueError(f"x/y length mismatch across tasks: {sorted(lengths)}")
        dtypes = dtypes or {}
        unknown = set(dtypes) - set(targets)
        if unknown:
            raise KeyError(f"target_dtypes has unknown tasks: {sorted(unknown)}")
        allowed = {"float32", "float64", "int64"}
        for task, dtype in dtypes.items():
            if dtype not in allowed:
                raise ValueError(f"unsupported dtype for {task!r}: {dtype!r}; choose {sorted(allowed)}")
        self.x = torch.as_tensor(x, dtype=torch.float32)
        self.y = {
            name: torch.as_tensor(value, dtype=getattr(torch, dtypes.get(name, "float32")))
            for name, value in targets.items()
        }
        if sample_ids is None:
            sample_ids = np.arange(len(x), dtype=np.int64)
        if len(sample_ids) != len(x):
            raise ValueError(f"sample_ids length mismatch: {len(sample_ids)} != {len(x)}")
        self.sample_ids = torch.as_tensor(sample_ids, dtype=torch.long)

    def __len__(self) -> int:
        return len(self.x)

    def __getitem__(self, index: int) -> dict[str, Any]:
        return {
            "x": self.x[index],
            "y": {name: value[index] for name, value in self.y.items()},
            "sample_id": self.sample_ids[index],
        }


class ArrayDataModule(L.LightningDataModule):
    """Read train/val arrays; test is a separate file behind an explicit flag."""

    def __init__(
        self,
        data_path: str,
        batch_size: int = 8,
        num_workers: int = 0,
        test_path: str | None = None,
        allow_test: bool = False,
        pin_memory: bool = False,
        test_read_flag: str | None = None,
        tasks: list[str] | None = None,
        target_dtypes: dict[str, str] | None = None,
    ) -> None:
        super().__init__()
        self.data_path = Path(data_path)
        self.test_path = Path(test_path) if test_path else None
        self.batch_size = batch_size
        self.num_workers = num_workers
        self.allow_test = allow_test
        self.pin_memory = pin_memory
        self.test_read_flag = Path(test_read_flag) if test_read_flag else None
        self.tasks = list(tasks) if tasks else None
        self.target_dtypes = dict(target_dtypes or {})
        self.train_ds: ArrayDataset | MultiTaskArrayDataset | None = None
        self.val_ds: ArrayDataset | MultiTaskArrayDataset | None = None
        self.test_ds: ArrayDataset | MultiTaskArrayDataset | None = None
        self.test_was_read = False
        self.input_shape: tuple[int, ...] | None = None
        self.output_shape: tuple[int, ...] | None = None
        self.output_shapes: dict[str, tuple[int, ...]] = {}

    def _infer_tasks(self, files: set[str]) -> list[str] | None:
        if self.tasks:
            return self.tasks
        inferred = sorted(name.removeprefix("y_train_") for name in files if name.startswith("y_train_"))
        return inferred or None

    def _task_targets(self, data: Any, split: str, tasks: list[str]) -> dict[str, np.ndarray]:
        keys = {f"y_{split}_{task}" for task in tasks}
        missing = keys - set(data.files)
        if missing:
            raise KeyError(f"{self.data_path} missing keys: {sorted(missing)}")
        return {task: data[f"y_{split}_{task}"] for task in tasks}

    def setup(self, stage: str | None = None) -> None:
        if self.train_ds is not None:
            return
        with np.load(self.data_path) as data:
            required = {"x_train", "x_val"}
            missing = required - set(data.files)
            if missing:
                raise KeyError(f"{self.data_path} missing keys: {sorted(missing)}")
            tasks = self._infer_tasks(set(data.files))
            if tasks:
                self.tasks = tasks
                unknown = set(self.target_dtypes) - set(tasks)
                if unknown:
                    raise KeyError(f"target_dtypes has unknown tasks: {sorted(unknown)}")
                train_targets = self._task_targets(data, "train", tasks)
                val_targets = self._task_targets(data, "val", tasks)
                self.train_ds = MultiTaskArrayDataset(
                    data["x_train"],
                    train_targets,
                    data["sample_ids_train"] if "sample_ids_train" in data.files else None,
                    self.target_dtypes,
                )
                self.val_ds = MultiTaskArrayDataset(
                    data["x_val"],
                    val_targets,
                    data["sample_ids_val"] if "sample_ids_val" in data.files else None,
                    self.target_dtypes,
                )
                self.output_shapes = {
                    task: tuple(self.train_ds.y[task].shape[1:]) for task in tasks
                }
                self.output_shape = next(iter(self.output_shapes.values()))
            else:
                required = {"y_train", "y_val"}
                missing = required - set(data.files)
                if missing:
                    raise KeyError(f"{self.data_path} missing keys: {sorted(missing)}")
                self.train_ds = ArrayDataset(
                    data["x_train"],
                    data["y_train"],
                    data["sample_ids_train"] if "sample_ids_train" in data.files else None,
                )
                self.val_ds = ArrayDataset(
                    data["x_val"],
                    data["y_val"],
                    data["sample_ids_val"] if "sample_ids_val" in data.files else None,
                )
                self.output_shape = tuple(self.train_ds.y.shape[1:])
            self.input_shape = tuple(self.train_ds.x.shape[1:])

    def _loader(self, ds: ArrayDataset | MultiTaskArrayDataset, shuffle: bool) -> DataLoader:
        return DataLoader(
            ds,
            batch_size=self.batch_size,
            shuffle=shuffle,
            num_workers=self.num_workers,
            pin_memory=self.pin_memory,
            persistent_workers=self.num_workers > 0,
        )

    def train_dataloader(self) -> DataLoader:
        assert self.train_ds is not None
        return self._loader(self.train_ds, shuffle=True)

    def val_dataloader(self) -> DataLoader:
        assert self.val_ds is not None
        return self._loader(self.val_ds, shuffle=False)

    def test_dataloader(self) -> DataLoader:
        if not self.allow_test:
            raise RuntimeError(
                "test is sealed: pass allow_test=True only after the protocol is frozen; "
                "never use test for checkpoint/threshold selection"
            )
        if self.test_path is None:
            raise RuntimeError("test_path is not configured")
        if self.test_read_flag is None:
            raise RuntimeError("test_read_flag is required for an auditable one-time test read")
        if self.test_was_read or self.test_read_flag.exists():
            raise RuntimeError(
                "test was already read; this template permits one deliberate read only. "
                "Use a final-test receipt, not another test_dataloader call."
            )
        try:
            same = self.test_path.samefile(self.data_path)
        except OSError:
            same = self.test_path.resolve() == self.data_path.resolve()
        if same:
            raise RuntimeError("test_path must be a separate file from data_path (same inode)")
        self.test_read_flag.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.test_read_flag, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError as exc:
            raise RuntimeError(
                "test was already read by another process; use a final-test receipt"
            ) from exc
        with os.fdopen(fd, "w") as handle:
            handle.write("test_dataloader was called\n")
        self.test_was_read = True
        if self.test_ds is None:
            with np.load(self.test_path) as data:
                if self.tasks:
                    targets = {}
                    missing = {f"y_test_{task}" for task in self.tasks} - set(data.files)
                    if missing:
                        raise KeyError(f"{self.test_path} missing keys: {sorted(missing)}")
                    targets = {task: data[f"y_test_{task}"] for task in self.tasks}
                    self.test_ds = MultiTaskArrayDataset(
                        data["x_test"],
                        targets,
                        data["sample_ids_test"] if "sample_ids_test" in data.files else None,
                        self.target_dtypes,
                    )
                else:
                    required = {"x_test", "y_test"}
                    missing = required - set(data.files)
                    if missing:
                        raise KeyError(f"{self.test_path} missing keys: {sorted(missing)}")
                    self.test_ds = ArrayDataset(
                        data["x_test"],
                        data["y_test"],
                        data["sample_ids_test"] if "sample_ids_test" in data.files else None,
                    )
        return self._loader(self.test_ds, shuffle=False)
