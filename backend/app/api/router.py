"""根路由与 API 路由（M0 / T07 整体重写），`CONTRACTS.md §1/§8/§9`。

`root_router` 挂三个根路径探针（不带 /api/v1，且不在 OpenAPI 中）；
`api_router` 预留给 M1+ 的业务模块，由 `main.py` 以 `/api/v1` 前缀挂载。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.health import router as health_router

root_router = APIRouter()
root_router.include_router(health_router)

api_router = APIRouter()
