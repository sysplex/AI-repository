"""应用生命周期（M0 / T07），`CONTRACTS.md §8/§9`。

`main.py` 的 `lifespan` 已转调本模块，T07 合并后自动生效，无需改动接线。
关闭时 DB 与 Redis 分别释放：任一失败只记日志，不影响另一路。
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from app.core.config import get_settings
from app.core.db import dispose_engine
from app.core.logging import get_logger
from app.core.redis import close_redis

if TYPE_CHECKING:
    from fastapi import FastAPI

_log = get_logger("app.lifecycle")

_startup_hooks: list[Callable[[FastAPI], Any]] = []


def register_startup_hook(hook: Callable[[FastAPI], Any]) -> None:
    """注册应用启动回调钩子（供高层路由层/业务组装层挂载，避免逆向分层依赖）。"""
    _startup_hooks.append(hook)


async def on_startup(app: FastAPI) -> None:
    """输出启动日志，含版本与环境（不含任何凭据），并执行所有注册的启动钩子。"""
    settings = get_settings()
    _log.info(
        "app.startup",
        app=app.title,
        version=settings.app_version,
        env=settings.app_env,
    )
    for hook in _startup_hooks:
        try:
            res = hook(app)
            if inspect.isawaitable(res):
                await res
        except Exception:
            _log.error(
                "app.startup_hook_failed",
                hook=getattr(hook, "__name__", str(hook)),
                exc_info=True,
            )
            raise


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
