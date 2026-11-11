"""健康检查与指标端点（M0 / T07），`CONTRACTS.md §8`。

三个端点挂在**根路径**、不需要认证、且 `include_in_schema=False`，
因此不会出现在 `/api/v1/openapi.json`。`/healthz` 不触碰任何外部依赖。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app.core.db import check_db
from app.core.metrics import CONTENT_TYPE_LATEST, render_metrics
from app.core.redis import check_redis

__all__ = ["router"]

_READY_TIMEOUT = 2.0
router = APIRouter()


async def _probe(name: str, check: Callable[[], Awaitable[bool]]) -> tuple[str, bool]:
    """单个依赖检查；检查函数自身抛异常也只记为不可用。"""
    try:
        return name, await check()
    except Exception:
        return name, False


@router.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    """进程存活探针：恒 200，不访问 DB / Redis。"""
    return {"status": "ok"}


@router.get("/readyz", include_in_schema=False)
async def readyz() -> JSONResponse:
    """并发检查 DB 与 Redis；整体 2 秒超时，超时一律视为不就绪。"""
    try:
        pairs = await asyncio.wait_for(
            asyncio.gather(
                _probe("database", check_db),
                _probe("redis", check_redis),
            ),
            timeout=_READY_TIMEOUT,
        )
        checks: dict[str, bool] = dict(pairs)
    except TimeoutError:
        checks = {"database": False, "redis": False}

    ready = all(checks.values())
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "not_ready", "checks": checks},
    )


@router.get("/metrics", include_in_schema=False)
async def metrics(request: Request) -> Response:
    """Prometheus 文本；`metrics_enabled=false` 时返回 404。"""
    enabled: Any = getattr(request.app.state, "metrics_enabled", False)
    if not enabled:
        return Response(status_code=404)
    return Response(content=render_metrics(request.app), media_type=CONTENT_TYPE_LATEST)
