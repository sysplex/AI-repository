"""中间件占位（T01 空壳）。T02 整体重写；T07 只在插入点补一行调用。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI

if TYPE_CHECKING:
    from app.core.config import Settings


def install_middlewares(app: FastAPI, settings: Settings) -> None:
    """T01 no-op；T02 实现请求上下文 / 安全响应头 / CORS 中间件。

    指标中间件插入点（T07 在此加入唯一一行 install_metrics(app, settings) 调用；
    create_app() 不单独调用，见 CONTRACTS §3/§8/§9）。
    """
    del app, settings
