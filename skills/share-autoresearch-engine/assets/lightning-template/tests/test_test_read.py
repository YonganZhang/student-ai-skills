"""Regression checks for the one-time test read contract."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.data import ArrayDataModule


def write_npz(path: Path) -> None:
    np.savez(
        path,
        x_train=np.zeros((2, 1, 4, 4), dtype=np.float32),
        y_train=np.zeros((2, 1, 4, 4), dtype=np.float32),
        x_val=np.zeros((2, 1, 4, 4), dtype=np.float32),
        y_val=np.zeros((2, 1, 4, 4), dtype=np.float32),
        x_test=np.zeros((2, 1, 4, 4), dtype=np.float32),
        y_test=np.zeros((2, 1, 4, 4), dtype=np.float32),
    )


class OneTimeTestReadTest(unittest.TestCase):
    def test_second_read_and_existing_flag_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix="dl-testread-") as tmp:
            root = Path(tmp)
            data = root / "data.npz"
            test = root / "test.npz"
            flag = root / "test_read.flag"
            write_npz(data)
            write_npz(test)
            dm = ArrayDataModule(
                data_path=str(data),
                test_path=str(test),
                allow_test=True,
                test_read_flag=str(flag),
            )
            dm.test_dataloader()
            self.assertTrue(flag.exists())
            with self.assertRaises(RuntimeError):
                dm.test_dataloader()

            second = ArrayDataModule(
                data_path=str(data),
                test_path=str(test),
                allow_test=True,
                test_read_flag=str(flag),
            )
            with self.assertRaises(RuntimeError):
                second.test_dataloader()

    def test_missing_flag_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="dl-testread-") as tmp:
            root = Path(tmp)
            data = root / "data.npz"
            test = root / "test.npz"
            write_npz(data)
            write_npz(test)
            dm = ArrayDataModule(
                data_path=str(data),
                test_path=str(test),
                allow_test=True,
            )
            with self.assertRaises(RuntimeError):
                dm.test_dataloader()

    def test_hardlink_alias_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="dl-testread-") as tmp:
            root = Path(tmp)
            data = root / "data.npz"
            alias = root / "test_alias.npz"
            write_npz(data)
            os.link(data, alias)
            dm = ArrayDataModule(
                data_path=str(data),
                test_path=str(alias),
                allow_test=True,
                test_read_flag=str(root / "test_read.flag"),
            )
            with self.assertRaises(RuntimeError):
                dm.test_dataloader()

    def test_test_file_must_be_separate(self):
        with tempfile.TemporaryDirectory(prefix="dl-testread-") as tmp:
            data = Path(tmp) / "data.npz"
            write_npz(data)
            dm = ArrayDataModule(
                data_path=str(data),
                test_path=str(data),
                allow_test=True,
            )
            with self.assertRaises(RuntimeError):
                dm.test_dataloader()


if __name__ == "__main__":
    unittest.main()
