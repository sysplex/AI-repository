"""错误体系占位（T01 空壳）。T03 将整体重写。"""

from __future__ import annotations

from fastapi import FastAPI


def register_exception_handlers(app: FastAPI) -> None:
    """T01 no-op；T03 实现统一错误响应处理器。"""
    del app
