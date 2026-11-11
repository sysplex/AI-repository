"""T01 冒烟测试：create_app() 可构建且 /docs 可访问。"""

from __future__ import annotations

import httpx
from fastapi import FastAPI
from httpx import ASGITransport

from app.main import create_app


async def test_create_app_builds() -> None:
    """create_app() 返回 FastAPI 实例，且不需要任何必填环境变量。"""
    app = create_app()
    assert isinstance(app, FastAPI)


async def test_docs_available() -> None:
    """/docs 返回 200（ASGITransport，不访问任何外部依赖）。"""
    app = create_app()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/docs")
    assert response.status_code == 200
