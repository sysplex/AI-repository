"""Scheduler 服务门面（M10-T05）。

提供收盘流水线触发与每日大盘/持仓简报查询接口。
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.modules.scheduler.enums import DailyReportType
from app.modules.scheduler.models import DailyReport
from app.modules.scheduler.pipeline import PostMarketPipeline
from app.modules.scheduler.schemas import DailyReportRead, PipelineRunResult

__all__ = ["SchedulerService"]

logger = get_logger("scheduler.service")


class SchedulerService:
    """收盘任务链调度与每日简报查询核心门面服务。"""

    def __init__(
        self,
        session: AsyncSession | None = None,
        pipeline: PostMarketPipeline | None = None,
    ) -> None:
        self._session = session
        self._pipeline = pipeline or PostMarketPipeline(session=session)

    def _get_session(self, session: AsyncSession | None) -> AsyncSession:
        sess = session or self._session
        if sess is None:
            raise ValueError("AsyncSession 必须传入或在 SchedulerService 构造时初始化。")
        return sess

    async def run_pipeline(
        self,
        *,
        trade_date: date | None = None,
        force: bool = False,
        market_context: dict[str, Any] | None = None,
        session: AsyncSession | None = None,
    ) -> PipelineRunResult:
        """手动或定时触发收盘后批处理任务链。"""
        sess = self._get_session(session)
        return await self._pipeline.run(
            trade_date=trade_date,
            force=force,
            session=sess,
            market_context=market_context,
        )

    async def get_daily_report(
        self,
        report_id: uuid.UUID,
        session: AsyncSession | None = None,
    ) -> DailyReportRead | None:
        """根据 ID 获取每日简报详情。"""
        sess = self._get_session(session)
        stmt = select(DailyReport).where(DailyReport.id == report_id)
        res = await sess.execute(stmt)
        report = res.scalar_one_or_none()
        if not report:
            return None
        return DailyReportRead.model_validate(report)

    async def list_daily_reports(
        self,
        *,
        user_id: uuid.UUID | None = None,
        report_date: date | None = None,
        report_type: DailyReportType | str | None = None,
        limit: int = 50,
        offset: int = 0,
        session: AsyncSession | None = None,
    ) -> list[DailyReportRead]:
        """按条件检索每日简报（公共大盘简报或个人持仓简报）。"""
        sess = self._get_session(session)
        stmt = select(DailyReport)

        if user_id is not None:
            stmt = stmt.where((DailyReport.user_id == user_id) | (DailyReport.user_id.is_(None)))
        else:
            # 未传 user_id 时默认只查公共大盘简报
            stmt = stmt.where(DailyReport.user_id.is_(None))

        if report_date is not None:
            stmt = stmt.where(DailyReport.report_date == report_date)

        if report_type is not None:
            val = (
                report_type.value if isinstance(report_type, DailyReportType) else str(report_type)
            )
            stmt = stmt.where(DailyReport.report_type == val)

        stmt = (
            stmt.order_by(
                DailyReport.report_date.desc(),
                DailyReport.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        res = await sess.execute(stmt)
        return [DailyReportRead.model_validate(r) for r in res.scalars().all()]
