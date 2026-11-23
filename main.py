"""Điểm khởi chạy chính của phần mềm ScreenLens Translate."""

from __future__ import annotations

import os
import sys


def main() -> int:
    # Đảm bảo hiển thị UTF-8 chuẩn trên console Windows
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    from src.app import run_app

    return run_app()


if __name__ == "__main__":
    raise SystemExit(main())
