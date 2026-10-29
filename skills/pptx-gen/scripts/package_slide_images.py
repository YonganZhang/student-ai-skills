#!/usr/bin/env python3
"""Validate and package a pure sequence of complete slide PNG images."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path

from PIL import Image


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_png(path: Path, require_4k: bool = False) -> dict:
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        if image.format != "PNG":
            raise ValueError(f"not a PNG: {path}")
        width, height = image.size

    if width < 1024 or height < 576:
        raise ValueError(f"too small for slide delivery: {path} is {width}x{height}")
    if require_4k and (width < 3840 or height < 2160):
        raise ValueError(f"not 4K-class: {path} is {width}x{height}")
    if abs(width / height - 16 / 9) > 0.03:
        raise ValueError(f"not 16:9: {path} is {width}x{height}")

    return {
        "name": path.name,
        "width": width,
        "height": height,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def package(source_dir: Path, output_zip: Path, expected_count: int, require_4k: bool = False) -> dict:
    images = sorted(
        path for path in source_dir.iterdir() if path.is_file() and path.suffix.lower() == ".png"
    )
    if len(images) != expected_count:
        raise ValueError(
            f"expected {expected_count} PNG files in {source_dir}, found {len(images)}"
        )

    records = [validate_png(path, require_4k=require_4k) for path in images]
    output_zip.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        dir=output_zip.parent,
        prefix=f".{output_zip.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)

    try:
        with zipfile.ZipFile(
            temporary_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as archive:
            for path in images:
                archive.write(path, arcname=path.name)

        with zipfile.ZipFile(temporary_path) as archive:
            names = archive.namelist()
            if names != [path.name for path in images]:
                raise ValueError("ZIP entry list does not match the validated PNG sequence")
            bad_entry = archive.testzip()
            if bad_entry is not None:
                raise ValueError(f"ZIP integrity failure at {bad_entry}")

        os.replace(temporary_path, output_zip)
    finally:
        temporary_path.unlink(missing_ok=True)

    return {
        "artifact_kind": "slide_image_sequence_zip",
        "image_count": len(records),
        "entries": [record["name"] for record in records],
        "images": records,
        "zip": str(output_zip),
        "zip_bytes": output_zip.stat().st_size,
        "zip_sha256": sha256_file(output_zip),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a ZIP containing only validated slide PNG files at their true resolution"
    )
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("output_zip", type=Path)
    parser.add_argument("--expected-count", type=int, required=True)
    parser.add_argument("--qa-json", type=Path)
    parser.add_argument("--require-4k", action="store_true", help="Require actual dimensions of at least 3840x2160")
    args = parser.parse_args()

    if args.expected_count < 1:
        parser.error("--expected-count must be positive")
    if not args.source_dir.is_dir():
        parser.error(f"source directory not found: {args.source_dir}")

    summary = package(
        args.source_dir.resolve(),
        args.output_zip.resolve(),
        args.expected_count,
        require_4k=args.require_4k,
    )
    if args.qa_json:
        args.qa_json.parent.mkdir(parents=True, exist_ok=True)
        args.qa_json.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
