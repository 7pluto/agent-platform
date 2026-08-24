#!/usr/bin/env python3
"""Fail a release when Console source or build output contains broken UTF-8 text."""

from __future__ import annotations

import argparse
from pathlib import Path


TEXT_EXTENSIONS = {".html", ".css", ".js", ".json", ".ts", ".vue", ".map"}

# These are stable fragments produced when ordinary Simplified Chinese UTF-8
# is incorrectly decoded as GBK and then saved again.  They are intentionally
# phrase-level markers to avoid flagging a legitimate isolated CJK character.
MOJIBAKE_MARKERS = (
    "\ufffd",
    "鍔犺浇",
    "鑳藉姏",
    "鏉冮檺",
    "鐭ヨ瘑",
    "妯″瀷",
    "鎻愮ず",
    "璇︽儏",
    "绠＄悊",
    "杩愯",
    "寮€濮",
    "宸插畬鎴",
    "璇烽€夋嫨",
    "鍙戝竷",
    "鎵ц",
    "鈥",
    "????",
)


def inspect_file(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
    except UnicodeError as exc:
        return [f"{path}: invalid UTF-8 ({exc})"]
    failures: list[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        matches = sorted({marker for marker in MOJIBAKE_MARKERS if marker in line})
        if matches:
            failures.append(f"{path}:{line_number}: suspicious mojibake {', '.join(repr(item) for item in matches)}")
    return failures


def check(root: Path) -> list[str]:
    failures: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in TEXT_EXTENSIONS:
            failures.extend(inspect_file(path))
    return failures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", default=["agent-console/src", "agent-console/index.html"])
    args = parser.parse_args()
    failures: list[str] = []
    for value in args.paths:
        path = Path(value)
        if path.is_file():
            failures.extend(inspect_file(path))
        elif path.is_dir():
            failures.extend(check(path))
        else:
            failures.append(f"{path}: path does not exist")
    if failures:
        raise SystemExit("Frontend UTF-8 validation failed:\n" + "\n".join(failures))
    print("Frontend UTF-8 validation passed")


if __name__ == "__main__":
    main()
