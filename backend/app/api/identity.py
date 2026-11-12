"""Identity HTTP 端点（T04 主干），`CONTRACTS.md §10`。

路径按 `docs/05-api-spec.md §2.1` 声明为完整相对路径（`/auth/...`），
由 `router.py` 一次性 `include_router` 到 `/api/v1` 之下，T05 直接在本文件追加
`/me`、`/admin/users`，无需再次改路由聚合。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.api.deps import (
    client_ip,
    current_user,
    get_identity_service,
    require_role,
)
from app.modules.identity.schemas import (
    AuthenticatedUser,
    LoginRequest,
    LogoutRequest,
    PaginatedUsers,
    RefreshRequest,
    RegisterRequest,
    SettingsUpdate,
    TokenPair,
    UsageResponse,
    UserPublic,
    UserRole,
)
from app.modules.identity.service import IdentityService

router = APIRouter(tags=["identity"])

ServiceDep = Annotated[IdentityService, Depends(get_identity_service)]
CurrentUserDep = Annotated[AuthenticatedUser, Depends(current_user)]
AdminDep = Annotated[AuthenticatedUser, Depends(require_role(UserRole.ADMIN))]


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


# ---------------------------------------------------------------- T05：自助


@router.get("/me", response_model=UserPublic, summary="我的资料")
async def get_me(user: CurrentUserDep, service: ServiceDep) -> UserPublic:
    """返回当前令牌对应用户的公开视图（不含任何凭据字段）。"""
    return await service.get_profile(user)


@router.patch("/me", response_model=UserPublic, summary="更新我的设置")
async def update_me(
    payload: SettingsUpdate,
    user: CurrentUserDep,
    service: ServiceDep,
) -> UserPublic:
    """整体替换设置项（风险偏好/语言/默认账户），写 `auth.settings_updated` 审计。"""
    return await service.update_settings(user, payload)


@router.get("/me/usage", response_model=UsageResponse, summary="我的 AI 用量与配额")
async def get_my_usage(user: CurrentUserDep, service: ServiceDep) -> UsageResponse:
    """当日用量；无记录返回全 0，`quota` 取 `AI_DAILY_QUOTA`（M1 只读，裁定 C6）。"""
    return await service.get_usage(user)


# ---------------------------------------------------------------- T05：管理


@router.get("/admin/users", response_model=PaginatedUsers, summary="用户列表（admin）")
async def list_users(
    admin: AdminDep,
    service: ServiceDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedUsers:
    """仅 admin 可访问；非 admin 403（`CONTRACTS §12`）。"""
    del admin
    return await service.list_users(page=page, page_size=page_size)
