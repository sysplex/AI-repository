"""Integration tests for SimBroker REST API endpoints and Broker Adapter (M4-T07).

Tests:
1. HARD-01 authentication enforcement (unauthenticated -> 401 UNAUTHENTICATED).
2. Authenticated REST endpoints (accounts, orders, positions, trades, risk, journal).
3. Idempotency-Key enforcement and duplicate submission handling.
4. Multi-tenant isolation (404 NOT_FOUND).
5. SimBroker adapter protocol compliance and in-memory execution.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user
from app.core.errors import NotFound
from app.modules.identity.enums import UserRole, UserStatus
from app.modules.identity.schemas import AuthenticatedUser, UserSettings
from app.modules.simbroker.adapter import SimBroker
from app.modules.simbroker.api import get_current_user, get_sim_service
from app.modules.simbroker.ports import BarProtocol, Broker
from app.modules.simbroker.schemas import (
    AccountOverview,
    AccountResponse,
    FeeModelConfig,
    OrderCreate,
    OrderResponse,
    PerformanceMetrics,
    PositionResponse,
    RiskOverview,
    TradeJournalResponse,
    TradeResponse,
)
from app.modules.simbroker.service import SimService

pytestmark = pytest.mark.integration


class DummyBar:
    """Mock candlestick bar implementing BarProtocol."""

    def __init__(
        self,
        trade_date: date,
        open_: str = "150.0",
        high: str = "155.0",
        low: str = "148.0",
        close: str = "152.0",
        volume: int = 100000,
    ) -> None:
        self.trade_date = trade_date
        self.open = Decimal(open_)
        self.high = Decimal(high)
        self.low = Decimal(low)
        self.close = Decimal(close)
        self.volume = volume


class DummyMarketFeed:
    """Mock MarketDataFeedProtocol."""

    def get_latest_price(self, symbol: str) -> Decimal | None:
        return Decimal("150.0000")

    def get_daily_bar(self, symbol: str, trade_date: date) -> BarProtocol | None:
        return DummyBar(
            trade_date=trade_date, open_="150.0", high="155.0", low="148.0", close="152.0"
        )

    def get_sp500_return(self, start_date: date, end_date: date) -> Decimal | None:
        return Decimal("5.0000")

    def get_symbol_sector(self, symbol: str) -> str | None:
        return "Technology"


@pytest.fixture
def auth_user() -> AuthenticatedUser:
    """Mock authenticated user for HARD-01."""
    return AuthenticatedUser(
        id=uuid.uuid4(),
        email="trader@example.com",
        role=UserRole.USER,
        status=UserStatus.ACTIVE,
        settings=UserSettings(),
    )


@pytest.fixture
def mock_sim_service() -> AsyncMock:
    """Mock SimService for API endpoint testing."""
    service = AsyncMock(spec=SimService)

    acc_id = uuid.uuid4()
    user_id = uuid.uuid4()
    order_id = uuid.uuid4()
    trade_id = uuid.uuid4()

    sample_account = AccountResponse(
        id=acc_id,
        user_id=user_id,
        name="Test Sim Account",
        initial_cash=Decimal("100000.0000"),
        cash=Decimal("100000.0000"),
        fee_model=FeeModelConfig(),
        slippage_bps=Decimal("5.0"),
        pdt_enabled=True,
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    service.create_account.return_value = sample_account
    service.list_accounts.return_value = [sample_account]

    sample_overview = AccountOverview(
        id=acc_id,
        name="Test Sim Account",
        status="active",
        initial_cash=Decimal("100000.0000"),
        cash=Decimal("100000.0000"),
        market_value=Decimal("0.0000"),
        equity=Decimal("100000.0000"),
        daily_pnl=Decimal("0.0000"),
        daily_pnl_pct=Decimal("0.0000"),
        total_pnl=Decimal("0.0000"),
        total_pnl_pct=Decimal("0.0000"),
        pdt_day_trades_count=0,
        pdt_warning=False,
    )
    service.get_account_overview.return_value = sample_overview

    service.deposit.return_value = Decimal("150000.0000")
    service.withdraw.return_value = Decimal("80000.0000")

    sample_order = OrderResponse(
        id=order_id,
        user_id=user_id,
        account_id=acc_id,
        symbol="AAPL",
        side="buy",
        type="market",
        qty=Decimal("10.0000"),
        limit_price=None,
        stop_price=None,
        tif="day",
        status="accepted",
        idempotency_key="key-test-001",
        source="manual",
        ai_report_id=None,
        note="test buy",
        reject_reason=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    service.submit_order.return_value = sample_order
    service.list_orders.return_value = [sample_order]

    sample_order_cancelled = OrderResponse(
        id=order_id,
        user_id=user_id,
        account_id=acc_id,
        symbol="AAPL",
        side="buy",
        type="market",
        qty=Decimal("10.0000"),
        limit_price=None,
        stop_price=None,
        tif="day",
        status="cancelled",
        idempotency_key="key-test-001",
        source="manual",
        ai_report_id=None,
        note="test buy",
        reject_reason=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    service.cancel_order.return_value = sample_order_cancelled

    sample_position = PositionResponse(
        id=uuid.uuid4(),
        account_id=acc_id,
        symbol="AAPL",
        qty=Decimal("10.0000"),
        avg_cost=Decimal("150.0000"),
        current_price=Decimal("155.0000"),
        market_value=Decimal("1550.0000"),
        unrealized_pnl=Decimal("50.0000"),
        unrealized_pnl_pct=Decimal("3.3333"),
        realized_pnl=Decimal("0.0000"),
        weight_pct=Decimal("1.5500"),
    )
    service.get_positions.return_value = [sample_position]

    sample_trade = TradeResponse(
        id=trade_id,
        user_id=user_id,
        account_id=acc_id,
        order_id=order_id,
        symbol="AAPL",
        side="buy",
        qty=Decimal("10.0000"),
        price=Decimal("150.0000"),
        fee=Decimal("1.0000"),
        realized_pnl=Decimal("0.0000"),
        executed_at=datetime.now(UTC),
    )
    service.get_trades.return_value = [sample_trade]

    sample_performance = PerformanceMetrics(
        account_id=acc_id,
        initial_cash=Decimal("100000.0000"),
        current_equity=Decimal("105000.0000"),
        total_return=Decimal("5000.0000"),
        total_return_pct=Decimal("5.0000"),
        max_drawdown=Decimal("1000.0000"),
        win_rate=Decimal("66.6667"),
        profit_loss_ratio=Decimal("2.5000"),
        total_trades=6,
        winning_trades=4,
        losing_trades=2,
        benchmark_return_pct=Decimal("3.0000"),
        alpha=Decimal("2.0000"),
        beta=Decimal("1.1000"),
        equity_curve=[],
    )
    service.get_performance.return_value = sample_performance

    sample_risk = RiskOverview(
        account_id=acc_id,
        cash_ratio=Decimal("98.4500"),
        single_stock_weights={"AAPL": Decimal("1.5500")},
        top_positions=[("AAPL", Decimal("1.5500"))],
        sector_weights={"Technology": Decimal("1.5500")},
        pdt_day_trades_count=0,
        pdt_warning=False,
    )
    service.get_risk.return_value = sample_risk

    sample_journal = TradeJournalResponse(
        id=uuid.uuid4(),
        trade_id=trade_id,
        tags=["breakout"],
        notes="Clean entry",
        mood="disciplined",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    service.update_trade_journal.return_value = sample_journal

    return service


def _setup_auth_override(
    app: FastAPI,
    auth_user: AuthenticatedUser,
    mock_sim_service: AsyncMock,
) -> None:
    """Helper to wire dependency overrides for authenticated requests."""

    async def _mock_current_user(request: Request) -> AuthenticatedUser:
        request.state.user = auth_user
        return auth_user

    app.dependency_overrides[current_user] = _mock_current_user
    app.dependency_overrides[get_current_user] = lambda: auth_user
    app.dependency_overrides[get_sim_service] = lambda: mock_sim_service


# =============================================================================
# 1. HARD-01 Authentication Guard Tests (Unauthenticated -> 401)
# =============================================================================


async def test_create_account_unauthenticated(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/sim/accounts", json={"name": "Test"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_list_accounts_unauthenticated(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/sim/accounts")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_get_account_overview_unauthenticated(client: httpx.AsyncClient) -> None:
    resp = await client.get(f"/api/v1/sim/accounts/{uuid.uuid4()}")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_deposit_unauthenticated(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        f"/api/v1/sim/accounts/{uuid.uuid4()}/deposit",
        json={"amount": "1000.0"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_withdraw_unauthenticated(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        f"/api/v1/sim/accounts/{uuid.uuid4()}/withdraw",
        json={"amount": "1000.0"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_submit_order_unauthenticated(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        f"/api/v1/sim/accounts/{uuid.uuid4()}/orders",
        json={"symbol": "AAPL", "side": "buy", "type": "market", "qty": "10.0"},
        headers={"Idempotency-Key": "test-key-1"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_list_orders_unauthenticated(client: httpx.AsyncClient) -> None:
    resp = await client.get(f"/api/v1/sim/accounts/{uuid.uuid4()}/orders")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_cancel_order_unauthenticated(client: httpx.AsyncClient) -> None:
    resp = await client.delete(f"/api/v1/sim/accounts/{uuid.uuid4()}/orders/{uuid.uuid4()}")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_get_positions_unauthenticated(client: httpx.AsyncClient) -> None:
    resp = await client.get(f"/api/v1/sim/accounts/{uuid.uuid4()}/positions")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_get_trades_unauthenticated(client: httpx.AsyncClient) -> None:
    resp = await client.get(f"/api/v1/sim/accounts/{uuid.uuid4()}/trades")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_get_performance_unauthenticated(client: httpx.AsyncClient) -> None:
    resp = await client.get(f"/api/v1/sim/accounts/{uuid.uuid4()}/performance")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_get_risk_unauthenticated(client: httpx.AsyncClient) -> None:
    resp = await client.get(f"/api/v1/sim/accounts/{uuid.uuid4()}/risk")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_update_journal_unauthenticated(client: httpx.AsyncClient) -> None:
    resp = await client.put(
        f"/api/v1/sim/trades/{uuid.uuid4()}/journal",
        json={"notes": "trade notes"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


# =============================================================================
# 2. Authenticated Endpoints Tests (200 / 201 OK)
# =============================================================================


async def test_create_account_authenticated(
    app: FastAPI,
    client: httpx.AsyncClient,
    mock_sim_service: AsyncMock,
    auth_user: AuthenticatedUser,
) -> None:
    _setup_auth_override(app, auth_user, mock_sim_service)

    resp = await client.post(
        "/api/v1/sim/accounts",
        json={"name": "Test Sim Account", "initial_cash": "100000.0000"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Sim Account"
    assert data["initial_cash"] == "100000.0000"
    mock_sim_service.create_account.assert_awaited_once()


async def test_list_accounts_authenticated(
    app: FastAPI,
    client: httpx.AsyncClient,
    mock_sim_service: AsyncMock,
    auth_user: AuthenticatedUser,
) -> None:
    _setup_auth_override(app, auth_user, mock_sim_service)

    resp = await client.get("/api/v1/sim/accounts")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["name"] == "Test Sim Account"


async def test_get_account_overview_authenticated(
    app: FastAPI,
    client: httpx.AsyncClient,
    mock_sim_service: AsyncMock,
    auth_user: AuthenticatedUser,
) -> None:
    _setup_auth_override(app, auth_user, mock_sim_service)
    acc_id = uuid.uuid4()

    resp = await client.get(f"/api/v1/sim/accounts/{acc_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Test Sim Account"
    assert data["equity"] == "100000.0000"
    mock_sim_service.get_account_overview.assert_awaited_once_with(
        account_id=acc_id, user_id=auth_user.id
    )


async def test_deposit_and_withdraw_authenticated(
    app: FastAPI,
    client: httpx.AsyncClient,
    mock_sim_service: AsyncMock,
    auth_user: AuthenticatedUser,
) -> None:
    _setup_auth_override(app, auth_user, mock_sim_service)
    acc_id = uuid.uuid4()

    # Deposit
    resp_dep = await client.post(
        f"/api/v1/sim/accounts/{acc_id}/deposit",
        json={"amount": "50000.0000"},
    )
    assert resp_dep.status_code == 200
    assert resp_dep.json()["cash"] == "150000.0000"
    mock_sim_service.deposit.assert_awaited_once_with(
        account_id=acc_id, amount=Decimal("50000.0000"), user_id=auth_user.id
    )

    # Withdraw
    resp_wd = await client.post(
        f"/api/v1/sim/accounts/{acc_id}/withdraw",
        json={"amount": "20000.0000"},
    )
    assert resp_wd.status_code == 200
    assert resp_wd.json()["cash"] == "80000.0000"
    mock_sim_service.withdraw.assert_awaited_once_with(
        account_id=acc_id, amount=Decimal("20000.0000"), user_id=auth_user.id
    )


async def test_submit_order_requires_idempotency_key(
    app: FastAPI,
    client: httpx.AsyncClient,
    mock_sim_service: AsyncMock,
    auth_user: AuthenticatedUser,
) -> None:
    """Missing Idempotency-Key header must return 400 Bad Request."""
    _setup_auth_override(app, auth_user, mock_sim_service)
    acc_id = uuid.uuid4()

    resp = await client.post(
        f"/api/v1/sim/accounts/{acc_id}/orders",
        json={"symbol": "AAPL", "side": "buy", "type": "market", "qty": "10.0000"},
    )
    assert resp.status_code == 400


async def test_submit_order_authenticated(
    app: FastAPI,
    client: httpx.AsyncClient,
    mock_sim_service: AsyncMock,
    auth_user: AuthenticatedUser,
) -> None:
    _setup_auth_override(app, auth_user, mock_sim_service)
    acc_id = uuid.uuid4()

    resp = await client.post(
        f"/api/v1/sim/accounts/{acc_id}/orders",
        json={"symbol": "AAPL", "side": "buy", "type": "market", "qty": "10.0000"},
        headers={"Idempotency-Key": "req-key-100"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["symbol"] == "AAPL"
    assert data["status"] == "accepted"
    mock_sim_service.submit_order.assert_awaited_once()


async def test_list_and_cancel_orders_authenticated(
    app: FastAPI,
    client: httpx.AsyncClient,
    mock_sim_service: AsyncMock,
    auth_user: AuthenticatedUser,
) -> None:
    _setup_auth_override(app, auth_user, mock_sim_service)
    acc_id = uuid.uuid4()
    order_id = uuid.uuid4()

    # List orders
    resp_list = await client.get(f"/api/v1/sim/accounts/{acc_id}/orders?status=accepted")
    assert resp_list.status_code == 200
    orders = resp_list.json()
    assert len(orders) == 1
    assert orders[0]["symbol"] == "AAPL"

    # Cancel order
    resp_cancel = await client.delete(f"/api/v1/sim/accounts/{acc_id}/orders/{order_id}")
    assert resp_cancel.status_code == 200
    cancelled = resp_cancel.json()
    assert cancelled["status"] == "cancelled"
    mock_sim_service.cancel_order.assert_awaited_once_with(
        account_id=acc_id, order_id=order_id, user_id=auth_user.id
    )


async def test_get_positions_and_trades_authenticated(
    app: FastAPI,
    client: httpx.AsyncClient,
    mock_sim_service: AsyncMock,
    auth_user: AuthenticatedUser,
) -> None:
    _setup_auth_override(app, auth_user, mock_sim_service)
    acc_id = uuid.uuid4()

    # Positions
    resp_pos = await client.get(f"/api/v1/sim/accounts/{acc_id}/positions")
    assert resp_pos.status_code == 200
    pos_data = resp_pos.json()
    assert len(pos_data) == 1
    assert pos_data[0]["symbol"] == "AAPL"

    # Trades
    resp_trades = await client.get(f"/api/v1/sim/accounts/{acc_id}/trades")
    assert resp_trades.status_code == 200
    trade_data = resp_trades.json()
    assert len(trade_data) == 1
    assert trade_data[0]["symbol"] == "AAPL"


async def test_get_performance_and_risk_authenticated(
    app: FastAPI,
    client: httpx.AsyncClient,
    mock_sim_service: AsyncMock,
    auth_user: AuthenticatedUser,
) -> None:
    _setup_auth_override(app, auth_user, mock_sim_service)
    acc_id = uuid.uuid4()

    # Performance
    resp_perf = await client.get(f"/api/v1/sim/accounts/{acc_id}/performance")
    assert resp_perf.status_code == 200
    perf_data = resp_perf.json()
    assert perf_data["total_return"] == "5000.0000"
    assert perf_data["alpha"] == "2.0000"

    # Risk
    resp_risk = await client.get(f"/api/v1/sim/accounts/{acc_id}/risk")
    assert resp_risk.status_code == 200
    risk_data = resp_risk.json()
    assert risk_data["cash_ratio"] == "98.4500"
    assert len(risk_data["single_stock_weights"]) == 1


async def test_update_trade_journal_authenticated(
    app: FastAPI,
    client: httpx.AsyncClient,
    mock_sim_service: AsyncMock,
    auth_user: AuthenticatedUser,
) -> None:
    _setup_auth_override(app, auth_user, mock_sim_service)
    trade_id = uuid.uuid4()

    resp = await client.put(
        f"/api/v1/sim/trades/{trade_id}/journal",
        json={"notes": "Good disciplined entry", "tags": ["breakout"], "mood": "disciplined"},
    )
    assert resp.status_code == 200
    journal_data = resp.json()
    assert journal_data["notes"] == "Clean entry"
    assert journal_data["tags"] == ["breakout"]


async def test_tenant_isolation_raises_404(
    app: FastAPI,
    client: httpx.AsyncClient,
    mock_sim_service: AsyncMock,
    auth_user: AuthenticatedUser,
) -> None:
    """Accessing another tenant's account returns 404 NOT_FOUND (C10 rule)."""
    _setup_auth_override(app, auth_user, mock_sim_service)
    mock_sim_service.get_account_overview.side_effect = NotFound("Account not found")

    resp = await client.get(f"/api/v1/sim/accounts/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


# =============================================================================
# 3. SimBroker Adapter Protocol Compliance & Unit Execution
# =============================================================================


def test_sim_broker_implements_protocol() -> None:
    """Verify SimBroker adapter implements Broker Protocol."""
    broker = SimBroker()
    assert isinstance(broker, Broker)
    assert broker.name == "SimBroker"


def test_sim_broker_submit_order_idempotency() -> None:
    """Verify submit_order idempotent replay with same idempotency_key."""
    broker = SimBroker(initial_cash=Decimal("50000.0000"))
    acc_id = str(uuid.uuid4())
    req = OrderCreate(
        symbol="AAPL",
        side="buy",
        type="limit",
        qty=Decimal("10.0000"),
        limit_price=Decimal("150.0000"),
    )

    o1 = broker.submit_order(account_id=acc_id, req=req, idempotency_key="key-idemp-1")
    assert o1.status == "accepted"
    assert o1.symbol == "AAPL"

    # Replay with same key
    o2 = broker.submit_order(account_id=acc_id, req=req, idempotency_key="key-idemp-1")
    assert o2.id == o1.id
    assert o2.status == o1.status


def test_sim_broker_process_bar_and_positions() -> None:
    """Verify limit order matching on bar, position creation, and account valuation."""
    feed = DummyMarketFeed()
    broker = SimBroker(
        initial_cash=Decimal("50000.0000"),
        market_feed=feed,
        slippage_bps=Decimal("0.0"),
    )
    acc_id = str(uuid.uuid4())
    req = OrderCreate(
        symbol="AAPL",
        side="buy",
        type="limit",
        qty=Decimal("10.0000"),
        limit_price=Decimal("150.0000"),
    )

    order = broker.submit_order(account_id=acc_id, req=req, idempotency_key="key-bar-1")
    assert order.status == "accepted"

    # Process bar at 2026-03-01: DummyBar low is 148.0 <= 150.0 -> fills at 150.0
    bar_dt = datetime(2026, 3, 1, 15, 0, tzinfo=UTC)
    trades = broker.process_bar(account_id=acc_id, bar_time=bar_dt)
    assert len(trades) == 1
    trade = trades[0]
    assert trade.symbol == "AAPL"
    assert trade.price == Decimal("150.0000")
    assert trade.qty == Decimal("10.0000")

    # Verify positions
    positions = broker.get_positions(account_id=acc_id)
    assert len(positions) == 1
    pos = positions[0]
    assert pos.symbol == "AAPL"
    assert pos.qty == Decimal("10.0000")
    assert pos.avg_cost == Decimal("150.0000")

    # Verify account
    overview = broker.get_account(account_id=acc_id)
    assert overview.status == "active"
    assert overview.market_value == Decimal("1500.0000")


def test_sim_broker_cancel_order() -> None:
    """Verify order cancellation in SimBroker."""
    broker = SimBroker(initial_cash=Decimal("50000.0000"))
    acc_id = str(uuid.uuid4())
    req = OrderCreate(
        symbol="MSFT",
        side="buy",
        type="limit",
        qty=Decimal("5.0000"),
        limit_price=Decimal("400.0000"),
    )

    order = broker.submit_order(account_id=acc_id, req=req, idempotency_key="key-cancel-1")
    assert order.status == "accepted"

    cancelled = broker.cancel_order(account_id=acc_id, order_id=str(order.id))
    assert cancelled.status == "cancelled"


@pytest.mark.integration
async def test_sim_service_postgres_closed_loop(db_session: AsyncSession) -> None:
    """真实 Postgres 闭环：创建账户(含 Decimal 手续费) -> 查询 -> 下单 -> 撤单 -> 重置 (P0-1)。"""
    from app.modules.identity.models import User
    from app.modules.simbroker.schemas import AccountCreate, FeeModelConfig

    test_user = User(
        id=uuid.uuid4(),
        email=f"sim-e2e-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="argon2$fake",  # noqa: S106
        settings={},
    )
    db_session.add(test_user)
    await db_session.flush()

    service = SimService(session=db_session)

    # 1. 创建账户（带包含 Decimal 的 fee_model 配置）
    req = AccountCreate(
        name="Postgres E2E Account",
        initial_cash=Decimal("100000.0000"),
        fee_model=FeeModelConfig(
            type="bps",
            per_share=Decimal("0.0050"),
            bps=Decimal("2.0000"),
            min_fee=Decimal("1.0000"),
            max_fee=Decimal("100.0000"),
        ),
        slippage_bps=Decimal("5.0"),
    )
    acc = await service.create_account(user_id=test_user.id, req=req)
    assert acc.name == "Postgres E2E Account"
    assert acc.cash == Decimal("100000.0000")
    assert acc.fee_model.per_share == Decimal("0.0050")

    # 2. 查询列表与概览
    accounts = await service.list_accounts(user_id=test_user.id)
    assert len(accounts) >= 1
    overview = await service.get_account_overview(account_id=acc.id, user_id=test_user.id)
    assert overview.cash == Decimal("100000.0000")

    # 3. 创建限价单
    order_req = OrderCreate(
        symbol="NVDA",
        side="buy",
        type="limit",
        qty=Decimal("10.0000"),
        limit_price=Decimal("120.0000"),
    )
    order = await service.submit_order(
        account_id=acc.id,
        user_id=test_user.id,
        req=order_req,
        idempotency_key=f"idem-{uuid.uuid4().hex[:8]}",
    )
    assert order.status == "accepted"
    assert order.symbol == "NVDA"

    # 4. 撤销订单
    cancelled = await service.cancel_order(
        account_id=acc.id,
        order_id=order.id,
        user_id=test_user.id,
    )
    assert cancelled.status == "cancelled"

    # 5. 重置账户
    reset_resp = await service.reset_account(account_id=acc.id, user_id=test_user.id)
    assert reset_resp.cash == Decimal("100000.0000")
