"""Integration tests for Strategy REST API endpoints (M3 / T06).

Tests authentication enforcement (HARD-01), parameter validation, and endpoint responses.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import current_user
from app.modules.identity.enums import UserRole, UserStatus
from app.modules.identity.schemas import AuthenticatedUser, UserSettings
from app.modules.strategy.api import get_strategy_service
from app.modules.strategy.schemas import (
    BacktestResult,
    Signal,
    StrategyMetadata,
    TechnicalSnapshot,
)
from app.modules.strategy.service import StrategyService

pytestmark = pytest.mark.integration


class DummyBar:
    """Mock candlestick bar."""

    def __init__(
        self,
        trade_date: date,
        open_: str,
        high: str,
        low: str,
        close: str,
        volume: int = 1000,
    ) -> None:
        self.trade_date = trade_date
        self.open = Decimal(open_)
        self.high = Decimal(high)
        self.low = Decimal(low)
        self.close = Decimal(close)
        self.volume = volume


@pytest.fixture
def mock_strategy_service() -> AsyncMock:
    """Mock for StrategyService."""
    service = AsyncMock(spec=StrategyService)

    sample_metadata = [
        StrategyMetadata(
            id="turtle_20_55",
            display_name="Turtle 20/55",
            category="trend",
            description="Classic Turtle Trend Following",
            requires=["bars"],
            default_params={"entry_window": 20, "exit_window": 10},
        )
    ]
    service.list_strategies.return_value = sample_metadata

    sample_signal = Signal(
        strategy_id="turtle_20_55",
        symbol="AAPL",
        as_of=date(2026, 3, 1),
        direction="long",
        strength=80,
        reasons=["Breakout 20-day high"],
        levels={"entry": Decimal("150.0"), "stop": Decimal("140.0")},
        metrics={"atr": "5.0"},
    )
    service.evaluate.return_value = sample_signal
    service.scan.return_value = [sample_signal]

    sample_snapshot = TechnicalSnapshot(
        symbol="AAPL",
        as_of=date(2026, 3, 1),
        sma_20=Decimal("150.0"),
        sma_50=Decimal("145.0"),
        sma_200=Decimal("130.0"),
        rsi_14=Decimal("62.5"),
        macd=Decimal("2.5"),
        macd_signal=Decimal("2.0"),
        macd_hist=Decimal("0.5"),
        atr_14=Decimal("3.5"),
    )
    service.compute_technical_snapshot.return_value = sample_snapshot

    sample_backtest = BacktestResult(
        strategy_id="turtle_20_55",
        symbol="AAPL",
        start=date(2026, 1, 1),
        end=date(2026, 3, 1),
        initial_capital=Decimal("100000.0"),
        final_equity=Decimal("115000.0"),
        total_return_pct=Decimal("15.0"),
        annualized_return_pct=Decimal("60.0"),
        max_drawdown_pct=Decimal("4.5"),
        win_rate=Decimal("75.0"),
        profit_factor=Decimal("2.5"),
        total_trades=4,
        trades=[],
        equity_curve=[],
    )
    service.backtest.return_value = sample_backtest

    return service


@pytest.fixture
def auth_user() -> AuthenticatedUser:
    """Mock authenticated user for HARD-01."""
    return AuthenticatedUser(
        id=uuid.uuid4(),
        email="test_user@example.com",
        role=UserRole.USER,
        status=UserStatus.ACTIVE,
        settings=UserSettings(),
    )


# =============================================================================
# HARD-01 Authentication Guard Tests (Unauthenticated -> 401)
# =============================================================================


async def test_list_strategies_unauthenticated(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/strategy/list")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_evaluate_unauthenticated(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/strategy/evaluate",
        json={"strategy_id": "turtle_20_55", "symbol": "AAPL", "as_of": "2026-03-01"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_scan_unauthenticated(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/strategy/scan",
        json={"strategy_id": "turtle_20_55", "symbols": ["AAPL"], "as_of": "2026-03-01"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_technical_snapshot_unauthenticated(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/strategy/technical/AAPL")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_backtest_unauthenticated(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/strategy/backtest",
        json={
            "strategy_id": "turtle_20_55",
            "symbol": "AAPL",
            "start": "2026-01-01",
            "end": "2026-03-01",
        },
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


# =============================================================================
# Authenticated Endpoints Tests (200 OK)
# =============================================================================


async def test_list_strategies_authenticated(
    app: FastAPI,
    client: httpx.AsyncClient,
    mock_strategy_service: AsyncMock,
    auth_user: AuthenticatedUser,
) -> None:
    app.dependency_overrides[current_user] = lambda: auth_user
    app.dependency_overrides[get_strategy_service] = lambda: mock_strategy_service

    resp = await client.get("/api/v1/strategy/list")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["id"] == "turtle_20_55"


async def test_evaluate_authenticated(
    app: FastAPI,
    client: httpx.AsyncClient,
    mock_strategy_service: AsyncMock,
    auth_user: AuthenticatedUser,
) -> None:
    app.dependency_overrides[current_user] = lambda: auth_user
    app.dependency_overrides[get_strategy_service] = lambda: mock_strategy_service

    resp = await client.post(
        "/api/v1/strategy/evaluate",
        json={"strategy_id": "turtle_20_55", "symbol": "AAPL", "as_of": "2026-03-01"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["strategy_id"] == "turtle_20_55"
    assert data["symbol"] == "AAPL"
    assert data["direction"] == "long"
    assert data["strength"] == 80


async def test_scan_authenticated(
    app: FastAPI,
    client: httpx.AsyncClient,
    mock_strategy_service: AsyncMock,
    auth_user: AuthenticatedUser,
) -> None:
    app.dependency_overrides[current_user] = lambda: auth_user
    app.dependency_overrides[get_strategy_service] = lambda: mock_strategy_service

    resp = await client.post(
        "/api/v1/strategy/scan",
        json={
            "strategy_id": "turtle_20_55",
            "symbols": ["AAPL", "MSFT"],
            "as_of": "2026-03-01",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["symbol"] == "AAPL"


async def test_technical_snapshot_authenticated(
    app: FastAPI,
    client: httpx.AsyncClient,
    mock_strategy_service: AsyncMock,
    auth_user: AuthenticatedUser,
) -> None:
    app.dependency_overrides[current_user] = lambda: auth_user
    app.dependency_overrides[get_strategy_service] = lambda: mock_strategy_service

    resp = await client.get("/api/v1/strategy/technical/AAPL?as_of=2026-03-01")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "AAPL"
    assert data["as_of"] == "2026-03-01"
    assert data["rsi_14"] == "62.5"


async def test_backtest_authenticated(
    app: FastAPI,
    client: httpx.AsyncClient,
    mock_strategy_service: AsyncMock,
    auth_user: AuthenticatedUser,
) -> None:
    app.dependency_overrides[current_user] = lambda: auth_user
    app.dependency_overrides[get_strategy_service] = lambda: mock_strategy_service

    resp = await client.post(
        "/api/v1/strategy/backtest",
        json={
            "strategy_id": "turtle_20_55",
            "symbol": "AAPL",
            "start": "2026-01-01",
            "end": "2026-03-01",
            "initial_capital": "100000.00",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["strategy_id"] == "turtle_20_55"
    assert data["total_return_pct"] == "15.0"
    assert data["win_rate"] == "75.0"


# =============================================================================
# Validation and Error Handling Tests
# =============================================================================


async def test_scan_empty_symbols_validation_error(
    app: FastAPI,
    client: httpx.AsyncClient,
    auth_user: AuthenticatedUser,
) -> None:
    app.dependency_overrides[current_user] = lambda: auth_user

    resp = await client.post(
        "/api/v1/strategy/scan",
        json={"strategy_id": "turtle_20_55", "symbols": [], "as_of": "2026-03-01"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_backtest_missing_required_fields(
    app: FastAPI,
    client: httpx.AsyncClient,
    auth_user: AuthenticatedUser,
) -> None:
    app.dependency_overrides[current_user] = lambda: auth_user

    resp = await client.post(
        "/api/v1/strategy/backtest",
        json={"strategy_id": "turtle_20_55"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
