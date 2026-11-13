"""M4-T05 公司行动（拆股/分红）、收盘批处理与净值快照单元测试。

涵盖：
1. 股票正向拆股与反向合股（无损市值保值不变量、成本反向调整）
2. 现金分红派发与账户现金累加
3. 公司行动自动化批量处理（先拆股后分红的时序性）
4. 收盘未成交 DAY 订单过期清理与 GTC 订单豁免
5. 最大回撤率（Drawdown）与峰值净值动态追踪
6. 收盘批处理全流程及 EquitySnapshot ORM 实体沉淀
7. 行情缺失防御（自动降级为 avg_cost 估值防御）
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.modules.simbroker.corporate_actions import (
    CorporateActionsEngine,
    DividendResult,
    InvalidActionError,
    SplitResult,
    apply_cash_dividend,
    apply_stock_split,
)
from app.modules.simbroker.market_close import (
    MarketCloseBatch,
    MarketCloseResult,
    calculate_drawdown,
    expire_day_orders,
    process_market_close,
)
from app.modules.simbroker.models import EquitySnapshot, SimAccount, SimPosition

# -----------------------------------------------------------------------------
# 测试辅助对象
# -----------------------------------------------------------------------------


@dataclass
class MockPosition:
    symbol: str
    qty: Decimal
    avg_cost: Decimal
    realized_pnl: Decimal = Decimal("0.0000")


@dataclass
class MockAccount:
    id: uuid.UUID
    cash: Decimal


@dataclass
class MockOrder:
    id: uuid.UUID
    symbol: str
    side: str
    type: str
    qty: Decimal
    tif: str
    status: str


class MockCorporateActionFeed:
    def __init__(
        self,
        splits: dict[str, Decimal] | None = None,
        dividends: dict[str, Decimal] | None = None,
    ) -> None:
        self.splits = splits or {}
        self.dividends = dividends or {}

    def get_split_ratio(self, symbol: str, trade_date: date) -> Decimal | None:
        return self.splits.get(symbol)

    def get_dividend_per_share(self, symbol: str, trade_date: date) -> Decimal | None:
        return self.dividends.get(symbol)


class MockMarketDataFeed:
    def __init__(self, prices: dict[str, Decimal] | None = None) -> None:
        self.prices = prices or {}

    def get_latest_price(self, symbol: str) -> Decimal | None:
        return self.prices.get(symbol)

    def get_daily_bar(self, symbol: str, trade_date: date) -> Any | None:
        return None

    def get_sp500_return(self, start_date: date, end_date: date) -> Decimal | None:
        return None

    def get_symbol_sector(self, symbol: str) -> str | None:
        return None


# -----------------------------------------------------------------------------
# 1. 拆股与合股无损市值校验
# -----------------------------------------------------------------------------


def test_forward_stock_split_preserves_cost_basis() -> None:
    """正向拆股 2:1：股数翻倍，单股成本减半，总成本基础严格恒等。"""
    pos = MockPosition(symbol="NVDA", qty=Decimal("10.0000"), avg_cost=Decimal("120.0000"))

    res: SplitResult = apply_stock_split(pos, split_ratio=Decimal("2.0"))

    assert res.is_reverse_split is False
    assert pos.qty == Decimal("20.0000")
    assert pos.avg_cost == Decimal("60.0000")
    assert res.cost_basis_before == Decimal("1200.0000")
    assert res.cost_basis_after == Decimal("1200.0000")
    assert res.cost_basis_before == res.cost_basis_after


def test_reverse_stock_split_preserves_cost_basis() -> None:
    """反向合股 1:4 (ratio=0.25)：股数减为 1/4，单股成本提升 4 倍，总成本基础守恒。"""
    pos = MockPosition(symbol="SOFI", qty=Decimal("40.0000"), avg_cost=Decimal("25.0000"))

    res: SplitResult = apply_stock_split(pos, split_ratio=Decimal("0.25"))

    assert res.is_reverse_split is True
    assert pos.qty == Decimal("10.0000")
    assert pos.avg_cost == Decimal("100.0000")
    assert res.cost_basis_before == Decimal("1000.0000")
    assert res.cost_basis_after == Decimal("1000.0000")


def test_odd_stock_split_3_for_1() -> None:
    """奇数拆股 3:1：保留 4 位精度下市值恒定。"""
    pos = MockPosition(symbol="AAPL", qty=Decimal("10.0000"), avg_cost=Decimal("100.0000"))

    res = apply_stock_split(pos, split_ratio=Decimal("3.0"))

    assert pos.qty == Decimal("30.0000")
    assert pos.avg_cost == Decimal("33.3333")
    assert abs(res.cost_basis_before - res.cost_basis_after) <= Decimal("0.01")


def test_invalid_split_ratio_raises() -> None:
    """非正数拆股比率抛出 InvalidActionError。"""
    pos = MockPosition(symbol="AAPL", qty=Decimal("10"), avg_cost=Decimal("100"))

    with pytest.raises(InvalidActionError, match="Split ratio must be positive"):
        apply_stock_split(pos, Decimal("0.0"))

    with pytest.raises(InvalidActionError, match="Split ratio must be positive"):
        apply_stock_split(pos, Decimal("-2.0"))


# -----------------------------------------------------------------------------
# 2. 现金分红派发
# -----------------------------------------------------------------------------


def test_cash_dividend_credit_to_account() -> None:
    """现金分红：按持仓股数增加账户可用现金。"""
    account = MockAccount(id=uuid.uuid4(), cash=Decimal("5000.0000"))
    pos = MockPosition(symbol="KO", qty=Decimal("100.0000"), avg_cost=Decimal("60.0000"))

    res: DividendResult = apply_cash_dividend(
        account=account,
        position=pos,
        dividend_per_share=Decimal("0.4850"),
    )

    # 100 * 0.4850 = 48.5000
    assert res.total_dividend == Decimal("48.5000")
    assert account.cash == Decimal("5048.5000")
    assert res.cash_before == Decimal("5000.0000")
    assert res.cash_after == Decimal("5048.5000")


def test_cash_dividend_zero_position() -> None:
    """持仓数量为 0 时，不发放分红且现金不变。"""
    account = MockAccount(id=uuid.uuid4(), cash=Decimal("5000.0000"))
    pos = MockPosition(symbol="KO", qty=Decimal("0.0000"), avg_cost=Decimal("0.0000"))

    res = apply_cash_dividend(account, pos, Decimal("0.5000"))

    assert res.total_dividend == Decimal("0.0000")
    assert account.cash == Decimal("5000.0000")


def test_invalid_dividend_per_share_raises() -> None:
    """非正数每股分红抛出 InvalidActionError。"""
    account = MockAccount(id=uuid.uuid4(), cash=Decimal("1000"))
    pos = MockPosition(symbol="KO", qty=Decimal("10"), avg_cost=Decimal("50"))

    with pytest.raises(InvalidActionError, match="Dividend per share must be positive"):
        apply_cash_dividend(account, pos, Decimal("0.0000"))

    with pytest.raises(InvalidActionError, match="Dividend per share must be positive"):
        apply_cash_dividend(account, pos, Decimal("-0.1000"))


# -----------------------------------------------------------------------------
# 3. 批量公司行动执行引擎
# -----------------------------------------------------------------------------


def test_corporate_actions_engine_split_then_dividend() -> None:
    """批量执行：先拆股后分红，分红按拆股后数量计算。"""
    account = MockAccount(id=uuid.uuid4(), cash=Decimal("10000.0000"))
    pos = MockPosition(symbol="AAPL", qty=Decimal("10.0000"), avg_cost=Decimal("150.0000"))

    # 拆股 2:1，且每股分红 $0.50
    feed = MockCorporateActionFeed(
        splits={"AAPL": Decimal("2.0")},
        dividends={"AAPL": Decimal("0.5000")},
    )

    engine = CorporateActionsEngine()
    summary = engine.process_actions_for_account(
        account=account,
        positions=[pos],
        trade_date=date(2026, 11, 13),
        feed=feed,
    )

    # 拆股后持仓为 20 股
    assert pos.qty == Decimal("20.0000")
    assert pos.avg_cost == Decimal("75.0000")
    assert len(summary.splits) == 1

    # 分红基于 20 股: 20 * 0.50 = 10.0000
    assert len(summary.dividends) == 1
    assert summary.total_dividend_cash == Decimal("10.0000")
    assert account.cash == Decimal("10010.0000")


def test_corporate_actions_engine_no_actions() -> None:
    """无公司行动时，持仓与现金均保持不变。"""
    account = MockAccount(id=uuid.uuid4(), cash=Decimal("10000.0000"))
    pos = MockPosition(symbol="MSFT", qty=Decimal("15.0000"), avg_cost=Decimal("300.0000"))

    feed = MockCorporateActionFeed(splits={"MSFT": Decimal("1.0")}, dividends={})
    engine = CorporateActionsEngine()
    summary = engine.process_actions_for_account(
        account=account,
        positions=[pos],
        trade_date=date(2026, 11, 13),
        feed=feed,
    )

    assert len(summary.splits) == 0
    assert len(summary.dividends) == 0
    assert summary.total_dividend_cash == Decimal("0.0000")
    assert pos.qty == Decimal("15.0000")
    assert account.cash == Decimal("10000.0000")


# -----------------------------------------------------------------------------
# 4. DAY 订单收盘过期清理
# -----------------------------------------------------------------------------


def test_expire_day_orders_and_preserve_gtc() -> None:
    """收盘时 DAY 挂单被置为 expired，GTC 挂单与已成交订单保持原状。"""
    o1 = MockOrder(uuid.uuid4(), "AAPL", "buy", "limit", Decimal("10"), "day", "accepted")
    o2 = MockOrder(uuid.uuid4(), "MSFT", "sell", "limit", Decimal("5"), "day", "pending")
    o3 = MockOrder(uuid.uuid4(), "TSLA", "buy", "limit", Decimal("8"), "gtc", "accepted")
    o4 = MockOrder(uuid.uuid4(), "GOOGL", "buy", "market", Decimal("2"), "day", "filled")

    expired_ids = expire_day_orders([o1, o2, o3, o4])

    assert len(expired_ids) == 2
    assert o1.id in expired_ids
    assert o2.id in expired_ids
    assert o1.status == "expired"
    assert o2.status == "expired"

    # GTC 订单不受收盘影响
    assert o3.status == "accepted"
    # 已终态订单不受影响
    assert o4.status == "filled"


# -----------------------------------------------------------------------------
# 5. 回撤计算逻辑
# -----------------------------------------------------------------------------


def test_calculate_drawdown_scenarios() -> None:
    """测试净值创新高、正常回撤以及深度回撤计算。"""
    # 场景 1: 创新高，无回撤
    new_peak, dd1 = calculate_drawdown(
        current_equity=Decimal("120000.0000"),
        historical_peak_equity=Decimal("100000.0000"),
    )
    assert new_peak == Decimal("120000.0000")
    assert dd1 == Decimal("0.000000")

    # 场景 2: 从 120,000 回撤到 108,000 (回撤 10%)
    new_peak, dd2 = calculate_drawdown(
        current_equity=Decimal("108000.0000"),
        historical_peak_equity=new_peak,
    )
    assert new_peak == Decimal("120000.0000")
    assert dd2 == Decimal("0.100000")

    # 场景 3: 深度回撤到 60,000 (回撤 50%)
    new_peak, dd3 = calculate_drawdown(
        current_equity=Decimal("60000.0000"),
        historical_peak_equity=new_peak,
    )
    assert dd3 == Decimal("0.500000")

    # 场景 4: 零净值
    _, dd4 = calculate_drawdown(current_equity=Decimal("0.0000"))
    assert dd4 == Decimal("0.000000")


# -----------------------------------------------------------------------------
# 6. 收盘批处理全流程与快照落地
# -----------------------------------------------------------------------------


def test_process_market_close_full_flow() -> None:
    """全套收盘批处理：持仓收盘估值、净值生成、回撤计算与快照构建。"""
    account_id = uuid.uuid4()
    account = MockAccount(id=account_id, cash=Decimal("20000.0000"))

    pos1 = MockPosition(symbol="AAPL", qty=Decimal("10.0000"), avg_cost=Decimal("150.0000"))
    pos2 = MockPosition(symbol="NVDA", qty=Decimal("20.0000"), avg_cost=Decimal("100.0000"))
    positions = [pos1, pos2]

    # DAY 订单 1 笔，GTC 订单 1 笔
    ord1 = MockOrder(uuid.uuid4(), "AAPL", "buy", "limit", Decimal("5"), "day", "accepted")
    ord2 = MockOrder(uuid.uuid4(), "NVDA", "sell", "limit", Decimal("5"), "gtc", "accepted")

    prices = {
        "AAPL": Decimal("160.0000"),  # 市值: 10 * 160 = 1600
        "NVDA": Decimal("110.0000"),  # 市值: 20 * 110 = 2200
    }
    # 总市值: 3800.0000; 总净值: 20000 + 3800 = 23800.0000

    fixed_time = datetime(2026, 11, 13, 21, 0, 0, tzinfo=UTC)
    result: MarketCloseResult = process_market_close(
        account=account,
        positions=positions,
        open_orders=[ord1, ord2],
        trade_date=date(2026, 11, 13),
        current_prices=prices,
        historical_peak_equity=Decimal("25000.0000"),  # 历史最高 25,000
        now_func=fixed_time,
    )

    assert result.account_id == account_id
    assert result.trade_date == date(2026, 11, 13)
    assert result.cash == Decimal("20000.0000")
    assert result.market_value == Decimal("3800.0000")
    assert result.equity == Decimal("23800.0000")
    assert result.peak_equity == Decimal("25000.0000")
    # 回撤: (25000 - 23800) / 25000 = 1200 / 25000 = 0.048000 (4.8%)
    assert result.drawdown == Decimal("0.048000")

    # 检查订单过期
    assert result.expired_orders_count == 1
    assert ord1.status == "expired"
    assert ord2.status == "accepted"

    # 检查快照 ORM 实体
    snapshot = result.snapshot
    assert isinstance(snapshot, EquitySnapshot)
    assert snapshot.account_id == account_id
    assert snapshot.trade_date == date(2026, 11, 13)
    assert snapshot.cash == Decimal("20000.0000")
    assert snapshot.market_value == Decimal("3800.0000")
    assert snapshot.equity == Decimal("23800.0000")
    assert snapshot.drawdown == Decimal("0.048000")
    assert snapshot.created_at == fixed_time


def test_process_market_close_missing_price_fallback() -> None:
    """当某标的行情缺失时，批处理自动防御降级使用 avg_cost，不抛出异常。"""
    account_id = uuid.uuid4()
    account = MockAccount(id=account_id, cash=Decimal("10000.0000"))
    pos = MockPosition(symbol="UNLISTED", qty=Decimal("10.0000"), avg_cost=Decimal("50.0000"))

    # 提供空行情 feed
    empty_feed = MockMarketDataFeed(prices={})

    result = MarketCloseBatch.execute(
        account=account,
        positions=[pos],
        open_orders=[],
        trade_date=date(2026, 11, 13),
        market_feed=empty_feed,
    )

    # 降级使用 50.0000 计算: 10 * 50 = 500
    assert result.market_value == Decimal("500.0000")
    assert result.equity == Decimal("10500.0000")


def test_process_market_close_invalid_account_raises() -> None:
    """账户缺失 id 时抛出 ValueError。"""

    class BadAccount:
        cash = Decimal("1000")

    with pytest.raises(ValueError, match="Account must have a valid 'id'"):
        process_market_close(
            account=BadAccount(),
            positions=[],
            open_orders=[],
            trade_date=date(2026, 11, 13),
        )


# -----------------------------------------------------------------------------
# 7. SQLAlchemy ORM 实体集成测试
# -----------------------------------------------------------------------------


def test_corporate_actions_with_orm_models() -> None:
    """验证真实 SimAccount 与 SimPosition 实体可以直接用于拆股和分红。"""
    user_id = uuid.uuid4()
    account_id = uuid.uuid4()

    orm_account = SimAccount(
        id=account_id,
        user_id=user_id,
        name="Close Test Account",
        cash=Decimal("5000.0000"),
    )

    orm_position = SimPosition(
        user_id=user_id,
        account_id=account_id,
        symbol="AAPL",
        qty=Decimal("10.0000"),
        avg_cost=Decimal("100.0000"),
        realized_pnl=Decimal("0.0000"),
    )

    # 执行 2:1 拆股
    apply_stock_split(orm_position, Decimal("2.0"))
    assert orm_position.qty == Decimal("20.0000")
    assert orm_position.avg_cost == Decimal("50.0000")

    # 执行 $1.00 分红
    apply_cash_dividend(orm_account, orm_position, Decimal("1.0000"))
    assert orm_account.cash == Decimal("5020.0000")
