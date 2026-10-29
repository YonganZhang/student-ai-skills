#!/usr/bin/env python3
"""Count Markdown files among the direct children of a directory. Read-only, non-recursive."""

import argparse
import errno
import json
import os
from pathlib import Path
import stat
import sys


def build_parser():
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="统计一个目录【直接子项】中 .md 普通文件的数量（不递归、不写入）。",
        epilog="例：python3 cli.py count . --json",
        allow_abbrev=False,
    )
    parser.add_argument("--json", action="store_true", help="成功结果输出 JSON")
    commands = parser.add_subparsers(dest="command", required=True)
    count = commands.add_parser(
        "count", help="统计目录直接子项中的 .md 普通文件", allow_abbrev=False,
        epilog="例：python3 cli.py count docs",
    )
    count.add_argument("directory", type=Path, help="目标目录（本身跟随软链；子项软链不计入）")
    count.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS,
        help="成功结果输出 JSON",
    )
    return parser


def count_markdown(directory):
    """Count regular .md files directly inside directory. Domain logic, no rendering.

    - The directory argument itself follows symlinks (resolve + stat).
    - Direct children are classified with follow_symlinks=False: a child symlink,
      even one pointing at a .md file, is NOT a regular file and is not counted.
    - .md match is case-sensitive on the lowercase suffix. No recursion.
    """
    try:
        target = directory.resolve(strict=True)
    except RuntimeError as error:
        # Python <= 3.12 uses RuntimeError for pathlib symlink loops.
        raise OSError(errno.ELOOP, "路径存在软链环", str(directory)) from error
    info = target.stat()
    if not stat.S_ISDIR(info.st_mode):
        raise NotADirectoryError(errno.ENOTDIR, "不是目录", str(target))
    total = 0
    with os.scandir(target) as entries:
        for entry in entries:
            if entry.name.endswith(".md") and entry.is_file(follow_symlinks=False):
                total += 1
    return {"path": str(target), "markdown_files": total}


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        result = count_markdown(args.directory)
    except NotADirectoryError as error:
        print(f"统计失败：{error.strerror}：{error.filename}；请传入一个目录路径。", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"统计失败：{error}；检查路径是否存在及读取权限。", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"schema_version": 1, "ok": True, "data": result}, ensure_ascii=False))
    else:
        print(f"{result['markdown_files']} markdown files  {result['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
