"""单元测试：AI 建议复盘 REST API 端点（M10-T06）。

测试覆盖：
- ReviewService 依赖注入与工厂覆盖
- `/api/v1/reviews/ai-outcomes` 复盘看板聚合统计查询
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.ai.api import (
    get_ai_outcomes,
    get_review_service,
    set_review_service_factory,
)
from app.modules.ai.schemas import ReviewSummaryResponse, VerdictStatsResponse

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_user() -> MagicMock:
    user = MagicMock()
    return user


def test_get_review_service_default() -> None:
    set_review_service_factory(None)
    session = AsyncMock()
    svc = get_review_service(session)
    assert svc is not None


def test_set_review_service_factory_override() -> None:
    custom_mock = MagicMock()
    set_review_service_factory(lambda sess: custom_mock)
    assert get_review_service(AsyncMock()) is custom_mock
    set_review_service_factory(None)


@pytest.mark.asyncio
async def test_get_ai_outcomes_api(mock_user: MagicMock) -> None:
    service = AsyncMock()
    mock_summary = ReviewSummaryResponse(
        total_recommendations=10,
        evaluated_count=8,
        avg_return_5d=Decimal("0.025"),
        avg_return_20d=Decimal("0.058"),
        avg_return_60d=Decimal("0.112"),
        avg_alpha_20d=Decimal("0.031"),
        win_rate_20d=Decimal("0.75"),
        by_verdict={
            "buy": VerdictStatsResponse(
                verdict="buy",
                total_count=6,
                evaluated_5d_count=6,
                evaluated_20d_count=6,
                evaluated_60d_count=4,
                avg_return_20d=Decimal("0.072"),
                win_rate_20d=Decimal("0.8333"),
            )
        },
        items=[],
    )
    service.get_outcomes_summary.return_value = mock_summary

    res = await get_ai_outcomes(
        service=service,
        _user=mock_user,
        verdict="buy",
        symbol="AAPL",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 11, 17),
        limit=50,
        offset=0,
    )

    assert res.total_recommendations == 10
    assert res.evaluated_count == 8
    assert res.win_rate_20d == Decimal("0.75")
    assert "buy" in res.by_verdict
    assert res.by_verdict["buy"].win_rate_20d == Decimal("0.8333")

    service.get_outcomes_summary.assert_awaited_once_with(
        verdict="buy",
        symbol="AAPL",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 11, 17),
        limit=50,
        offset=0,
    )
