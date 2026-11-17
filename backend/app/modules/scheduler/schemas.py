"""Scheduler 领域 Pydantic 校验 Schema（M10-T01），`CONTRACTS.md §2.4`。"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.scheduler.enums import DailyReportType, JobStatus

__all__ = [
    "DailyReportCreate",
    "DailyReportFilter",
    "DailyReportRead",
    "JobStatus",
    "PipelineRunResult",
    "PipelineStepStatus",
]


class DailyReportCreate(BaseModel):
    """创建每日简报请求。"""

    user_id: uuid.UUID | None = Field(default=None, description="所属用户 ID，NULL 为公共大盘简报")
    report_date: date = Field(description="报告所属交易日")
    report_type: DailyReportType
    title: str = Field(min_length=1, max_length=256, description="日报标题")
    summary: str = Field(min_length=1, description="Markdown/文本核心摘要")
    payload: dict[str, Any] = Field(default_factory=dict, description="结构化详情快照")


class DailyReportRead(BaseModel):
    """每日简报详情响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID | None
    report_date: date
    report_type: DailyReportType
    title: str
    summary: str
    payload: dict[str, Any]
    created_at: datetime


class DailyReportFilter(BaseModel):
    """每日简报查询过滤器。"""

    report_date: date | None = None
    report_type: DailyReportType | None = None


# ==========================================
# 2. 收盘后批处理任务链 DAG 监控快照
# ==========================================


class PipelineStepStatus(BaseModel):
    """流水线单步执行状态。"""

    model_config = ConfigDict(frozen=True)

    name: str
    status: JobStatus
    started_at: datetime
    finished_at: datetime | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None


class PipelineRunResult(BaseModel):
    """收盘后批处理任务链完整执行结果快照。"""

    model_config = ConfigDict(frozen=True)

    trade_date: date
    status: JobStatus
    started_at: datetime
    finished_at: datetime | None = None
    is_trading_day: bool = True
    steps: list[PipelineStepStatus] = Field(default_factory=list)
    error_message: str | None = None
