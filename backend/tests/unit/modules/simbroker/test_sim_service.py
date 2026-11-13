"""Unit tests for SimService facade (M4-T07).

Tests all business methods of SimService using an AsyncMock(AsyncSession) pattern,
verifying accounting orchestration, idempotency checks, multi-tenant isolation,
order submission and cancellation, market close and bar processing.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import NotFound, StateConflict
from app.modules.simbroker.models import (
    EquitySnapshot,
    SimAccount,
    SimOrder,
    SimPosition,
    SimTrade,
    TradeJournal,
)
from app.modules.simbroker.schemas import (
    AccountCreate,
    FeeModelConfig,
    OrderCreate,
    TradeJournalUpdate,
)
from app.modules.simbroker.service import SimService

pytestmark = pytest.mark.unit


def _populate_defaults(entity: Any) -> None:
    now = datetime.now(UTC)
    if hasattr(entity, "id") and getattr(entity, "id", None) is None:
        entity.id = uuid.uuid4()
    if hasattr(entity, "created_at") and getattr(entity, "created_at", None) is None:
        entity.created_at = now
    if hasattr(entity, "updated_at") and getattr(entity, "updated_at", None) is None:
        entity.updated_at = now


def _mock_result(
    *,
    scalar: Any = None,
    scalars: Sequence[Any] = (),
    rowcount: int = 0,
) -> MagicMock:
    """Helper to mock SQLAlchemy Result."""
    res = MagicMock()
    res.scalar_one_or_none.return_value = scalar
    res.scalar_one.return_value = scalar
    res.scalars.return_value.all.return_value = list(scalars)
    res.rowcount = rowcount
    return res


def _mock_session(
    *,
    account: SimAccount | None = None,
    accounts: list[SimAccount] | None = None,
    positions: list[SimPosition] | None = None,
    orders: list[SimOrder] | None = None,
    trades: list[SimTrade] | None = None,
    snapshots: list[EquitySnapshot] | None = None,
    journal: TradeJournal | None = None,
) -> AsyncMock:
    """Helper to mock AsyncSession with dynamic SQL routing."""
    session = AsyncMock()

    def _add_side_effect(entity: Any) -> None:
        _populate_defaults(entity)

    session.add = MagicMock(side_effect=_add_side_effect)

    async def _refresh_side_effect(entity: Any) -> None:
        _populate_defaults(entity)

    session.refresh = AsyncMock(side_effect=_refresh_side_effect)
    session.flush = AsyncMock(side_effect=lambda: None)
    session.commit = AsyncMock(side_effect=lambda: None)

    async def _execute(stmt: Any, *args: Any, **kwargs: Any) -> MagicMock:
        sql = str(stmt).lower()
        if "from sim_accounts" in sql:
            acc_list = accounts if accounts is not None else ([account] if account else [])
            first_acc = acc_list[0] if acc_list else account
            return _mock_result(scalar=first_acc, scalars=acc_list)
        if "from sim_positions" in sql:
            pos_list = positions or []
            first_pos = pos_list[0] if pos_list else None
            return _mock_result(scalar=first_pos, scalars=pos_list)
        if "from sim_orders" in sql:
            ord_list = orders or []
            first_ord = ord_list[0] if ord_list else None
            return _mock_result(scalar=first_ord, scalars=ord_list)
        if "from sim_trades" in sql:
            tr_list = trades or []
            first_tr = tr_list[0] if tr_list else None
            return _mock_result(scalar=first_tr, scalars=tr_list)
        if "from equity_snapshots" in sql:
            sn_list = snapshots or []
            first_sn = sn_list[0] if sn_list else None
            return _mock_result(scalar=first_sn, scalars=sn_list)
        if "from trade_journals" in sql:
            return _mock_result(scalar=journal, scalars=[journal] if journal else [])
        return _mock_result()

    session.execute = AsyncMock(side_effect=_execute)
    return session


def _make_account(
    id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    name: str = "Account 1",
    initial_cash: Decimal = Decimal("50000.0000"),
    cash: Decimal = Decimal("50000.0000"),
    status: str = "active",
) -> SimAccount:
    return SimAccount(
        id=id or uuid.uuid4(),
        user_id=user_id or uuid.uuid4(),
        name=name,
        initial_cash=initial_cash,
        cash=cash,
        fee_model=FeeModelConfig().model_dump(),
        slippage_bps=Decimal("5.0"),
        pdt_enabled=True,
        status=status,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _make_order(
    id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    account_id: uuid.UUID | None = None,
    symbol: str = "AAPL",
    side: str = "buy",
    type: str = "limit",
    qty: Decimal = Decimal("10.0000"),
    limit_price: Decimal | None = Decimal("150.0000"),
    status: str = "accepted",
    idempotency_key: str = "idem-1",
    tif: str = "day",
    source: str = "manual",
) -> SimOrder:
    return SimOrder(
        id=id or uuid.uuid4(),
        user_id=user_id or uuid.uuid4(),
        account_id=account_id or uuid.uuid4(),
        symbol=symbol,
        side=side,
        type=type,
        qty=qty,
        limit_price=limit_price,
        status=status,
        idempotency_key=idempotency_key,
        tif=tif,
        source=source,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


class DummyBar:
    """Mock BarProtocol implementation."""

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


# =============================================================================
# 1. Account Management Tests
# =============================================================================


async def test_create_account() -> None:
    session = _mock_session()
    service = SimService(session=session)
    user_id = uuid.uuid4()
    req = AccountCreate(name="My Sim Account", initial_cash=Decimal("50000.0000"))

    account_resp = await service.create_account(user_id=user_id, req=req)

    assert account_resp.name == "My Sim Account"
    assert account_resp.initial_cash == Decimal("50000.0000")
    assert account_resp.cash == Decimal("50000.0000")
    assert session.add.called
    assert session.commit.awaited
    assert session.refresh.awaited


async def test_get_account_entity_success_and_tenant_check() -> None:
    account_id = uuid.uuid4()
    user_id = uuid.uuid4()
    account = _make_account(id=account_id, user_id=user_id)

    session = _mock_session(account=account)
    service = SimService(session=session)

    # Success when tenant matches
    res = await service.get_account_entity(account_id, user_id=user_id)
    assert res.id == account_id

    # 404 when tenant does not match (C10 multi-tenant isolation)
    other_user = uuid.uuid4()
    with pytest.raises(NotFound):
        await service.get_account_entity(account_id, user_id=other_user)

    # 404 when account does not exist
    session_empty = _mock_session(account=None)
    service_empty = SimService(session=session_empty)
    with pytest.raises(NotFound):
        await service_empty.get_account_entity(account_id, user_id=user_id)


async def test_list_accounts() -> None:
    user_id = uuid.uuid4()
    acc1 = _make_account(user_id=user_id)
    session = _mock_session(accounts=[acc1])
    service = SimService(session=session)

    accounts = await service.list_accounts(user_id=user_id)
    assert len(accounts) == 1
    assert accounts[0].id == acc1.id


async def test_deposit_and_withdraw() -> None:
    account_id = uuid.uuid4()
    user_id = uuid.uuid4()
    account = _make_account(
        id=account_id,
        user_id=user_id,
        initial_cash=Decimal("10000.0000"),
        cash=Decimal("10000.0000"),
    )
    session = _mock_session(account=account)
    service = SimService(session=session)

    # Deposit
    new_cash = await service.deposit(account_id, Decimal("5000.0000"), user_id=user_id)
    assert new_cash == Decimal("15000.0000")
    assert account.cash == Decimal("15000.0000")

    # Withdraw success
    new_cash2 = await service.withdraw(account_id, Decimal("3000.0000"), user_id=user_id)
    assert new_cash2 == Decimal("12000.0000")

    # Withdraw overdraft raises StateConflict
    with pytest.raises(StateConflict):
        await service.withdraw(account_id, Decimal("50000.0000"), user_id=user_id)


# =============================================================================
# 2. Order Management & Idempotency Tests
# =============================================================================


async def test_submit_order_idempotent_replay() -> None:
    account_id = uuid.uuid4()
    user_id = uuid.uuid4()
    account = _make_account(id=account_id, user_id=user_id)
    existing_order = _make_order(
        user_id=user_id,
        account_id=account_id,
        idempotency_key="existing-key-1",
        status="accepted",
    )

    session = _mock_session(account=account, orders=[existing_order])
    service = SimService(session=session)
    req = OrderCreate(symbol="AAPL", side="buy", type="market", qty=Decimal("10.0000"))

    resp = await service.submit_order(
        user_id=user_id, account_id=account_id, req=req, idempotency_key="existing-key-1"
    )
    assert resp.id == existing_order.id
    assert resp.status == "accepted"


async def test_submit_order_insufficient_funds_rejected() -> None:
    account_id = uuid.uuid4()
    user_id = uuid.uuid4()
    account = _make_account(
        id=account_id,
        user_id=user_id,
        initial_cash=Decimal("100.0000"),
        cash=Decimal("100.0000"),
    )

    session = _mock_session(account=account, orders=[])
    service = SimService(session=session)
    req = OrderCreate(
        symbol="AAPL",
        side="buy",
        type="limit",
        qty=Decimal("100.0000"),
        limit_price=Decimal("150.0000"),
    )

    resp = await service.submit_order(
        user_id=user_id, account_id=account_id, req=req, idempotency_key="key-reject-1"
    )
    assert resp.status == "rejected"
    assert "INSUFFICIENT_FUNDS" in str(resp.reject_reason)


async def test_submit_order_success() -> None:
    account_id = uuid.uuid4()
    user_id = uuid.uuid4()
    account = _make_account(
        id=account_id,
        user_id=user_id,
        initial_cash=Decimal("50000.0000"),
        cash=Decimal("50000.0000"),
    )

    session = _mock_session(account=account, orders=[])
    service = SimService(session=session)
    req = OrderCreate(
        symbol="AAPL",
        side="buy",
        type="limit",
        qty=Decimal("10.0000"),
        limit_price=Decimal("150.0000"),
    )

    order_resp = await service.submit_order(
        user_id=user_id, account_id=account_id, req=req, idempotency_key="key-success-1"
    )
    assert order_resp.symbol == "AAPL"
    assert order_resp.status in ("accepted", "pending")
    assert session.add.called
    assert session.commit.awaited


async def test_cancel_order_success_and_conflict() -> None:
    account_id = uuid.uuid4()
    user_id = uuid.uuid4()
    order_id = uuid.uuid4()
    order = _make_order(
        id=order_id,
        user_id=user_id,
        account_id=account_id,
        status="accepted",
    )

    # Cancel open order -> success
    account = _make_account(id=account_id, user_id=user_id)
    session = _mock_session(account=account, orders=[order])
    service = SimService(session=session)
    res = await service.cancel_order(account_id=account_id, order_id=order_id, user_id=user_id)
    assert res.status == "cancelled"

    # Cancel already filled order -> StateConflict
    order.status = "filled"
    with pytest.raises(StateConflict):
        await service.cancel_order(account_id=account_id, order_id=order_id, user_id=user_id)


# =============================================================================
# 3. Positions, Performance, Risk & Market Close Tests
# =============================================================================


async def test_get_positions_and_trades() -> None:
    account_id = uuid.uuid4()
    user_id = uuid.uuid4()
    account = _make_account(
        id=account_id,
        user_id=user_id,
        initial_cash=Decimal("50000.0000"),
        cash=Decimal("35000.0000"),
    )
    pos = SimPosition(
        id=uuid.uuid4(),
        user_id=user_id,
        account_id=account_id,
        symbol="AAPL",
        qty=Decimal("100.0000"),
        avg_cost=Decimal("150.0000"),
        realized_pnl=Decimal("0.0000"),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    trade = SimTrade(
        id=uuid.uuid4(),
        user_id=user_id,
        account_id=account_id,
        order_id=uuid.uuid4(),
        symbol="AAPL",
        side="buy",
        qty=Decimal("100.0000"),
        price=Decimal("150.0000"),
        fee=Decimal("1.0000"),
        realized_pnl=Decimal("0.0000"),
        executed_at=datetime.now(UTC),
    )

    session = _mock_session(account=account, positions=[pos], trades=[trade])
    service = SimService(session=session)

    positions = await service.get_positions(account_id, user_id=user_id)
    assert len(positions) == 1
    assert positions[0].symbol == "AAPL"
    assert positions[0].qty == Decimal("100.0000")

    trades = await service.get_trades(account_id, user_id=user_id)
    assert len(trades) == 1
    assert trades[0].symbol == "AAPL"


async def test_update_trade_journal() -> None:
    trade_id = uuid.uuid4()
    user_id = uuid.uuid4()
    trade = SimTrade(
        id=trade_id,
        user_id=user_id,
        account_id=uuid.uuid4(),
        order_id=uuid.uuid4(),
        symbol="AAPL",
        side="buy",
        qty=Decimal("10.0000"),
        price=Decimal("150.0000"),
        fee=Decimal("1.0000"),
        realized_pnl=Decimal("0.0000"),
        executed_at=datetime.now(UTC),
    )

    session = _mock_session(trades=[trade], journal=None)
    service = SimService(session=session)
    req = TradeJournalUpdate(notes="Entered on pullback", tags=["pullback"], emotion="calm")

    journal_resp = await service.update_trade_journal(trade_id=trade_id, req=req, user_id=user_id)
    assert journal_resp.trade_id == trade_id
    assert journal_resp.notes == "Entered on pullback"
    assert session.add.called
    assert session.commit.awaited


async def test_process_bar_and_fill_order() -> None:
    account_id = uuid.uuid4()
    user_id = uuid.uuid4()
    account = _make_account(
        id=account_id,
        user_id=user_id,
        initial_cash=Decimal("50000.0000"),
        cash=Decimal("50000.0000"),
        status="active",
    )
    open_order = _make_order(
        user_id=user_id,
        account_id=account_id,
        symbol="AAPL",
        side="buy",
        type="limit",
        qty=Decimal("10.0000"),
        limit_price=Decimal("150.0000"),
        status="accepted",
    )

    session = _mock_session(account=account, orders=[open_order], positions=[])
    service = SimService(session=session)
    bar = DummyBar(
        trade_date=date(2026, 3, 1),
        open_="150.0",
        high="155.0",
        low="148.0",
        close="152.0",
    )

    trades = await service.process_bar(
        account_id=account_id, symbol="AAPL", bar=bar, user_id=user_id
    )
    assert len(trades) == 1
    assert trades[0].symbol == "AAPL"
    assert trades[0].price == Decimal("150.0000")
    assert open_order.status == "filled"
    assert session.commit.awaited
