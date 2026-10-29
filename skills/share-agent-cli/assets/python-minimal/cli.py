#!/usr/bin/env python3
"""Small, dependency-free read-only CLI example. Replace inspect with real work."""

import argparse
import errno
import json
from pathlib import Path
import stat
import sys


def build_parser():
    parser = argparse.ArgumentParser(
        description="只读查看一个路径的元信息。",
        epilog="例：python3 cli.py inspect README.md --json",
        allow_abbrev=False,
    )
    parser.add_argument("--json", action="store_true", help="成功结果输出 JSON")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser(
        "inspect", help="查看文件或目录元信息", allow_abbrev=False,
        epilog="例：python3 cli.py inspect .",
    )
    inspect.add_argument("path", type=Path, help="目标文件或目录（跟随软链）")
    inspect.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS,
        help="成功结果输出 JSON",
    )
    return parser


def inspect_path(path):
    """Keep domain work independent of argument parsing and rendering."""
    try:
        target = path.resolve(strict=True)
    except RuntimeError as error:
        # Python <= 3.12 uses RuntimeError for pathlib symlink loops.
        raise OSError(errno.ELOOP, "路径存在软链环", str(path)) from error
    info = target.stat()
    kind = "directory" if stat.S_ISDIR(info.st_mode) else (
        "file" if stat.S_ISREG(info.st_mode) else "other"
    )
    return {"path": str(target), "kind": kind, "size_bytes": info.st_size}


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        result = inspect_path(args.path)
    except OSError as error:
        print(f"读取失败：{error}；检查路径是否存在及读取权限。", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"schema_version": 1, "ok": True, "data": result}, ensure_ascii=False))
    else:
        print(f"{result['kind']}  {result['size_bytes']} bytes  {result['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
