"""录制 fixture 加载器（M0 / T10）。

只负责把 `tests/fixtures/<provider>/<symbol>/<endpoint>.json` 读成 Python 对象，
并阻止路径越界；不做任何脱敏或业务解析。目录规范见同目录 `README.md`。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURE_ROOT = Path(__file__).resolve().parent


def load_fixture(path: str | Path) -> Any:
    """按相对 `tests/fixtures/` 的路径加载 JSON；越界或缺失时显式报错。"""
    target = (FIXTURE_ROOT / path).resolve()
    if not target.is_relative_to(FIXTURE_ROOT):
        raise ValueError("fixture 路径必须位于 tests/fixtures 内")
    if not target.is_file():
        raise FileNotFoundError(f"录制 fixture 不存在：{path}")
    with target.open(encoding="utf-8") as handle:
        return json.load(handle)
