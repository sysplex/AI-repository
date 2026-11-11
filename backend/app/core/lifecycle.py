"""生命周期占位（T01 空壳）。T07 将整体重写。"""

from __future__ import annotations

from fastapi import FastAPI


async def on_startup(app: FastAPI) -> None:
    """T01 no-op；T07 记录启动日志。"""
    del app


async def on_shutdown(app: FastAPI) -> None:
    """T01 no-op；T07 释放 DB / Redis 连接。"""
    del app
