"""应用接线（CONTRACTS §9）。本文件仅 T01 与 T11 可改。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router, root_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.lifecycle import on_shutdown, on_startup
from app.core.logging import setup_logging
from app.core.middleware import install_middlewares


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """生命周期钩子；T01 空壳转调 lifecycle 的 no-op 实现，T07 合并后自动生效。"""
    await on_startup(app)
    try:
        yield
    finally:
        await on_shutdown(app)


def create_app() -> FastAPI:
    """构建 FastAPI 应用；所有依赖的空壳由 T01 提供，后续任务只改自己的文件。"""
    settings = get_settings()
    setup_logging(settings)
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs" if settings.docs_enabled else None,
        openapi_url="/api/v1/openapi.json" if settings.docs_enabled else None,
        lifespan=lifespan,
    )
    install_middlewares(app, settings)
    register_exception_handlers(app)
    app.include_router(root_router)
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
