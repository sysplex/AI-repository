"""M10 调度器端口与协议契约（T04 & T05）。"""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol, runtime_checkable

__all__ = ["ReviewServiceProtocol"]


@runtime_checkable
class ReviewServiceProtocol(Protocol):
    """AI 投资建议复盘回填与评估服务协议。"""

    async def backfill_outcomes(
        self,
        *,
        as_of: date | None = None,
        batch_size: int = 100,
        session: Any = None,
    ) -> list[Any]:
        """扫描历史研报并回填评估收益率。"""
        ...
