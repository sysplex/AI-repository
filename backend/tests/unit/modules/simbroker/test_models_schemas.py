"""M4-T01 单元测试：领域模型、SQLAlchemy 实体、DTO Schema 与 Ports 契约。"""

from __future__ import annotations

import importlib.util
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.modules.simbroker.models import (
    EquitySnapshot,
    SimAccount,
    SimOrder,
    SimPosition,
    SimTrade,
    TradeJournal,
)
from app.modules.simbroker.ports import (
    BarProtocol,
    Broker,
    CorporateActionFeedProtocol,
    MarketDataFeedProtocol,
)
from app.modules.simbroker.schemas import (
    AccountCreate,
    AccountOverview,
    AccountResponse,
    DepositRequest,
    EquitySnapshotResponse,
    FeeModelConfig,
    OrderCreate,
    OrderResponse,
    PerformanceMetrics,
    PositionResponse,
    RiskOverview,
    TradeJournalResponse,
    TradeJournalUpdate,
    TradeResponse,
)


def _load_migration_module() -> Any:
    migration_path = (
        Path(__file__).resolve().parents[4] / "alembic" / "versions" / "0004_simbroker.py"
    )
    spec = importlib.util.spec_from_file_location("m0004_simbroker", migration_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestSimbrokerOrmModels:
    """SQLAlchemy ORM 实体属性与表映射测试"""

    def test_sim_account_model(self) -> None:
        acc_id = uuid.uuid4()
        user_id = uuid.uuid4()
        acc = SimAccount(
            id=acc_id,
            user_id=user_id,
            name="Alpha Fund",
            initial_cash=Decimal("50000.0000"),
            cash=Decimal("50000.0000"),
            fee_model={"type": "per_share", "per_share": "0.005"},
            slippage_bps=Decimal("3.0000"),
            pdt_enabled=True,
            status="active",
        )
        assert acc.id == acc_id
        assert acc.user_id == user_id
        assert acc.name == "Alpha Fund"
        assert acc.cash == Decimal("50000.0000")
        assert acc.fee_model["type"] == "per_share"
        assert acc.__tablename__ == "sim_accounts"

    def test_sim_order_model(self) -> None:
        order_id = uuid.uuid4()
        acc_id = uuid.uuid4()
        user_id = uuid.uuid4()
        order = SimOrder(
            id=order_id,
            user_id=user_id,
            account_id=acc_id,
            symbol="AAPL",
            side="buy",
            type="limit",
            qty=Decimal("100.0000"),
            limit_price=Decimal("180.5000"),
            tif="day",
            status="pending",
            idempotency_key="key-test-123",
            source="manual",
        )
        assert order.id == order_id
        assert order.symbol == "AAPL"
        assert order.qty == Decimal("100.0000")
        assert order.idempotency_key == "key-test-123"
        assert order.__tablename__ == "sim_orders"

    def test_sim_trade_model(self) -> None:
        trade_id = uuid.uuid4()
        trade = SimTrade(
            id=trade_id,
            user_id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            order_id=uuid.uuid4(),
            symbol="NVDA",
            side="buy",
            qty=Decimal("50.0000"),
            price=Decimal("120.0000"),
            fee=Decimal("1.5000"),
            realized_pnl=Decimal("0.0000"),
            executed_at=datetime.now(UTC),
        )
        assert trade.id == trade_id
        assert trade.symbol == "NVDA"
        assert trade.price == Decimal("120.0000")
        assert trade.__tablename__ == "sim_trades"

    def test_sim_position_model(self) -> None:
        pos_id = uuid.uuid4()
        pos = SimPosition(
            id=pos_id,
            user_id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            symbol="MSFT",
            qty=Decimal("20.0000"),
            avg_cost=Decimal("400.0000"),
            realized_pnl=Decimal("350.0000"),
        )
        assert pos.id == pos_id
        assert pos.symbol == "MSFT"
        assert pos.avg_cost == Decimal("400.0000")
        assert pos.__tablename__ == "sim_positions"

    def test_equity_snapshot_model(self) -> None:
        acc_id = uuid.uuid4()
        t_date = date(2026, 11, 13)
        snap = EquitySnapshot(
            account_id=acc_id,
            trade_date=t_date,
            cash=Decimal("40000.0000"),
            market_value=Decimal("65000.0000"),
            equity=Decimal("105000.0000"),
            drawdown=Decimal("0.025000"),
        )
        assert snap.account_id == acc_id
        assert snap.trade_date == t_date
        assert snap.equity == Decimal("105000.0000")
        assert snap.__tablename__ == "equity_snapshots"

    def test_trade_journal_model(self) -> None:
        j_id = uuid.uuid4()
        trade_id = uuid.uuid4()
        journal = TradeJournal(
            id=j_id,
            trade_id=trade_id,
            notes="Followed trend breakout on daily chart.",
            tags=["trend_following", "breakout"],
            emotion="calm",
        )
        assert journal.id == j_id
        assert journal.trade_id == trade_id
        assert journal.tags == ["trend_following", "breakout"]
        assert journal.__tablename__ == "trade_journal"


class TestSimbrokerSchemas:
    """Pydantic DTO Schema 序列化与校验测试"""

    def test_fee_model_config(self) -> None:
        default_fee = FeeModelConfig()
        assert default_fee.type == "zero"
        assert default_fee.per_share == Decimal("0")

        custom_fee = FeeModelConfig(
            type="per_share",
            per_share=Decimal("0.005"),
            min_fee=Decimal("1.00"),
            max_fee=Decimal("10.00"),
        )
        assert custom_fee.type == "per_share"
        assert custom_fee.min_fee == Decimal("1.00")

    def test_account_create_and_response(self) -> None:
        req = AccountCreate(name="My Paper Account", initial_cash=Decimal("200000.00"))
        assert req.name == "My Paper Account"
        assert req.initial_cash == Decimal("200000.00")

        with pytest.raises(ValidationError):
            AccountCreate(name="", initial_cash=Decimal("1000"))

        with pytest.raises(ValidationError):
            AccountCreate(name="Bad", initial_cash=Decimal("-100"))

        acc_resp = AccountResponse(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            name="Alpha",
            initial_cash=Decimal("100000.00"),
            cash=Decimal("100000.00"),
            fee_model=FeeModelConfig(),
            slippage_bps=Decimal("5.0"),
            pdt_enabled=True,
            status="active",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        assert acc_resp.status == "active"

    def test_account_overview(self) -> None:
        overview = AccountOverview(
            id=uuid.uuid4(),
            name="Demo",
            status="active",
            initial_cash=Decimal("100000.00"),
            cash=Decimal("60000.00"),
            market_value=Decimal("45000.00"),
            equity=Decimal("105000.00"),
            daily_pnl=Decimal("1200.00"),
            daily_pnl_pct=Decimal("0.0115"),
            total_pnl=Decimal("5000.00"),
            total_pnl_pct=Decimal("0.0500"),
            pdt_day_trades_count=1,
            pdt_warning=False,
        )
        assert overview.equity == Decimal("105000.00")
        assert overview.pdt_day_trades_count == 1

    def test_deposit_request(self) -> None:
        dep = DepositRequest(amount=Decimal("10000.00"))
        assert dep.amount == Decimal("10000.00")

        with pytest.raises(ValidationError):
            DepositRequest(amount=Decimal("-500"))

    def test_order_create_validation(self) -> None:
        order = OrderCreate(
            symbol="AAPL",
            side="buy",
            type="limit",
            qty=Decimal("10"),
            limit_price=Decimal("175.50"),
            tif="day",
        )
        assert order.symbol == "AAPL"
        assert order.side == "buy"

        with pytest.raises(ValidationError):
            OrderCreate(symbol="", side="buy", type="market", qty=Decimal("10"))

        with pytest.raises(ValidationError):
            OrderCreate(symbol="AAPL", side="buy", type="market", qty=Decimal("0"))

    def test_order_response(self) -> None:
        now = datetime.now(UTC)
        resp = OrderResponse(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            symbol="GOOGL",
            side="buy",
            type="market",
            qty=Decimal("15"),
            tif="day",
            status="accepted",
            idempotency_key="idemp-1",
            source="manual",
            created_at=now,
            updated_at=now,
        )
        assert resp.symbol == "GOOGL"
        assert resp.status == "accepted"

    def test_position_and_trade_response(self) -> None:
        pos = PositionResponse(
            id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            symbol="TSLA",
            qty=Decimal("50"),
            avg_cost=Decimal("200.00"),
            current_price=Decimal("220.00"),
            market_value=Decimal("11000.00"),
            unrealized_pnl=Decimal("1000.00"),
            unrealized_pnl_pct=Decimal("0.10"),
            realized_pnl=Decimal("0.00"),
            weight_pct=Decimal("0.11"),
        )
        assert pos.market_value == Decimal("11000.00")

        trade = TradeResponse(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            order_id=uuid.uuid4(),
            symbol="TSLA",
            side="buy",
            qty=Decimal("50"),
            price=Decimal("200.00"),
            fee=Decimal("1.00"),
            realized_pnl=Decimal("0.00"),
            executed_at=datetime.now(UTC),
        )
        assert trade.price == Decimal("200.00")

    def test_equity_snapshot_and_journal_schemas(self) -> None:
        snap = EquitySnapshotResponse(
            account_id=uuid.uuid4(),
            trade_date=date(2026, 11, 13),
            cash=Decimal("50000.00"),
            market_value=Decimal("55000.00"),
            equity=Decimal("105000.00"),
            drawdown=Decimal("0.0125"),
        )
        assert snap.drawdown == Decimal("0.0125")

        update = TradeJournalUpdate(notes="Exited per plan", tags=["plan", "exit"], emotion="calm")
        assert update.tags == ["plan", "exit"]

        now = datetime.now(UTC)
        j_resp = TradeJournalResponse(
            id=uuid.uuid4(),
            trade_id=uuid.uuid4(),
            notes="Note",
            tags=["a"],
            emotion="neutral",
            created_at=now,
            updated_at=now,
        )
        assert j_resp.notes == "Note"

    def test_performance_metrics_and_risk(self) -> None:
        acc_id = uuid.uuid4()
        metrics = PerformanceMetrics(
            account_id=acc_id,
            initial_cash=Decimal("100000.00"),
            current_equity=Decimal("115000.00"),
            total_return=Decimal("15000.00"),
            total_return_pct=Decimal("0.1500"),
            max_drawdown=Decimal("0.0450"),
            win_rate=Decimal("0.6667"),
            profit_loss_ratio=Decimal("2.3500"),
            total_trades=15,
            winning_trades=10,
            losing_trades=5,
            benchmark_return_pct=Decimal("0.0800"),
            alpha=Decimal("0.0700"),
            beta=Decimal("1.0500"),
        )
        assert metrics.total_return == Decimal("15000.00")
        assert metrics.win_rate == Decimal("0.6667")

        risk = RiskOverview(
            account_id=acc_id,
            cash_ratio=Decimal("0.4000"),
            single_stock_weights={"AAPL": Decimal("0.2500"), "MSFT": Decimal("0.3500")},
            top_positions=[("MSFT", Decimal("0.3500")), ("AAPL", Decimal("0.2500"))],
            sector_weights={"Technology": Decimal("0.6000")},
            pdt_day_trades_count=2,
            pdt_warning=False,
        )
        assert risk.cash_ratio == Decimal("0.4000")


class TestPortsContractCompliance:
    """Ports 协议实现兼容性测试"""

    def test_dummy_broker_implementation(self) -> None:
        class DummyBroker:
            name: str = "simbroker"

            def submit_order(
                self, account_id: str, req: OrderCreate, idempotency_key: str
            ) -> OrderResponse:
                now = datetime.now(UTC)
                return OrderResponse(
                    id=uuid.uuid4(),
                    user_id=uuid.uuid4(),
                    account_id=uuid.UUID(account_id),
                    symbol=req.symbol,
                    side=req.side,
                    type=req.type,
                    qty=req.qty,
                    tif=req.tif,
                    status="accepted",
                    idempotency_key=idempotency_key,
                    source="manual",
                    created_at=now,
                    updated_at=now,
                )

            def cancel_order(self, account_id: str, order_id: str) -> OrderResponse:
                now = datetime.now(UTC)
                return OrderResponse(
                    id=uuid.UUID(order_id),
                    user_id=uuid.uuid4(),
                    account_id=uuid.UUID(account_id),
                    symbol="AAPL",
                    side="buy",
                    type="limit",
                    qty=Decimal("10"),
                    tif="day",
                    status="cancelled",
                    idempotency_key="cancelled-key",
                    source="manual",
                    created_at=now,
                    updated_at=now,
                )

            def get_account(self, account_id: str) -> AccountOverview:
                return AccountOverview(
                    id=uuid.UUID(account_id),
                    name="Test",
                    status="active",
                    initial_cash=Decimal("100000.00"),
                    cash=Decimal("100000.00"),
                    market_value=Decimal("0.00"),
                    equity=Decimal("100000.00"),
                    daily_pnl=Decimal("0.00"),
                    daily_pnl_pct=Decimal("0.0000"),
                    total_pnl=Decimal("0.00"),
                    total_pnl_pct=Decimal("0.0000"),
                )

            def get_positions(self, account_id: str) -> list[PositionResponse]:
                return []

            def process_bar(self, account_id: str, bar_time: datetime) -> list[TradeResponse]:
                return []

        broker: Broker = DummyBroker()
        assert broker.name == "simbroker"

    def test_dummy_market_and_corporate_feeds(self) -> None:
        class DummyBar:
            trade_date = date(2026, 11, 13)
            open = Decimal("150.00")
            high = Decimal("155.00")
            low = Decimal("149.00")
            close = Decimal("154.00")
            volume = 1000000

        class DummyMarketFeed:
            def get_latest_price(self, symbol: str) -> Decimal | None:
                return Decimal("154.00")

            def get_daily_bar(self, symbol: str, trade_date: date) -> BarProtocol | None:
                return DummyBar()

            def get_sp500_return(self, start_date: date, end_date: date) -> Decimal | None:
                return Decimal("0.05")

            def get_symbol_sector(self, symbol: str) -> str | None:
                return "Technology"

        class DummyCorpFeed:
            def get_split_ratio(self, symbol: str, trade_date: date) -> Decimal | None:
                return Decimal("2.0")

            def get_dividend_per_share(self, symbol: str, trade_date: date) -> Decimal | None:
                return Decimal("0.50")

        mfeed: MarketDataFeedProtocol = DummyMarketFeed()
        assert mfeed.get_latest_price("AAPL") == Decimal("154.00")
        assert mfeed.get_symbol_sector("AAPL") == "Technology"

        cfeed: CorporateActionFeedProtocol = DummyCorpFeed()
        assert cfeed.get_split_ratio("AAPL", date(2026, 11, 13)) == Decimal("2.0")
        assert cfeed.get_dividend_per_share("AAPL", date(2026, 11, 13)) == Decimal("0.50")


class TestAlembicMigrationMetadata:
    """验证 0004_simbroker 迁移文件元数据与可逆方法定义"""

    def test_migration_metadata(self) -> None:
        m04 = _load_migration_module()
        assert m04.revision == "0004_simbroker"
        assert m04.down_revision == "0003_identity"
        assert callable(m04.upgrade)
        assert callable(m04.downgrade)
        assert "sim_accounts" in m04._TABLES
        assert "sim_orders" in m04._TABLES
        assert "sim_trades" in m04._TABLES
        assert "sim_positions" in m04._TABLES
        assert "equity_snapshots" in m04._TABLES
        assert "trade_journal" in m04._TABLES
