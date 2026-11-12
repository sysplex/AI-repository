"""Identity HTTP 端点（T04 主干），`CONTRACTS.md §10`。

路径按 `docs/05-api-spec.md §2.1` 声明为完整相对路径（`/auth/...`），
由 `router.py` 一次性 `include_router` 到 `/api/v1` 之下，T05 直接在本文件追加
`/me`、`/admin/users`，无需再次改路由聚合。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.deps import client_ip, current_user, get_identity_service
from app.modules.identity.schemas import (
    AuthenticatedUser,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserPublic,
)
from app.modules.identity.service import IdentityService

router = APIRouter(tags=["identity"])

ServiceDep = Annotated[IdentityService, Depends(get_identity_service)]
CurrentUserDep = Annotated[AuthenticatedUser, Depends(current_user)]


@router.post(
    "/auth/register",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    summary="注册账号",
)
async def register(
    payload: RegisterRequest,
    request: Request,
    service: ServiceDep,
) -> UserPublic:
    """创建账号；成功后不自动登录（`CONTRACTS §9` 行为 1）。"""
    return await service.register(payload, ip=client_ip(request))


@router.post("/auth/login", response_model=TokenPair, summary="登录并签发双令牌")
async def login(
    payload: LoginRequest,
    request: Request,
    service: ServiceDep,
) -> TokenPair:
    """凭据正确返回 access + refresh；失败统一 401，超阈值 429。"""
    return await service.login(payload, ip=client_ip(request))


@router.post("/auth/refresh", response_model=TokenPair, summary="轮换刷新令牌")
async def refresh(
    payload: RefreshRequest,
    request: Request,
    service: ServiceDep,
) -> TokenPair:
    """旧 refresh 立即吊销，返回全新一对令牌。"""
    return await service.refresh(payload, ip=client_ip(request))


@router.post(
    "/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="登出并吊销刷新令牌",
)
async def logout(
    payload: LogoutRequest,
    request: Request,
    service: ServiceDep,
    user: CurrentUserDep,
) -> Response:
    """需要有效 access；提交的 refresh 令牌随即失效（幂等）。"""
    await service.logout(payload, user=user, ip=client_ip(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
