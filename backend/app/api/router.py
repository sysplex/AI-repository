"""路由占位（T01 空壳）。T07 整体重写并挂载 /healthz /readyz /metrics。"""

from __future__ import annotations

from fastapi import APIRouter

root_router = APIRouter()
api_router = APIRouter()
