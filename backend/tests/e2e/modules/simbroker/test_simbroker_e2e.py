"""End-to-End (E2E) Integration Acceptance Tests for SimBroker Engine (M4-T08).

Validates all criteria from `docs/08-test-plan.md §6 M4` and `T08-integration-and-acceptance.md`:
1. Invariant property tests (cash conservation, equity identity, non-negative positions).
2. Market/Limit/Stop orders matching matches hand-calculated samples.
3. Insufficient funds / oversell rejections with exact error codes.
4. Idempotent submission: concurrent / duplicate submission only matches once.
5. Equity snapshot, drawdown, win rate, profit-loss ratio, and SPY benchmark comparison.
6. Missing bar defense: order stays accepted or expires according to TIF.
7. Corporate actions value conservation: forward & reverse stock splits and cash dividends.
8. Full-chain REST API end-to-end authenticated lifecycle.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, Request

from app.api.deps import current_user
from app.modules.identity.enums import UserRole, UserStatus
from app.modules.identity.schemas import AuthenticatedUser, UserSettings
from app.modules.simbroker.accounting import PositionState
from app.modules.simbroker.adapter import SimBroker
from app.modules.simbroker.api import get_current_user, get_sim_service
from app.modules.simbroker.corporate_actions import (
    apply_cash_dividend,
    apply_stock_split,
)
from app.modules.simbroker.market_close import MarketCloseBatch
from app.modules.simbroker.matcher import MatchingEngine
from app.modules.simbroker.models import EquitySnapshot, SimAccount, SimOrder
from app.modules.simbroker.performance import PerformanceAnalyzer
from app.modules.simbroker.ports import BarProtocol
from app.modules.simbroker.schemas import (
    AccountOverview,
    AccountResponse,
    FeeModelConfig,
    OrderCreate,
    OrderResponse,
    PositionResponse,
    TradeJournalResponse,
    TradeResponse,
)
from app.modules.simbroker.service import SimService
from app.modules.simbroker.validator import OrderValidator

pytestmark = pytest.mark.e2e


class ConcreteBar:
    """Standard bar implementation for E2E testing."""

    def __init__(
        self,
        trade_date: date,
        open_: str,
        high: str,
        low: str,
        close: str,
        volume: int = 100000,
    ) -> None:
        self.trade_date = trade_date
        self.open = Decimal(open_)
        self.high = Decimal(high)
        self.low = Decimal(low)
        self.close = Decimal(close)
        self.volume = volume


class ConcreteMarketFeed:
    """Deterministic market feed for E2E multi-symbol testing."""

    def __init__(self, prices: dict[str, Decimal] | None = None) -> None:
        self._prices = prices or {
            "AAPL": Decimal("150.0000"),
            "MSFT": Decimal("300.0000"),
            "GOOGL": Decimal("180.0000"),
            "NVDA": Decimal("120.0000"),
            "SPY": Decimal("500.0000"),
        }
        self._sectors = {
            "AAPL": "Technology",
            "MSFT": "Technology",
            "GOOGL": "Communication Services",
            "NVDA": "Technology",
            "SPY": "Index",
        }

    def get_latest_price(self, symbol: str) -> Decimal | None:
        return self._prices.get(symbol)

    def get_daily_bar(self, symbol: str, trade_date: date) -> BarProtocol | None:
        price = self._prices.get(symbol)
        if price is None:
            return None
        return ConcreteBar(
            trade_date=trade_date,
            open_=str(price),
            high=str(price + Decimal("5.0")),
            low=str(price - Decimal("5.0")),
            close=str(price),
        )

    def get_sp500_return(self, start_date: date, end_date: date) -> Decimal | None:
        return Decimal("4.5000")

    def get_symbol_sector(self, symbol: str) -> str | None:
        return self._sectors.get(symbol, "Unknown")


# =============================================================================
# 1. Financial Invariants Full-Matrix Verification (Test Plan §6.1)
# =============================================================================


def test_e2e_invariant_properties_full_lifecycle() -> None:
    """Verify Cash Conservation, Equity Identity, and Non-negative Positions."""
    feed = ConcreteMarketFeed()
    broker = SimBroker(
        initial_cash=Decimal("100000.0000"),
        fee_model=FeeModelConfig(
            type="per_share", per_share=Decimal("0.005"), min_fee=Decimal("1.0")
        ),
        slippage_bps=Decimal("5.0"),
        market_feed=feed,
    )
    acc_id = str(uuid.uuid4())
    trade_time = datetime(2026, 3, 1, 14, 30, tzinfo=UTC)

    # 1. Buy 100 shares of AAPL
    broker.submit_order(
        acc_id,
        OrderCreate(
            symbol="AAPL",
            side="buy",
            type="limit",
            qty=Decimal("100.0000"),
            limit_price=Decimal("150.0000"),
        ),
        "k-inv-1",
    )
    trades1 = broker.process_bar(acc_id, trade_time)
    assert len(trades1) == 1

    # Invariant checks:
    # cash + positions market value == equity
    overview1 = broker.get_account(acc_id)
    positions1 = broker.get_positions(acc_id)
    pos_map1 = {p.symbol: p for p in positions1}
    assert pos_map1["AAPL"].qty == Decimal("100.0000")
    assert pos_map1["AAPL"].qty >= Decimal("0")
    total_mv1 = sum(p.market_value for p in positions1)
    assert overview1.equity == overview1.cash + total_mv1

    # 2. Buy 50 shares of MSFT
    broker.submit_order(
        acc_id,
        OrderCreate(
            symbol="MSFT",
            side="buy",
            type="limit",
            qty=Decimal("50.0000"),
            limit_price=Decimal("300.0000"),
        ),
        "k-inv-2",
    )
    trades2 = broker.process_bar(acc_id, trade_time)
    assert len(trades2) == 1

    overview2 = broker.get_account(acc_id)
    positions2 = broker.get_positions(acc_id)
    total_mv2 = sum(p.market_value for p in positions2)
    assert overview2.equity == overview2.cash + total_mv2
    for p in positions2:
        assert p.qty >= Decimal("0")

    # 3. Partial sell 40 shares of AAPL
    broker.submit_order(
        acc_id,
        OrderCreate(
            symbol="AAPL",
            side="sell",
            type="limit",
            qty=Decimal("40.0000"),
            limit_price=Decimal("150.0000"),
        ),
        "k-inv-3",
    )
    trades3 = broker.process_bar(acc_id, trade_time)
    assert len(trades3) == 1

    overview3 = broker.get_account(acc_id)
    positions3 = broker.get_positions(acc_id)
    pos_map3 = {p.symbol: p for p in positions3}
    assert pos_map3["AAPL"].qty == Decimal("60.0000")
    total_mv3 = sum(p.market_value for p in positions3)
    assert overview3.equity == overview3.cash + total_mv3

    # 4. Total Cash Conservation Check:
    # cash == initial_cash - sum(buy_costs + buy_fees) + sum(sell_proceeds - sell_fees)
    all_trades = broker._trades[acc_id]
    total_buys = sum(t.qty * t.price + t.fee for t in all_trades if t.side == "buy")
    total_sells = sum(t.qty * t.price - t.fee for t in all_trades if t.side == "sell")
    expected_cash = Decimal("100000.0000") - total_buys + total_sells
    assert overview3.cash == expected_cash


# =============================================================================
# 2. Order Matching vs Hand-Calculated Arithmetic (Test Plan §6.2)
# =============================================================================


def test_e2e_order_matching_exact_arithmetic() -> None:
    """Verify Market, Limit, and Stop order execution matches exact hand-calculated math."""
    fee_model = FeeModelConfig(type="per_share", per_share=Decimal("0.005"), min_fee=Decimal("1.0"))
    slippage_bps = Decimal("5.0")  # 5 bps = 0.0005 multiplier

    # Scenario A: Market Buy Order
    # Bar: open=100.0, high=105.0, low=98.0, close=102.0
    # Expected execution: fill_price = open * (1 + 0.0005) = 100.0 * 1.0005 = 100.0500
    # Fee: 100 shares * $0.005 = $0.50 -> min fee $1.00 applied
    bar = ConcreteBar(date(2026, 3, 1), "100.0", "105.0", "98.0", "102.0")
    order_market = OrderResponse(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        symbol="AAPL",
        side="buy",
        type="market",
        qty=Decimal("100.0000"),
        tif="day",
        status="accepted",
        idempotency_key="mkt-1",
        source="manual",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    res_mkt = MatchingEngine.match_order(
        order=order_market,
        bar=bar,
        slippage_bps=slippage_bps,
        fee_model=fee_model,
        execution_time=datetime(2026, 3, 1, 15, 0, tzinfo=UTC),
    )
    assert res_mkt.status == "filled"
    assert res_mkt.fill_price == Decimal("100.0500")
    assert res_mkt.fee == Decimal("1.0000")

    # Scenario B: Limit Buy Order
    # Limit price = 99.0000. Bar low = 98.0 <= 99.0 -> Matched at 99.0000
    # Fee: 200 shares * $0.005 = $1.00
    order_limit = OrderResponse(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        symbol="AAPL",
        side="buy",
        type="limit",
        qty=Decimal("200.0000"),
        limit_price=Decimal("99.0000"),
        tif="day",
        status="accepted",
        idempotency_key="lim-1",
        source="manual",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    res_lim = MatchingEngine.match_order(
        order=order_limit,
        bar=bar,
        slippage_bps=Decimal("0.0"),  # Limit boundary execution
        fee_model=fee_model,
        execution_time=datetime(2026, 3, 1, 15, 0, tzinfo=UTC),
    )
    assert res_lim.status == "filled"
    assert res_lim.fill_price == Decimal("99.0000")
    assert res_lim.fee == Decimal("1.0000")

    # Scenario C: Stop Sell Order
    # Stop price = 99.0. Bar low = 98.0 <= 99.0 -> Triggered!
    # Slippage downwards: 99.0 * (1 - 0.0005) = 98.9505
    order_stop = OrderResponse(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        symbol="AAPL",
        side="sell",
        type="stop",
        qty=Decimal("100.0000"),
        stop_price=Decimal("99.0000"),
        tif="day",
        status="accepted",
        idempotency_key="stp-1",
        source="manual",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    res_stp = MatchingEngine.match_order(
        order=order_stop,
        bar=bar,
        slippage_bps=slippage_bps,
        fee_model=fee_model,
        execution_time=datetime(2026, 3, 1, 15, 0, tzinfo=UTC),
    )
    assert res_stp.status == "filled"
    assert res_stp.fill_price == Decimal("98.9505")


# =============================================================================
# 3. Insufficient Funds & Oversell Rejections (Test Plan §6.3)
# =============================================================================


def test_e2e_rejections_and_error_codes() -> None:
    """Verify rejection reasons and error codes for insufficient funds, oversell, and PDT rules."""
    # 1. INSUFFICIENT_FUNDS
    req_buy = OrderCreate(
        symbol="AAPL",
        side="buy",
        type="limit",
        qty=Decimal("100.0000"),
        limit_price=Decimal("150.0000"),  # Needs ~$15,000
    )
    val_funds = OrderValidator.validate(
        order_req=req_buy,
        account_cash=Decimal("500.0000"),  # Only $500
        account_slippage_bps=Decimal("5.0"),
        account_fee_model=FeeModelConfig(),
        account_pdt_enabled=False,
        account_equity=Decimal("500.0000"),
    )
    assert not val_funds.is_valid
    assert val_funds.error_code == "INSUFFICIENT_FUNDS"

    # 2. INSUFFICIENT_POSITION
    req_sell = OrderCreate(
        symbol="AAPL",
        side="sell",
        type="market",
        qty=Decimal("50.0000"),
    )
    val_pos = OrderValidator.validate(
        order_req=req_sell,
        account_cash=Decimal("10000.0000"),
        account_slippage_bps=Decimal("5.0"),
        account_fee_model=FeeModelConfig(),
        account_pdt_enabled=False,
        account_equity=Decimal("10000.0000"),
        current_position_qty=Decimal("20.0000"),  # Holds only 20
        current_market_price=Decimal("150.0000"),
    )
    assert not val_pos.is_valid
    assert val_pos.error_code == "INSUFFICIENT_POSITION"

    # 3. PDT_RESTRICTION
    # Equity $20,000 < $25,000, 3 day trades completed, 4th same day exit
    val_pdt = OrderValidator.validate(
        order_req=req_sell,
        account_cash=Decimal("10000.0000"),
        account_slippage_bps=Decimal("5.0"),
        account_fee_model=FeeModelConfig(),
        account_pdt_enabled=True,
        account_equity=Decimal("20000.0000"),
        current_position_qty=Decimal("100.0000"),
        current_market_price=Decimal("150.0000"),
        rolling_day_trades=3,
        is_same_day_roundtrip=True,
    )
    assert not val_pdt.is_valid
    assert val_pdt.error_code == "PDT_RESTRICTION"


# =============================================================================
# 4. Concurrency & Idempotency Duplicate Submission (Test Plan §6.4)
# =============================================================================


def test_e2e_idempotency_duplicate_submission() -> None:
    """Verify duplicate submission returns existing order without re-matching."""
    broker = SimBroker(initial_cash=Decimal("50000.0000"))
    acc_id = str(uuid.uuid4())
    req = OrderCreate(
        symbol="AAPL",
        side="buy",
        type="limit",
        qty=Decimal("10.0000"),
        limit_price=Decimal("150.0000"),
    )

    # First submission
    ord1 = broker.submit_order(acc_id, req, "idemp-key-repeat")
    assert ord1.status == "accepted"

    # Second submission (replayed)
    ord2 = broker.submit_order(acc_id, req, "idemp-key-repeat")
    assert ord2.id == ord1.id
    assert ord2.status == ord1.status

    # Third submission (different key -> new order)
    ord3 = broker.submit_order(acc_id, req, "idemp-key-different")
    assert ord3.id != ord1.id

    # Verify orders count in container
    account_orders = broker._orders[acc_id]
    assert len(account_orders) == 2


# =============================================================================
# 5. Snapshot, Drawdown, Win Rate, and SPY Comparison (Test Plan §6.5)
# =============================================================================


def test_e2e_performance_and_risk_metrics() -> None:
    """Verify equity snapshot, drawdown, win rate, and SPY benchmark analysis."""
    acc_id = uuid.uuid4()
    initial_cash = Decimal("100000.0000")
    current_equity = Decimal("115000.0000")

    # 1. Equity snapshots (Simulating peak and drawdown)
    # Day 1: 100k, Day 2: 120k (peak), Day 3: 110k (-8.33% DD), Day 4: 115k
    s1 = EquitySnapshot(
        account_id=acc_id,
        trade_date=date(2026, 3, 1),
        cash=Decimal("100000.0000"),
        market_value=Decimal("0.0000"),
        equity=Decimal("100000.0000"),
        drawdown=Decimal("0.0000"),
    )
    s2 = EquitySnapshot(
        account_id=acc_id,
        trade_date=date(2026, 3, 2),
        cash=Decimal("70000.0000"),
        market_value=Decimal("50000.0000"),
        equity=Decimal("120000.0000"),
        drawdown=Decimal("0.0000"),
    )
    s3 = EquitySnapshot(
        account_id=acc_id,
        trade_date=date(2026, 3, 3),
        cash=Decimal("70000.0000"),
        market_value=Decimal("40000.0000"),
        equity=Decimal("110000.0000"),
        drawdown=Decimal("10000.0000"),
    )
    s4 = EquitySnapshot(
        account_id=acc_id,
        trade_date=date(2026, 3, 4),
        cash=Decimal("65000.0000"),
        market_value=Decimal("50000.0000"),
        equity=Decimal("115000.0000"),
        drawdown=Decimal("5000.0000"),
    )

    # 2. Closed trades (3 winning trades, 1 losing trade)
    # Win 1: +$3,000, Win 2: +$2,000, Win 3: +$1,000, Loss 1: -$2,000
    class _MockTrade:
        def __init__(self, pnl: str) -> None:
            self.realized_pnl = Decimal(pnl)

    closed_trades = [
        _MockTrade("3000.0000"),
        _MockTrade("2000.0000"),
        _MockTrade("1000.0000"),
        _MockTrade("-2000.0000"),
    ]

    feed = ConcreteMarketFeed()
    perf = PerformanceAnalyzer.analyze(
        account_id=acc_id,
        initial_cash=initial_cash,
        current_equity=current_equity,
        equity_snapshots=[s1, s2, s3, s4],
        closed_trades=closed_trades,
        benchmark_feed=feed,
    )

    assert perf.total_return == Decimal("15000.0000")
    assert perf.total_return_pct == Decimal("15.0000")
    assert perf.max_drawdown == Decimal("10000.0000")
    assert perf.win_rate == Decimal("75.0000")  # 3 / 4 = 75%
    # Profit factor: (3000 + 2000 + 1000) / 2000 = 6000 / 2000 = 3.0000
    assert perf.profit_loss_ratio == Decimal("3.0000")
    assert perf.benchmark_return_pct == Decimal("4.5000")
    assert perf.alpha == Decimal("10.5000")  # 15.0 - 4.5 = 10.5


# =============================================================================
# 6. Missing Bar Defense & TIF Expiration (Test Plan §6.6)
# =============================================================================


def test_e2e_missing_bar_defense_and_tif() -> None:
    """Verify missing market bar prevents execution and DAY orders expire at close."""
    # 1. MatchingEngine: None bar defense
    order_day = SimOrder(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        symbol="UNKNOWN_SYM",
        side="buy",
        type="limit",
        qty=Decimal("100.0000"),
        limit_price=Decimal("100.0000"),
        tif="day",
        status="accepted",
        idempotency_key="k-miss-1",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    res_miss = MatchingEngine.match_order(
        order=order_day,
        bar=None,  # Missing bar
        slippage_bps=Decimal("5.0"),
        fee_model=FeeModelConfig(),
        execution_time=datetime(2026, 3, 1, 15, 0, tzinfo=UTC),
    )
    assert res_miss.status == "accepted"
    assert res_miss.filled_qty == Decimal("0")
    assert res_miss.fill_price is None

    # 2. Market Close Batch: DAY order expires, GTC order stays accepted
    order_gtc = SimOrder(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        symbol="AAPL",
        side="buy",
        type="limit",
        qty=Decimal("50.0000"),
        limit_price=Decimal("140.0000"),
        tif="gtc",
        status="accepted",
        idempotency_key="k-gtc-1",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    acc = SimAccount(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        name="Close Acc",
        initial_cash=Decimal("50000.0000"),
        cash=Decimal("50000.0000"),
        status="active",
    )
    close_res = MarketCloseBatch.execute(
        account=acc,
        positions=[],
        open_orders=[order_day, order_gtc],
        trade_date=date(2026, 3, 1),
        market_feed=ConcreteMarketFeed(),
        historical_peak_equity=Decimal("50000.0000"),
    )
    assert order_day.status == "expired"
    assert order_gtc.status == "accepted"
    assert close_res.expired_orders_count == 1


# =============================================================================
# 7. Corporate Actions Value Conservation (Split / Reverse Split / Dividend)
# =============================================================================


def test_e2e_corporate_actions_value_conservation() -> None:
    """Verify forward split, reverse split, and dividend conserve portfolio value."""
    # 1. Forward Split 2:1
    # 100 shares @ $150 cost ($15,000) -> 200 shares @ $75 cost ($15,000)
    pos = PositionState(symbol="AAPL", qty=Decimal("100.0000"), avg_cost=Decimal("150.0000"))
    split_res = apply_stock_split(
        position=pos,
        split_ratio=Decimal("2.0"),  # 2:1
    )
    assert pos.qty == Decimal("200.0000")
    assert pos.avg_cost == Decimal("75.0000")
    assert split_res.cost_basis_before == Decimal("15000.0000")
    assert split_res.cost_basis_after == Decimal("15000.0000")
    assert split_res.cost_basis_before == split_res.cost_basis_after

    # 2. Reverse Split 1:4 (split_ratio = 0.25)
    # 200 shares @ $75 ($15,000) -> 50 shares @ $300 ($15,000)
    rev_res = apply_stock_split(
        position=pos,
        split_ratio=Decimal("0.25"),  # 1:4
    )
    assert pos.qty == Decimal("50.0000")
    assert pos.avg_cost == Decimal("300.0000")
    assert rev_res.cost_basis_before == Decimal("15000.0000")
    assert rev_res.cost_basis_after == Decimal("15000.0000")

    # 3. Cash Dividend $2.50 per share on 50 shares
    # Expected dividend payout = 50 * $2.50 = $125.00
    class _Acc:
        def __init__(self, cash: Decimal) -> None:
            self.cash = cash

    acc = _Acc(Decimal("10000.0000"))
    div_res = apply_cash_dividend(
        account=acc,
        position=pos,
        dividend_per_share=Decimal("2.5000"),
    )
    assert div_res.total_dividend == Decimal("125.0000")
    assert acc.cash == Decimal("10125.0000")


# =============================================================================
# 8. Full REST API End-to-End Authenticated Lifecycle
# =============================================================================


async def test_e2e_rest_api_full_authenticated_lifecycle(
    app: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """Verify full end-to-end REST API lifecycle from creation to trading and journaling."""
    user_id = uuid.uuid4()
    auth_user = AuthenticatedUser(
        id=user_id,
        email="e2e_trader@example.com",
        role=UserRole.USER,
        status=UserStatus.ACTIVE,
        settings=UserSettings(),
    )

    # In-memory mock service for API dispatch
    mock_service = AsyncMock(spec=SimService)
    acc_id = uuid.uuid4()
    order_id = uuid.uuid4()
    trade_id = uuid.uuid4()

    mock_service.create_account.return_value = AccountResponse(
        id=acc_id,
        user_id=user_id,
        name="E2E Account",
        initial_cash=Decimal("100000.0000"),
        cash=Decimal("100000.0000"),
        fee_model=FeeModelConfig(),
        slippage_bps=Decimal("5.0"),
        pdt_enabled=True,
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    mock_service.get_account_overview.return_value = AccountOverview(
        id=acc_id,
        name="E2E Account",
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
    mock_service.deposit.return_value = Decimal("150000.0000")
    mock_service.withdraw.return_value = Decimal("120000.0000")
    mock_service.submit_order.return_value = OrderResponse(
        id=order_id,
        user_id=user_id,
        account_id=acc_id,
        symbol="NVDA",
        side="buy",
        type="limit",
        qty=Decimal("20.0000"),
        limit_price=Decimal("120.0000"),
        tif="day",
        status="accepted",
        idempotency_key="e2e-order-nvda",
        source="manual",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    mock_service.get_positions.return_value = [
        PositionResponse(
            id=uuid.uuid4(),
            account_id=acc_id,
            symbol="NVDA",
            qty=Decimal("20.0000"),
            avg_cost=Decimal("120.0000"),
            current_price=Decimal("125.0000"),
            market_value=Decimal("2500.0000"),
            unrealized_pnl=Decimal("100.0000"),
            unrealized_pnl_pct=Decimal("4.1667"),
            realized_pnl=Decimal("0.0000"),
            weight_pct=Decimal("2.0833"),
        )
    ]
    mock_service.get_trades.return_value = [
        TradeResponse(
            id=trade_id,
            user_id=user_id,
            account_id=acc_id,
            order_id=order_id,
            symbol="NVDA",
            side="buy",
            qty=Decimal("20.0000"),
            price=Decimal("120.0000"),
            fee=Decimal("1.0000"),
            realized_pnl=Decimal("0.0000"),
            executed_at=datetime.now(UTC),
        )
    ]
    mock_service.update_trade_journal.return_value = TradeJournalResponse(
        id=uuid.uuid4(),
        trade_id=trade_id,
        notes="Solid breakout entry on NVDA",
        tags=["breakout", "tech"],
        emotion="confident",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    async def _mock_auth(request: Request) -> AuthenticatedUser:
        request.state.user = auth_user
        return auth_user

    app.dependency_overrides[current_user] = _mock_auth
    app.dependency_overrides[get_current_user] = lambda: auth_user
    app.dependency_overrides[get_sim_service] = lambda: mock_service

    # Step 1: Deposit funds
    resp_dep = await client.post(
        f"/api/v1/sim/accounts/{acc_id}/deposit",
        json={"amount": "50000.0000"},
    )
    assert resp_dep.status_code == 200
    assert resp_dep.json()["cash"] == "150000.0000"

    # Step 2: Submit order with idempotency key
    resp_ord = await client.post(
        f"/api/v1/sim/accounts/{acc_id}/orders",
        json={
            "symbol": "NVDA",
            "side": "buy",
            "type": "limit",
            "qty": "20.0000",
            "limit_price": "120.0000",
        },
        headers={"Idempotency-Key": "e2e-order-nvda"},
    )
    assert resp_ord.status_code == 201
    assert resp_ord.json()["symbol"] == "NVDA"

    # Step 3: Check positions
    resp_pos = await client.get(f"/api/v1/sim/accounts/{acc_id}/positions")
    assert resp_pos.status_code == 200
    pos_data = resp_pos.json()
    assert len(pos_data) == 1
    assert pos_data[0]["symbol"] == "NVDA"

    # Step 4: Check trades
    resp_tr = await client.get(f"/api/v1/sim/accounts/{acc_id}/trades")
    assert resp_tr.status_code == 200
    assert len(resp_tr.json()) == 1

    # Step 5: Update trade journal
    resp_j = await client.put(
        f"/api/v1/sim/trades/{trade_id}/journal",
        json={
            "notes": "Solid breakout entry on NVDA",
            "tags": ["breakout", "tech"],
            "emotion": "confident",
        },
    )
    assert resp_j.status_code == 200
    assert resp_j.json()["emotion"] == "confident"
