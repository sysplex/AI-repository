"""Scheduler 领域枚举定义（M10-T01），`CONTRACTS.md §2-§3`。"""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "DailyReportType",
    "JobStatus",
]


class DailyReportType(StrEnum):
    """每日简报类型。"""

    MARKET_DIGEST = "market_digest"
    PORTFOLIO_DIGEST = "portfolio_digest"


class JobStatus(StrEnum):
    """调度任务执行状态。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
