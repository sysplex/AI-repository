"""Identity 路由依赖（T04 主干），`CONTRACTS.md §10`。

路由层只负责「取值 → 调服务 → 返回」，不写业务规则（`docs/07 §5`）。
端口实现由 `service.build_identity_service` 装配：import-linter 契约禁止
`app.api` 直接引用业务模块的 `adapters`（T01 C8），路由层只见 service / schemas 公开面。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.errors import Forbidden, Unauthenticated
from app.core.redis import get_redis
from app.modules.identity.enums import UserRole
from app.modules.identity.schemas import AuthenticatedUser
from app.modules.identity.service import (
    IdentityService,
    build_identity_service,
    make_mail_sender,
)

__all__ = [
    "bearer_token",
    "client_ip",
    "current_user",
    "get_identity_service",
    "require_role",
]

_SCHEME = "bearer"


def get_identity_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
) -> IdentityService:
    """组装 `IdentityService`；测试用 `app.dependency_overrides` 替换本函数即可。

    邮件适配器由 `make_mail_sender(settings)` 按 `APP_ENV` 选择：路由层不直接引用
    `adapters`（T01 契约 C8），只负责把选好的实例交给组合根（T06）。
    """
    return build_identity_service(
        session=session,
        settings=settings,
        redis=redis,
        mail=make_mail_sender(settings),
    )


def client_ip(request: Request) -> str | None:
    """来源 IP：只取 `Request.client.host`，不采信客户端可伪造的 `X-Forwarded-For`。"""
    if request.client is None:
        return None
    return request.client.host


def bearer_token(request: Request) -> str:
    """从 `Authorization` 解析 Bearer 令牌；缺失/格式错误一律 401。"""
    header = request.headers.get("Authorization")
    if not header:
        raise Unauthenticated()
    scheme, _, credentials = header.partition(" ")
    if scheme.lower() != _SCHEME or not credentials.strip():
        raise Unauthenticated()
    return credentials.strip()


async def current_user(
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    service: Annotated[IdentityService, Depends(get_identity_service)],
) -> AuthenticatedUser:
    """解析 Bearer access 并回读用户；所有私有端点的认证入口。"""
    user = await service.authenticate_access_token(token)
    request.state.user = user
    return user


def require_role(role: UserRole) -> Callable[..., Awaitable[AuthenticatedUser]]:
    """生成「角色不足即 403」的依赖工厂（`CONTRACTS §10`）。

    用工厂而不是 `Depends(require_role(...))` 常量，避免 FastAPI 把不同角色的
    依赖缓存成同一个 key；返回值同时携带当前用户，供端点直接使用。
    """

    async def _dependency(
        user: Annotated[AuthenticatedUser, Depends(current_user)],
    ) -> AuthenticatedUser:
        if user.role != role:
            raise Forbidden()
        return user

    return _dependency
