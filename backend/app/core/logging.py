"""日志占位（T01 空壳）。T02 将整体重写，保持本文件两个公开签名不变。

c4b30e8 澄清：create_app() 会调用 setup_logging(settings)，因此空壳必须导出它；
get_logger 在空壳期返回标准库 Logger（T02 改为 structlog BoundLogger）。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.config import Settings

__all__ = ["get_logger", "setup_logging"]


def setup_logging(settings: Settings) -> None:
    """T01 no-op；T02 实现 structlog JSON / 控制台日志配置。"""
    del settings


def get_logger(name: str | None = None) -> logging.Logger:
    """返回标准库 Logger；T02 整体重写时改为 structlog.stdlib.BoundLogger。"""
    return logging.getLogger(name)
