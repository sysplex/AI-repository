"""Notify 模块 REST API 端点（M10-T06），`CONTRACTS.md §1-§4` 与 `docs/05-api-spec.md §2.7`。

对外暴露完整的 `/api/v1/alerts/*` 与 `/api/v1/notification-channels/*` 端点体系：
- 提醒规则 CRUD、条件校验、即时开关
- M7 论文破裂规则批量导入
- 提醒触发审计流水检索
- 通知渠道配置 CRUD 与连通性测试
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.errors import NotFound, Unauthenticated
from app.core.logging import get_logger
from app.modules.notify.enums import AlertStatus, AlertType
from app.modules.notify.schemas import (
    AlertCreate,
    AlertHistoryRead,
    AlertRead,
    AlertUpdate,
    BatchThesisBreakersRequest,
    ChannelTestResult,
    NotificationChannelCreate,
    NotificationChannelRead,
    NotificationChannelUpdate,
)
from app.modules.notify.service import AlertService

__all__ = [
    "alerts_router",
    "channels_router",
    "check_channel_connectivity",
    "get_alert_service",
    "get_current_user",
    "set_alert_service_factory",
]

logger = get_logger("notify.api")

alerts_router = APIRouter()
channels_router = APIRouter()

_alert_service_factory: Callable[[AsyncSession], AlertService] | None = None


def set_alert_service_factory(factory: Callable[[AsyncSession], AlertService] | None) -> None:
    """设置 AlertService 自定义构建工厂（单元与集成测试辅助）。"""
    global _alert_service_factory
    _alert_service_factory = factory


def get_alert_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AlertService:
    """AlertService 依赖注入提供器。"""
    if _alert_service_factory is not None:
        return _alert_service_factory(session)
    return AlertService(session=session)


def get_current_user(request: Request) -> Any:
    """从 ASGI 请求上下文获取已通过鉴权的用户信息。"""
    user = getattr(request.state, "user", None)
    if user is None:
        raise Unauthenticated("需要登录才能访问提醒服务")
    return user


# =============================================================================
# 1. 提醒规则端点 (/api/v1/alerts)
# =============================================================================


@alerts_router.post(
    "",
    response_model=AlertRead,
    status_code=status.HTTP_201_CREATED,
    summary="创建智能提醒规则",
)
async def create_alert(
    data: AlertCreate,
    service: Annotated[AlertService, Depends(get_alert_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> AlertRead:
    """创建新的提醒规则，支持价格、技术指标、财报日以及投资论文破裂条件。"""
    return await service.create_alert(user_id=user.id, data=data)


@alerts_router.get(
    "",
    response_model=list[AlertRead],
    summary="查询用户的提醒规则列表",
)
async def list_alerts(
    service: Annotated[AlertService, Depends(get_alert_service)],
    user: Annotated[Any, Depends(get_current_user)],
    symbol: Annotated[str | None, Query(description="按股票代码过滤")] = None,
    alert_type: Annotated[AlertType | None, Query(description="按提醒类型过滤")] = None,
    status: Annotated[AlertStatus | None, Query(description="按规则状态过滤")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AlertRead]:
    """按条件过滤查询当前登录用户的提醒规则列表。"""
    return await service.list_alerts(
        user_id=user.id,
        symbol=symbol,
        alert_type=alert_type,
        status=status,
        limit=limit,
        offset=offset,
    )


@alerts_router.get(
    "/history",
    response_model=list[AlertHistoryRead],
    summary="查询提醒触发历史流水",
)
async def list_alert_history(
    service: Annotated[AlertService, Depends(get_alert_service)],
    user: Annotated[Any, Depends(get_current_user)],
    alert_id: Annotated[uuid.UUID | None, Query(description="按提醒规则 ID 过滤")] = None,
    symbol: Annotated[str | None, Query(description="按标的代码过滤")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AlertHistoryRead]:
    """查询提醒触发历史审计流水，记录触发时行情快照与渠道送达结果。"""
    return await service.list_history(
        user_id=user.id,
        alert_id=alert_id,
        symbol=symbol,
        limit=limit,
        offset=offset,
    )


@alerts_router.post(
    "/thesis-breakers",
    response_model=list[AlertRead],
    status_code=status.HTTP_201_CREATED,
    summary="批量导入 M7 投资论文破裂监控规则",
)
async def batch_create_thesis_breakers(
    data: BatchThesisBreakersRequest,
    service: Annotated[AlertService, Depends(get_alert_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> list[AlertRead]:
    """将 M7 长期持有耐久度评估输出的投资论文破裂项批量转为量化监控规则。"""
    return await service.batch_create_thesis_breakers(
        user_id=user.id,
        symbol=data.symbol,
        breakers=data.breakers,
        channel_ids=data.channel_ids,
        cooldown_minutes=data.cooldown_minutes,
    )


@alerts_router.get(
    "/{alert_id}",
    response_model=AlertRead,
    summary="获取单个提醒规则详情",
)
async def get_alert(
    alert_id: uuid.UUID,
    service: Annotated[AlertService, Depends(get_alert_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> AlertRead:
    """获取指定提醒规则详情并强制多租户安全隔离校验。"""
    alert = await service.get_alert(user_id=user.id, alert_id=alert_id)
    if not alert:
        raise NotFound(message="提醒规则不存在或无权访问")
    return alert


@alerts_router.patch(
    "/{alert_id}",
    response_model=AlertRead,
    summary="更新提醒规则属性与状态",
)
async def update_alert(
    alert_id: uuid.UUID,
    data: AlertUpdate,
    service: Annotated[AlertService, Depends(get_alert_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> AlertRead:
    """更新提醒规则属性（支持启停开关、条件微调与渠道变更）。"""
    alert = await service.update_alert(user_id=user.id, alert_id=alert_id, data=data)
    if not alert:
        raise NotFound(message="提醒规则不存在或无权访问")
    return alert


@alerts_router.delete(
    "/{alert_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除指定提醒规则",
)
async def delete_alert(
    alert_id: uuid.UUID,
    service: Annotated[AlertService, Depends(get_alert_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> None:
    """删除指定提醒规则。"""
    deleted = await service.delete_alert(user_id=user.id, alert_id=alert_id)
    if not deleted:
        raise NotFound(message="提醒规则不存在或无权访问")


# =============================================================================
# 2. 通知渠道管理端点 (/api/v1/notification-channels)
# =============================================================================


@channels_router.post(
    "",
    response_model=NotificationChannelRead,
    status_code=status.HTTP_201_CREATED,
    summary="创建用户通知渠道",
)
async def create_channel(
    data: NotificationChannelCreate,
    service: Annotated[AlertService, Depends(get_alert_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> NotificationChannelRead:
    """创建通知渠道（支持邮件、Webhook 与站内信）。"""
    return await service.create_channel(user_id=user.id, data=data)


@channels_router.get(
    "",
    response_model=list[NotificationChannelRead],
    summary="查询用户的所有通知渠道",
)
async def list_channels(
    service: Annotated[AlertService, Depends(get_alert_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> list[NotificationChannelRead]:
    """查询当前登录用户配置的所有通知渠道。"""
    return await service.list_channels(user_id=user.id)


@channels_router.get(
    "/{channel_id}",
    response_model=NotificationChannelRead,
    summary="获取单个通知渠道详情",
)
async def get_channel(
    channel_id: uuid.UUID,
    service: Annotated[AlertService, Depends(get_alert_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> NotificationChannelRead:
    """获取单个通知渠道配置。"""
    channel = await service.get_channel(user_id=user.id, channel_id=channel_id)
    if not channel:
        raise NotFound(message="通知渠道不存在或无权访问")
    return channel


@channels_router.patch(
    "/{channel_id}",
    response_model=NotificationChannelRead,
    summary="更新通知渠道配置",
)
async def update_channel(
    channel_id: uuid.UUID,
    data: NotificationChannelUpdate,
    service: Annotated[AlertService, Depends(get_alert_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> NotificationChannelRead:
    """更新通知渠道配置（名称、参数或启停状态）。"""
    channel = await service.update_channel(user_id=user.id, channel_id=channel_id, data=data)
    if not channel:
        raise NotFound(message="通知渠道不存在或无权访问")
    return channel


@channels_router.delete(
    "/{channel_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除指定通知渠道",
)
async def delete_channel(
    channel_id: uuid.UUID,
    service: Annotated[AlertService, Depends(get_alert_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> None:
    """删除指定的通知渠道。"""
    deleted = await service.delete_channel(user_id=user.id, channel_id=channel_id)
    if not deleted:
        raise NotFound(message="通知渠道不存在或无权访问")


@channels_router.post(
    "/{channel_id}/test",
    response_model=ChannelTestResult,
    summary="测试指定渠道网络连通性",
)
async def check_channel_connectivity(
    channel_id: uuid.UUID,
    service: Annotated[AlertService, Depends(get_alert_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> ChannelTestResult:
    """发送一条测试通知以验证渠道连通性与配置有效性。"""
    res = await service.test_channel(user_id=user.id, channel_id=channel_id)
    if not res:
        raise NotFound(message="通知渠道不存在或无权访问")
    return ChannelTestResult.model_validate(res)
