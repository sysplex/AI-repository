"""M4-T04 记账引擎、持仓管理、平均成本法与财务不变量单元及属性测试。

涵盖：
1. 加权平均成本法（买入计入手续费、多次加仓成本稀释、部分平仓、清仓与再次建仓）
2. 出入金与超限防御
3. 超卖防御与现金不足拦截（原子性保证）
4. 并发幂等性防护（同一 idempotency_key 严格有且仅有一次生效）
5. 基于 Hypothesis 与长随机序列的财务三大不变量检验：
   - 现金守恒不变量
   - 净值恒等不变量
   - 持仓非负不变量
6. 综合财务审计报告（audit_invariants）与违规侦测
7. SQLAlchemy ORM 实体（SimAccount, SimPosition, SimTrade）兼容性
"""

from __future__ import annotations

import concurrent.futures
import uuid
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.modules.simbroker.accounting import (
    AccountEquitySummary,
    AccountingEngine,
    AccountState,
    DuplicateTransactionError,
    InsufficientCashError,
    InsufficientPositionError,
    InvalidAmountError,
    PositionState,
    TradeExecutionRecord,
)
from app.modules.simbroker.models import SimAccount, SimPosition, SimTrade

# -----------------------------------------------------------------------------
# 1. 加权平均成本法与基础记账测试
# -----------------------------------------------------------------------------


def test_single_buy_weighted_average_cost() -> None:
    """单笔买入：手续费并入持仓成本，现金正确扣减。"""
    engine = AccountingEngine()
    account = AccountState(cash=Decimal("10000.0000"))
    pos = PositionState(symbol="AAPL")

    rec = engine.execute_buy(
        account=account,
        symbol="AAPL",
        qty=Decimal("10"),
        price=Decimal("150.0000"),
        fee=Decimal("2.0000"),
        position=pos,
    )

    # 现金扣减: 10 * 150 + 2 = 1502
    assert account.cash == Decimal("8498.0000")
    assert rec.cash_after == Decimal("8498.0000")
    # 持仓成本: 1502 / 10 = 150.2000
    assert pos.qty == Decimal("10.0000")
    assert pos.avg_cost == Decimal("150.2000")
    assert rec.avg_cost_after == Decimal("150.2000")
    assert rec.realized_pnl == Decimal("0.0000")


def test_multiple_buys_weighted_average_cost() -> None:
    """多次连续买入：加权平均稀释成本。"""
    engine = AccountingEngine()
    account = AccountState(cash=Decimal("50000.0000"))
    pos = PositionState(symbol="TSLA")

    # 第一次买入: 10 股 @ 200, 手续费 1 -> 总成本 2001, avg_cost = 200.1000
    engine.execute_buy(
        account=account,
        symbol="TSLA",
        qty=Decimal("10"),
        price=Decimal("200.0000"),
        fee=Decimal("1.0000"),
        position=pos,
    )
    assert pos.qty == Decimal("10.0000")
    assert pos.avg_cost == Decimal("200.1000")

    # 第二次加仓: 20 股 @ 230, 手续费 2 -> 增量成本 4602
    # 总成本: 2001 + 4602 = 6603; 总股数: 30; avg_cost = 6603 / 30 = 220.1000
    engine.execute_buy(
        account=account,
        symbol="TSLA",
        qty=Decimal("20"),
        price=Decimal("230.0000"),
        fee=Decimal("2.0000"),
        position=pos,
    )
    assert pos.qty == Decimal("30.0000")
    assert pos.avg_cost == Decimal("220.1000")
    assert account.cash == Decimal("50000.0000") - Decimal("6603.0000")


def test_partial_sell_realized_pnl_and_retained_cost() -> None:
    """部分平仓：平均成本保持不变，已实现盈亏结转并扣减卖出手续费。"""
    engine = AccountingEngine()
    account = AccountState(cash=Decimal("10000.0000"))
    pos = PositionState(symbol="MSFT")

    # 买入 20 股 @ 100, 费用 0 -> avg_cost = 100.0000
    engine.execute_buy(
        account=account,
        symbol="MSFT",
        qty=Decimal("20"),
        price=Decimal("100.0000"),
        fee=Decimal("0.0000"),
        position=pos,
    )
    assert account.cash == Decimal("8000.0000")

    # 卖出 8 股 @ 120, 费用 1.50
    # 毛利: (120 - 100) * 8 = 160
    # 净盈亏: 160 - 1.50 = 158.5000
    # 卖出回款: 8 * 120 - 1.50 = 958.5000
    rec = engine.execute_sell(
        account=account,
        symbol="MSFT",
        qty=Decimal("8"),
        price=Decimal("120.0000"),
        fee=Decimal("1.5000"),
        position=pos,
    )

    assert pos.qty == Decimal("12.0000")
    assert pos.avg_cost == Decimal("100.0000")  # 部分卖出成本不变
    assert pos.realized_pnl == Decimal("158.5000")
    assert rec.realized_pnl == Decimal("158.5000")
    assert account.cash == Decimal("8000.0000") + Decimal("958.5000")


def test_full_sell_resets_cost_and_accumulates_pnl() -> None:
    """全部平仓（清仓）：持仓为 0，成本归 0，再次建仓时重新计算成本。"""
    engine = AccountingEngine()
    account = AccountState(cash=Decimal("10000.0000"))
    pos = PositionState(symbol="NVDA")

    # 建仓
    engine.execute_buy(
        account=account,
        symbol="NVDA",
        qty=Decimal("10"),
        price=Decimal("100.0000"),
        fee=Decimal("1.0000"),
        position=pos,
    )
    assert pos.avg_cost == Decimal("100.1000")

    # 清仓 (亏损卖出)
    # 毛利: (90 - 100.10) * 10 = -101
    # 净盈亏: -101 - 1 = -102.0000
    # 回款: 10 * 90 - 1 = 899.0000
    rec = engine.execute_sell(
        account=account,
        symbol="NVDA",
        qty=Decimal("10"),
        price=Decimal("90.0000"),
        fee=Decimal("1.0000"),
        position=pos,
    )
    assert pos.qty == Decimal("0.0000")
    assert pos.avg_cost == Decimal("0.0000")
    assert pos.realized_pnl == Decimal("-102.0000")
    assert rec.realized_pnl == Decimal("-102.0000")

    # 再次重新建仓
    engine.execute_buy(
        account=account,
        symbol="NVDA",
        qty=Decimal("5"),
        price=Decimal("110.0000"),
        fee=Decimal("0.5000"),
        position=pos,
    )
    assert pos.qty == Decimal("5.0000")
    assert pos.avg_cost == Decimal("110.1000")  # (550 + 0.5) / 5
    # 原累积已实现盈亏保持
    assert pos.realized_pnl == Decimal("-102.0000")


# -----------------------------------------------------------------------------
# 2. 出入金与超限防御
# -----------------------------------------------------------------------------


def test_deposit_and_withdraw() -> None:
    """测试正常的入金与出金操作。"""
    engine = AccountingEngine()
    account = AccountState(cash=Decimal("5000.0000"))

    new_cash = engine.deposit(account, Decimal("2500.5000"))
    assert new_cash == Decimal("7500.5000")
    assert account.cash == Decimal("7500.5000")

    new_cash = engine.withdraw(account, Decimal("1500.0000"))
    assert new_cash == Decimal("6000.5000")
    assert account.cash == Decimal("6000.5000")


def test_withdraw_insufficient_cash() -> None:
    """提取超过当前可用现金时抛出 InsufficientCashError，且现金未被改变。"""
    engine = AccountingEngine()
    account = AccountState(cash=Decimal("1000.0000"))

    with pytest.raises(InsufficientCashError, match="Insufficient cash for withdrawal"):
        engine.withdraw(account, Decimal("1000.0001"))

    assert account.cash == Decimal("1000.0000")


def test_invalid_deposit_and_withdraw_amounts() -> None:
    """非正数金额出入金抛出 InvalidAmountError。"""
    engine = AccountingEngine()
    account = AccountState(cash=Decimal("1000.0000"))

    with pytest.raises(InvalidAmountError, match="Deposit amount must be positive"):
        engine.deposit(account, Decimal("0.0000"))

    with pytest.raises(InvalidAmountError, match="Deposit amount must be positive"):
        engine.deposit(account, Decimal("-100.0000"))

    with pytest.raises(InvalidAmountError, match="Withdrawal amount must be positive"):
        engine.withdraw(account, Decimal("0.0000"))

    with pytest.raises(InvalidAmountError, match="Withdrawal amount must be positive"):
        engine.withdraw(account, Decimal("-50.0000"))


# -----------------------------------------------------------------------------
# 3. 超卖防范与现金不足拦截（原子性保证）
# -----------------------------------------------------------------------------


def test_oversell_prevention() -> None:
    """超卖防御：持仓不足时拒绝卖出，保持状态原子不变。"""
    engine = AccountingEngine()
    account = AccountState(cash=Decimal("10000.0000"))
    pos = PositionState(symbol="GOOGL", qty=Decimal("10.0000"), avg_cost=Decimal("100.0000"))

    with pytest.raises(InsufficientPositionError, match="Insufficient position"):
        engine.execute_sell(
            account=account,
            symbol="GOOGL",
            qty=Decimal("10.0001"),
            price=Decimal("120.0000"),
            fee=Decimal("1.0000"),
            position=pos,
        )

    # 状态严格不变
    assert account.cash == Decimal("10000.0000")
    assert pos.qty == Decimal("10.0000")
    assert pos.avg_cost == Decimal("100.0000")


def test_sell_without_position() -> None:
    """无持仓对象时尝试卖出抛出 InsufficientPositionError。"""
    engine = AccountingEngine()
    account = AccountState(cash=Decimal("10000.0000"))

    with pytest.raises(InsufficientPositionError, match="No position found"):
        engine.execute_sell(
            account=account,
            symbol="UNKNOWN",
            qty=Decimal("5.0000"),
            price=Decimal("100.0000"),
            position=None,
        )


def test_buy_insufficient_cash_atomicity() -> None:
    """现金不足时买入失败，账户与持仓完全不变。"""
    engine = AccountingEngine()
    account = AccountState(cash=Decimal("500.0000"))
    pos = PositionState(symbol="AMZN", qty=Decimal("2.0000"), avg_cost=Decimal("150.0000"))

    with pytest.raises(InsufficientCashError, match="Insufficient cash for buy"):
        engine.execute_buy(
            account=account,
            symbol="AMZN",
            qty=Decimal("10.0000"),
            price=Decimal("150.0000"),
            fee=Decimal("1.0000"),
            position=pos,
        )

    assert account.cash == Decimal("500.0000")
    assert pos.qty == Decimal("2.0000")
    assert pos.avg_cost == Decimal("150.0000")


def test_invalid_order_parameters() -> None:
    """非正数数量、价格或负手续费抛出 InvalidAmountError。"""
    engine = AccountingEngine()
    account = AccountState(cash=Decimal("10000.0000"))

    with pytest.raises(InvalidAmountError, match="Buy quantity must be positive"):
        engine.execute_buy(account, "AAPL", Decimal("0"), Decimal("100"))

    with pytest.raises(InvalidAmountError, match="Buy price must be positive"):
        engine.execute_buy(account, "AAPL", Decimal("10"), Decimal("-100"))

    with pytest.raises(InvalidAmountError, match="Fee cannot be negative"):
        engine.execute_buy(account, "AAPL", Decimal("10"), Decimal("100"), fee=Decimal("-1"))


# -----------------------------------------------------------------------------
# 4. 并发幂等性防护
# -----------------------------------------------------------------------------


def test_idempotent_key_duplicate_rejection() -> None:
    """同一 idempotency_key 再次提交时抛出 DuplicateTransactionError，金额不重复扣减。"""
    engine = AccountingEngine()
    account = AccountState(cash=Decimal("10000.0000"))
    pos = PositionState(symbol="AAPL")
    idem_key = "order-idem-12345"

    rec1 = engine.execute_buy(
        account=account,
        symbol="AAPL",
        qty=Decimal("10"),
        price=Decimal("100"),
        fee=Decimal("1"),
        position=pos,
        idempotency_key=idem_key,
    )
    assert account.cash == Decimal("8999.0000")
    assert pos.qty == Decimal("10.0000")
    assert engine.has_processed_key(idem_key) is True
    assert engine.get_processed_record(idem_key) == rec1

    # 第二次使用相同 key 提交
    with pytest.raises(DuplicateTransactionError, match="already processed"):
        engine.execute_buy(
            account=account,
            symbol="AAPL",
            qty=Decimal("10"),
            price=Decimal("100"),
            fee=Decimal("1"),
            position=pos,
            idempotency_key=idem_key,
        )

    # 状态没有被重复扣减
    assert account.cash == Decimal("8999.0000")
    assert pos.qty == Decimal("10.0000")


def test_concurrent_idempotency_race_condition() -> None:
    """多线程并发提交相同 idempotency_key，严格有且仅有 1 个成功。"""
    engine = AccountingEngine()
    account = AccountState(cash=Decimal("100000.0000"))
    pos = PositionState(symbol="AAPL")
    idem_key = "concurrent-key-999"

    success_count = 0
    duplicate_count = 0

    def submit() -> str:
        try:
            engine.execute_buy(
                account=account,
                symbol="AAPL",
                qty=Decimal("5"),
                price=Decimal("100"),
                fee=Decimal("1"),
                position=pos,
                idempotency_key=idem_key,
            )
            return "success"
        except DuplicateTransactionError:
            return "duplicate"

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(submit) for _ in range(10)]
        results = [f.result() for f in futures]

    success_count = results.count("success")
    duplicate_count = results.count("duplicate")

    assert success_count == 1
    assert duplicate_count == 9
    # 现金严格只扣减一次: 5 * 100 + 1 = 501
    assert account.cash == Decimal("100000.0000") - Decimal("501.0000")
    assert pos.qty == Decimal("5.0000")


# -----------------------------------------------------------------------------
# 5. 财务不变量综合审计与验证
# -----------------------------------------------------------------------------


def test_invariants_audit_success_scenario() -> None:
    """在复杂交易序列后，综合审计报告显示所有财务不变量均 100% 成立。"""
    engine = AccountingEngine()
    initial_cash = Decimal("50000.0000")
    account = AccountState(cash=initial_cash)

    deposits: list[Decimal] = [Decimal("10000.0000"), Decimal("5000.0000")]
    withdrawals: list[Decimal] = [Decimal("3000.0000")]

    for d in deposits:
        engine.deposit(account, d)
    for w in withdrawals:
        engine.withdraw(account, w)

    trades: list[TradeExecutionRecord] = []
    positions: dict[str, PositionState] = {
        "AAPL": PositionState(symbol="AAPL"),
        "TSLA": PositionState(symbol="TSLA"),
    }

    # 买入 AAPL 20 @ 150, fee 2
    trades.append(
        engine.execute_buy(
            account, "AAPL", Decimal("20"), Decimal("150"), Decimal("2"), positions["AAPL"]
        )
    )
    # 买入 TSLA 10 @ 200, fee 1
    trades.append(
        engine.execute_buy(
            account, "TSLA", Decimal("10"), Decimal("200"), Decimal("1"), positions["TSLA"]
        )
    )
    # 卖出 AAPL 5 @ 160, fee 1
    trades.append(
        engine.execute_sell(
            account, "AAPL", Decimal("5"), Decimal("160"), Decimal("1"), positions["AAPL"]
        )
    )

    current_prices = {
        "AAPL": Decimal("165.0000"),
        "TSLA": Decimal("210.0000"),
    }

    report = engine.audit_invariants(
        initial_cash=initial_cash,
        deposits=deposits,
        withdrawals=withdrawals,
        trade_records=trades,
        positions=list(positions.values()),
        current_prices=current_prices,
        account=account,
    )

    assert report.is_valid is True
    assert report.cash_conservation_valid is True
    assert report.equity_identity_valid is True
    assert report.non_negative_positions_valid is True
    assert report.violations == []
    assert report.cash_discrepancy == Decimal("0.0000")
    assert report.equity_discrepancy == Decimal("0.0000")


def test_invariants_audit_tampered_cash_detection() -> None:
    """人工篡改现金时，审计报告准确拦截并报告现金守恒破坏。"""
    engine = AccountingEngine()
    account = AccountState(cash=Decimal("10000.0000"))
    pos = PositionState(symbol="AAPL")
    tr = engine.execute_buy(account, "AAPL", Decimal("10"), Decimal("100"), Decimal("1"), pos)

    # 恶意篡改现金
    account.cash += Decimal("100.0000")

    report = engine.audit_invariants(
        initial_cash=Decimal("10000.0000"),
        deposits=[],
        withdrawals=[],
        trade_records=[tr],
        positions=[pos],
        current_prices={"AAPL": Decimal("100")},
        account=account,
    )

    assert report.is_valid is False
    assert report.cash_conservation_valid is False
    assert any("Cash conservation broken" in v for v in report.violations)


def test_invariants_audit_negative_position_detection() -> None:
    """持仓数量为负数时，审计报告准确拦截持仓非负性破坏。"""
    engine = AccountingEngine()
    account = AccountState(cash=Decimal("10000.0000"))
    illegal_pos = PositionState(symbol="BAD", qty=Decimal("-5.0000"))

    report = engine.audit_invariants(
        initial_cash=Decimal("10000.0000"),
        deposits=[],
        withdrawals=[],
        trade_records=[],
        positions=[illegal_pos],
        current_prices={},
        account=account,
    )

    assert report.is_valid is False
    assert report.non_negative_positions_valid is False
    assert any("Non-negative position invariant violated" in v for v in report.violations)


# -----------------------------------------------------------------------------
# 6. 基于 Hypothesis 的随机交易序列财务不变量属性测试
# -----------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    initial_cash=st.decimals(min_value=Decimal("10000"), max_value=Decimal("100000"), places=2),
    operations=st.lists(
        st.tuples(
            st.sampled_from(["buy", "sell", "deposit", "withdraw"]),
            st.decimals(min_value=Decimal("1"), max_value=Decimal("20"), places=2),  # qty or amount
            st.decimals(min_value=Decimal("10"), max_value=Decimal("500"), places=2),  # price
            st.decimals(min_value=Decimal("0"), max_value=Decimal("3"), places=2),  # fee
        ),
        min_size=10,
        max_size=50,
    ),
)
def test_hypothesis_invariants_over_random_sequences(
    initial_cash: Decimal,
    operations: list[tuple[str, Decimal, Decimal, Decimal]],
) -> None:
    """基于 Hypothesis 生成随机交易流，严格验证三大财务不变量在任意操作序列下 100% 守恒。"""
    engine = AccountingEngine()
    account = AccountState(cash=initial_cash)
    positions: dict[str, PositionState] = {"TEST": PositionState(symbol="TEST")}

    deposits: list[Decimal] = []
    withdrawals: list[Decimal] = []
    trades: list[TradeExecutionRecord] = []

    for op, val1, val2, val3 in operations:
        pos = positions["TEST"]
        if op == "deposit":
            engine.deposit(account, val1)
            deposits.append(val1)
        elif op == "withdraw":
            if account.cash >= val1:
                engine.withdraw(account, val1)
                withdrawals.append(val1)
        elif op == "buy":
            qty, price, fee = val1, val2, val3
            cost = qty * price + fee
            if account.cash >= cost:
                rec = engine.execute_buy(account, "TEST", qty, price, fee, pos)
                trades.append(rec)
        elif op == "sell":
            qty, price, fee = val1, val2, val3
            if pos.qty >= qty:
                rec = engine.execute_sell(account, "TEST", qty, price, fee, pos)
                trades.append(rec)

    # 1. 验证持仓非负性
    assert pos.qty >= Decimal("0.0000")

    # 2. 验证现金守恒性
    assert (
        engine.verify_cash_conservation(
            initial_cash=initial_cash,
            deposits=deposits,
            withdrawals=withdrawals,
            trade_records=trades,
            current_cash=account.cash,
        )
        is True
    )

    # 3. 验证净值恒等性
    market_price = Decimal("150.0000")
    summary = engine.calculate_equity_summary(
        account=account,
        positions=[pos],
        current_prices={"TEST": market_price},
    )
    assert (
        engine.verify_equity_identity(
            equity=summary.equity,
            cash=account.cash,
            market_value=summary.market_value,
        )
        is True
    )


# -----------------------------------------------------------------------------
# 7. ORM 实体（SimAccount, SimPosition, SimTrade）集成兼容性
# -----------------------------------------------------------------------------


def test_accounting_engine_with_orm_models() -> None:
    """验证 AccountingEngine 可以直接对 SQLAlchemy ORM 实体（SimAccount, SimPosition）生效。"""
    user_id = uuid.uuid4()
    account_id = uuid.uuid4()
    order_id = uuid.uuid4()

    orm_account = SimAccount(
        id=account_id,
        user_id=user_id,
        name="ORM Account",
        initial_cash=Decimal("50000.0000"),
        cash=Decimal("50000.0000"),
    )

    orm_position = SimPosition(
        user_id=user_id,
        account_id=account_id,
        symbol="SPY",
        qty=Decimal("0.0000"),
        avg_cost=Decimal("0.0000"),
        realized_pnl=Decimal("0.0000"),
    )

    engine = AccountingEngine()

    # 买入 10 股 SPY @ 500, 手续费 2
    rec = engine.execute_buy(
        account=orm_account,
        symbol="SPY",
        qty=Decimal("10.0000"),
        price=Decimal("500.0000"),
        fee=Decimal("2.0000"),
        position=orm_position,
    )

    assert orm_account.cash == Decimal("44998.0000")
    assert orm_position.qty == Decimal("10.0000")
    assert orm_position.avg_cost == Decimal("500.2000")

    # 构建 SimTrade ORM 实体
    trade_entity = AccountingEngine.create_sim_trade(
        record=rec,
        user_id=user_id,
        account_id=account_id,
        order_id=order_id,
    )

    assert isinstance(trade_entity, SimTrade)
    assert trade_entity.user_id == user_id
    assert trade_entity.account_id == account_id
    assert trade_entity.symbol == "SPY"
    assert trade_entity.side == "buy"
    assert trade_entity.qty == Decimal("10.0000")
    assert trade_entity.price == Decimal("500.0000")
    assert trade_entity.fee == Decimal("2.0000")
    assert trade_entity.realized_pnl == Decimal("0.0000")


# -----------------------------------------------------------------------------
# 8. 浮动盈亏与估值指标计算
# -----------------------------------------------------------------------------


def test_position_metrics_and_unrealized_pnl() -> None:
    """测试单个持仓浮动盈亏计算（盈利与亏损）。"""
    engine = AccountingEngine()

    # 盈利场景: 成本 100, 现价 120 -> +20%
    pos_gain = PositionState(symbol="WIN", qty=Decimal("10.0000"), avg_cost=Decimal("100.0000"))
    metrics_gain = engine.calculate_position_metrics(pos_gain, Decimal("120.0000"))
    assert metrics_gain.market_value == Decimal("1200.0000")
    assert metrics_gain.unrealized_pnl == Decimal("200.0000")
    assert metrics_gain.unrealized_pnl_pct == Decimal("20.0000")

    # 亏损场景: 成本 100, 现价 80 -> -20%
    pos_loss = PositionState(symbol="LOSS", qty=Decimal("10.0000"), avg_cost=Decimal("100.0000"))
    metrics_loss = engine.calculate_position_metrics(pos_loss, Decimal("80.0000"))
    assert metrics_loss.market_value == Decimal("800.0000")
    assert metrics_loss.unrealized_pnl == Decimal("-200.0000")
    assert metrics_loss.unrealized_pnl_pct == Decimal("-20.0000")

    # 空仓场景
    pos_empty = PositionState(symbol="EMPTY", qty=Decimal("0.0000"), avg_cost=Decimal("0.0000"))
    metrics_empty = engine.calculate_position_metrics(pos_empty, Decimal("100.0000"))
    assert metrics_empty.market_value == Decimal("0.0000")
    assert metrics_empty.unrealized_pnl == Decimal("0.0000")
    assert metrics_empty.unrealized_pnl_pct == Decimal("0.0000")


# -----------------------------------------------------------------------------
# 9. 扩展边界分支与接口完整性测试
# -----------------------------------------------------------------------------


def test_execute_trade_dispatcher() -> None:
    """测试统一 execute_trade 入口的分发与非法 side 拦截。"""
    engine = AccountingEngine()
    account = AccountState(cash=Decimal("10000.0000"))
    pos = PositionState(symbol="AAPL")

    # 分发 buy
    rec_buy = engine.execute_trade(
        account=account,
        symbol="AAPL",
        side="buy",
        qty=Decimal("10"),
        price=Decimal("100"),
        fee=Decimal("1"),
        position=pos,
    )
    assert rec_buy.side == "buy"
    assert pos.qty == Decimal("10")

    # 分发 sell
    rec_sell = engine.execute_trade(
        account=account,
        symbol="AAPL",
        side="sell",
        qty=Decimal("5"),
        price=Decimal("110"),
        fee=Decimal("1"),
        position=pos,
    )
    assert rec_sell.side == "sell"
    assert pos.qty == Decimal("5")

    # 非法 side
    with pytest.raises(ValueError, match="Unsupported trade side"):
        engine.execute_trade(
            account=account,
            symbol="AAPL",
            side="hold",  # type: ignore[arg-type]
            qty=Decimal("1"),
            price=Decimal("100"),
            position=pos,
        )


def test_execute_sell_invalid_parameters_and_idempotency() -> None:
    """测试 execute_sell 的边界参数拦截与幂等键拒绝。"""
    engine = AccountingEngine()
    account = AccountState(cash=Decimal("10000.0000"))
    pos = PositionState(symbol="TEST", qty=Decimal("10"), avg_cost=Decimal("100"))

    with pytest.raises(InvalidAmountError, match="Sell quantity must be positive"):
        engine.execute_sell(account, "TEST", Decimal("0"), Decimal("100"), position=pos)

    with pytest.raises(InvalidAmountError, match="Sell price must be positive"):
        engine.execute_sell(account, "TEST", Decimal("5"), Decimal("-10"), position=pos)

    with pytest.raises(InvalidAmountError, match="Fee cannot be negative"):
        engine.execute_sell(
            account, "TEST", Decimal("5"), Decimal("100"), fee=Decimal("-1"), position=pos
        )

    # 首次卖出带 idempotency_key
    engine.execute_sell(
        account,
        "TEST",
        Decimal("2"),
        Decimal("100"),
        fee=Decimal("0"),
        position=pos,
        idempotency_key="sell-key-1",
    )
    # 重复提交
    with pytest.raises(DuplicateTransactionError, match="already processed"):
        engine.execute_sell(
            account,
            "TEST",
            Decimal("2"),
            Decimal("100"),
            fee=Decimal("0"),
            position=pos,
            idempotency_key="sell-key-1",
        )


def test_buy_without_position_object() -> None:
    """测试 execute_buy 当 position 为 None 时正常返回记录。"""
    engine = AccountingEngine()
    account = AccountState(cash=Decimal("10000.0000"))

    rec = engine.execute_buy(
        account, "AAPL", Decimal("5"), Decimal("200"), fee=Decimal("2"), position=None
    )
    assert rec.position_qty_before == Decimal("0")
    assert rec.position_qty_after == Decimal("5")
    assert rec.avg_cost_after == Decimal("200.4000")  # (1000 + 2) / 5
    assert account.cash == Decimal("10000") - Decimal("1002")


def test_zero_equity_cash_ratio_and_audit_equity_tampered() -> None:
    """测试净值为 0 时的现金占比以及净值不一致时审计报告拦截。"""
    engine = AccountingEngine()
    account = AccountState(cash=Decimal("0.0000"))

    summary = engine.calculate_equity_summary(account, [], {})
    assert summary.equity == Decimal("0.0000")
    assert summary.cash_ratio == Decimal("0.0000")

    # 审计不变量时检测到净值被破坏
    # 模拟外部篡改场景：注入一个虚假破坏净值的自定义类
    class BrokenSummaryEngine(AccountingEngine):
        def calculate_equity_summary(self, *args: object, **kwargs: object) -> AccountEquitySummary:
            return AccountEquitySummary(
                cash=Decimal("100.0000"),
                market_value=Decimal("0.0000"),
                equity=Decimal("999.0000"),  # 故意虚标
                cash_ratio=Decimal("10.0000"),
                position_count=0,
            )

    broken_engine = BrokenSummaryEngine()
    report = broken_engine.audit_invariants(
        initial_cash=Decimal("100.0000"),
        deposits=[],
        withdrawals=[],
        trade_records=[],
        positions=[],
        current_prices={},
        account=AccountState(cash=Decimal("100.0000")),
    )
    assert report.is_valid is False
    assert report.equity_identity_valid is False
    assert any("Equity identity broken" in v for v in report.violations)


def test_clear_idempotency_keys_and_unquantized_mode() -> None:
    """测试清空幂等键与无量化模式。"""
    engine = AccountingEngine(quantize_places=None)
    account = AccountState(cash=Decimal("10000"))
    pos = PositionState(symbol="RAW")

    engine.execute_buy(
        account, "RAW", Decimal("1"), Decimal("100"), idempotency_key="k1", position=pos
    )
    assert engine.has_processed_key("k1") is True

    engine.clear_idempotency_keys()
    assert engine.has_processed_key("k1") is False

    # 再次使用相同的 k1 可以正常执行
    engine.execute_buy(
        account, "RAW", Decimal("1"), Decimal("100"), idempotency_key="k1", position=pos
    )
    assert engine.has_processed_key("k1") is True
