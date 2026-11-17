"""Scheduler 模块 REST API 端点（M10-T06），`CONTRACTS.md §1-§5` 与 `docs/05-api-spec.md §2.7`。

对外暴露 `/api/v1/reports/*` 与 `/api/v1/scheduler/*`：
- 每日收盘大盘研报与个人持仓复盘简报查询
- 收盘批处理流水线触发端点
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.errors import NotFound, Unauthenticated
from app.core.logging import get_logger
from app.modules.scheduler.enums import DailyReportType
from app.modules.scheduler.schemas import DailyReportRead, PipelineRunResult
from app.modules.scheduler.service import SchedulerService

__all__ = [
    "get_current_user",
    "get_scheduler_service",
    "reports_router",
    "scheduler_router",
    "set_scheduler_service_factory",
]

logger = get_logger("scheduler.api")

reports_router = APIRouter()
scheduler_router = APIRouter()

_scheduler_service_factory: Callable[[AsyncSession], SchedulerService] | None = None


def set_scheduler_service_factory(
    factory: Callable[[AsyncSession], SchedulerService] | None,
) -> None:
    """设置 SchedulerService 自定义构建工厂（测试辅助）。"""
    global _scheduler_service_factory
    _scheduler_service_factory = factory


def get_scheduler_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SchedulerService:
    """SchedulerService 依赖注入提供器。"""
    if _scheduler_service_factory is not None:
        return _scheduler_service_factory(session)
    return SchedulerService(session=session)


def get_current_user(request: Request) -> Any:
    """从 ASGI 请求上下文获取已通过鉴权的用户信息。"""
    user = getattr(request.state, "user", None)
    if user is None:
        raise Unauthenticated("需要登录才能访问简报与调度服务")
    return user


class RunPipelineRequest(BaseModel):
    """手动触发收盘批处理任务链请求。"""

    trade_date: date | None = Field(default=None, description="指定美股交易日（默认今日）")
    force: bool = Field(default=False, description="是否强制执行（忽略非交易日日历守卫）")


# =============================================================================
# 1. 每日简报端点 (/api/v1/reports/daily)
# =============================================================================


@reports_router.get(
    "/daily",
    response_model=list[DailyReportRead],
    summary="查询每日投研与持仓简报",
)
async def list_daily_reports(
    service: Annotated[SchedulerService, Depends(get_scheduler_service)],
    user: Annotated[Any, Depends(get_current_user)],
    report_date: Annotated[date | None, Query(alias="date", description="按交易日过滤")] = None,
    report_type: Annotated[DailyReportType | None, Query(description="按简报类型过滤")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[DailyReportRead]:
    """查询每日大盘复盘报告（market_digest）与用户个人持仓简报（portfolio_digest）。"""
    return await service.list_daily_reports(
        user_id=user.id,
        report_date=report_date,
        report_type=report_type,
        limit=limit,
        offset=offset,
    )


@reports_router.get(
    "/daily/{report_id}",
    response_model=DailyReportRead,
    summary="获取单个每日简报详情",
)
async def get_daily_report(
    report_id: uuid.UUID,
    service: Annotated[SchedulerService, Depends(get_scheduler_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> DailyReportRead:
    """根据 ID 获取每日简报详情。"""
    report = await service.get_daily_report(report_id=report_id)
    if not report:
        raise NotFound(message="报告不存在")
    # 租户隔离校验：私有简报若非当前用户则拒绝访问
    if report.user_id is not None and report.user_id != user.id:
        raise NotFound(message="报告不存在或无权访问")
    return report


# =============================================================================
# 2. 调度流水线执行端点 (/api/v1/scheduler/run-post-market)
# =============================================================================


@scheduler_router.post(
    "/run-post-market",
    response_model=PipelineRunResult,
    summary="手动/管理触发收盘批处理任务链",
)
async def run_post_market(
    data: RunPipelineRequest,
    service: Annotated[SchedulerService, Depends(get_scheduler_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> PipelineRunResult:
    """手动或补算执行收盘后批处理 DAG 流水线（支持 force 模式）。"""
    return await service.run_pipeline(
        trade_date=data.trade_date,
        force=data.force,
    )
