"""应用生命周期（M0 / T07），`CONTRACTS.md §8/§9`。

`main.py` 的 `lifespan` 已转调本模块，T07 合并后自动生效，无需改动接线。
关闭时 DB 与 Redis 分别释放：任一失败只记日志，不影响另一路。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.core.db import dispose_engine
from app.core.logging import get_logger
from app.core.redis import close_redis

if TYPE_CHECKING:
    from fastapi import FastAPI

_log = get_logger("app.lifecycle")


async def on_startup(app: FastAPI) -> None:
    """输出启动日志，含版本与环境（不含任何凭据）。"""
    settings = get_settings()
    _log.info(
        "app.startup",
        app=app.title,
        version=settings.app_version,
        env=settings.app_env,
    )


async def on_shutdown(app: FastAPI) -> None:
    """释放 DB 连接池与 Redis 连接；单点失败不阻断其余清理。"""
    del app
    closers: tuple[tuple[str, Callable[[], Awaitable[None]]], ...] = (
        ("database", dispose_engine),
        ("redis", close_redis),
    )
    for component, closer in closers:
        try:
            await closer()
        except Exception:
            _log.error("app.shutdown_component_failed", component=component, exc_info=True)
    _log.info("app.shutdown")
