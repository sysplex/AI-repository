"""M4-T06 绩效分析、回撤胜率、SPY 跑赢对比与持仓风险体检单元测试。

涵盖：
1. 总收益额、总收益率与初始资金为 0 防御
2. 净值曲线与全局最大回撤（MDD）核算
3. 交易胜率（Win Rate）与盈亏比（Profit/Loss Ratio 除以零保护）
4. 基准 SPY 收益对比与 Alpha/Beta 指标
5. 持仓风险体检（现金水位、单股集中度排序、行业板块权重分布、PDT 预警状态）
6. 投资组合比例守恒（单股权重和 + 现金占比 == 100%）
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from app.modules.simbroker.performance import PerformanceAnalyzer
from app.modules.simbroker.risk import RiskAnalyzer
from app.modules.simbroker.schemas import PerformanceMetrics, RiskOverview

# -----------------------------------------------------------------------------
# 测试辅助双
# -----------------------------------------------------------------------------


@dataclass
class MockSnapshot:
    trade_date: date
    cash: Decimal
    market_value: Decimal
    equity: Decimal
    drawdown: Decimal = Decimal("0.000000")


@dataclass
class MockTrade:
    realized_pnl: Decimal


@dataclass
class MockPosition:
    symbol: str
    qty: Decimal
    avg_cost: Decimal


class MockMarketDataFeed:
    def __init__(
        self,
        prices: dict[str, Decimal] | None = None,
        sectors: dict[str, str] | None = None,
        sp500_return: Decimal | None = None,
    ) -> None:
        self.prices = prices or {}
        self.sectors = sectors or {}
        self.sp500_return = sp500_return

    def get_latest_price(self, symbol: str) -> Decimal | None:
        return self.prices.get(symbol)

    def get_daily_bar(self, symbol: str, trade_date: date) -> Any | None:
        return None

    def get_sp500_return(self, start_date: date, end_date: date) -> Decimal | None:
        return self.sp500_return

    def get_symbol_sector(self, symbol: str) -> str | None:
        return self.sectors.get(symbol)


# -----------------------------------------------------------------------------
# 1. 基础总收益与收益率计算
# -----------------------------------------------------------------------------


def test_performance_total_return_gain() -> None:
    """测试正收益情境：初始 100,000，当前 125,000 -> +25,000 (+25.0000%)。"""
    acc_id = uuid.uuid4()
    metrics: PerformanceMetrics = PerformanceAnalyzer.analyze(
        account_id=acc_id,
        initial_cash=Decimal("100000.0000"),
        current_equity=Decimal("125000.0000"),
        equity_snapshots=[],
        closed_trades=[],
    )

    assert metrics.account_id == acc_id
    assert metrics.total_return == Decimal("25000.0000")
    assert metrics.total_return_pct == Decimal("25.0000")
    assert metrics.win_rate == Decimal("0.0000")
    assert metrics.profit_loss_ratio == Decimal("0.0000")


def test_performance_total_return_loss() -> None:
    """测试亏损情境：初始 100,000，当前 85,000 -> -15,000 (-15.0000%)。"""
    metrics = PerformanceAnalyzer.analyze(
        account_id=uuid.uuid4(),
        initial_cash=Decimal("100000.0000"),
        current_equity=Decimal("85000.0000"),
        equity_snapshots=[],
        closed_trades=[],
    )

    assert metrics.total_return == Decimal("-15000.0000")
    assert metrics.total_return_pct == Decimal("-15.0000")


def test_performance_zero_initial_cash_defense() -> None:
    """初始资金为 0 时的除以零防御。"""
    metrics = PerformanceAnalyzer.analyze(
        account_id=uuid.uuid4(),
        initial_cash=Decimal("0.0000"),
        current_equity=Decimal("5000.0000"),
        equity_snapshots=[],
        closed_trades=[],
    )

    assert metrics.total_return == Decimal("5000.0000")
    assert metrics.total_return_pct == Decimal("0.0000")


# -----------------------------------------------------------------------------
# 2. 净值曲线与全局最大回撤
# -----------------------------------------------------------------------------


def test_performance_max_drawdown_calculation() -> None:
    """测试净值曲线全局最大回撤计算：100k -> 120k (peak) -> 96k (回撤 20%) -> 110k。"""
    snapshots = [
        MockSnapshot(
            date(2026, 11, 10),
            Decimal("100000"),
            Decimal("0"),
            Decimal("100000.0000"),
            Decimal("0.000000"),
        ),
        MockSnapshot(
            date(2026, 11, 11),
            Decimal("60000"),
            Decimal("60000"),
            Decimal("120000.0000"),
            Decimal("0.000000"),
        ),
        MockSnapshot(
            date(2026, 11, 12),
            Decimal("50000"),
            Decimal("46000"),
            Decimal("96000.0000"),
            Decimal("0.200000"),
        ),
        MockSnapshot(
            date(2026, 11, 13),
            Decimal("50000"),
            Decimal("60000"),
            Decimal("110000.0000"),
            Decimal("0.083333"),
        ),
    ]

    metrics = PerformanceAnalyzer.analyze(
        account_id=uuid.uuid4(),
        initial_cash=Decimal("100000.0000"),
        current_equity=Decimal("110000.0000"),
        equity_snapshots=snapshots,
        closed_trades=[],
    )

    # 最大回撤为 20% (0.200000)
    assert metrics.max_drawdown == Decimal("0.200000")
    assert len(metrics.equity_curve) == 4
    assert metrics.equity_curve[1].equity == Decimal("120000.0000")


# -----------------------------------------------------------------------------
# 3. 胜率与盈亏比
# -----------------------------------------------------------------------------


def test_win_rate_and_profit_loss_ratio_mixed() -> None:
    """测试多笔盈利与亏损混合场景：3 赢 2 输，胜率 60%，总赢 600 / 总输 200 = 3.0。"""
    trades = [
        MockTrade(realized_pnl=Decimal("100.0000")),
        MockTrade(realized_pnl=Decimal("200.0000")),
        MockTrade(realized_pnl=Decimal("300.0000")),
        MockTrade(realized_pnl=Decimal("-150.0000")),
        MockTrade(realized_pnl=Decimal("-50.0000")),
    ]

    metrics = PerformanceAnalyzer.analyze(
        account_id=uuid.uuid4(),
        initial_cash=Decimal("50000.0000"),
        current_equity=Decimal("50400.0000"),
        equity_snapshots=[],
        closed_trades=trades,
    )

    assert metrics.total_trades == 5
    assert metrics.winning_trades == 3
    assert metrics.losing_trades == 2
    # 3 / 5 = 60.0000%
    assert metrics.win_rate == Decimal("60.0000")
    # 600 / 200 = 3.0000
    assert metrics.profit_loss_ratio == Decimal("3.0000")


def test_win_rate_and_profit_loss_ratio_all_wins() -> None:
    """全胜场景：胜率 100%，盈亏比为 999.9999（无除以零）。"""
    trades = [
        MockTrade(realized_pnl=Decimal("500.0000")),
        MockTrade(realized_pnl=Decimal("300.0000")),
    ]

    metrics = PerformanceAnalyzer.analyze(
        account_id=uuid.uuid4(),
        initial_cash=Decimal("10000.0000"),
        current_equity=Decimal("10800.0000"),
        equity_snapshots=[],
        closed_trades=trades,
    )

    assert metrics.winning_trades == 2
    assert metrics.losing_trades == 0
    assert metrics.win_rate == Decimal("100.0000")
    assert metrics.profit_loss_ratio == Decimal("999.9999")


def test_win_rate_and_profit_loss_ratio_all_losses() -> None:
    """全败场景：胜率 0%，盈亏比 0.0000。"""
    trades = [
        MockTrade(realized_pnl=Decimal("-200.0000")),
        MockTrade(realized_pnl=Decimal("-100.0000")),
    ]

    metrics = PerformanceAnalyzer.analyze(
        account_id=uuid.uuid4(),
        initial_cash=Decimal("10000.0000"),
        current_equity=Decimal("9700.0000"),
        equity_snapshots=[],
        closed_trades=trades,
    )

    assert metrics.winning_trades == 0
    assert metrics.losing_trades == 2
    assert metrics.win_rate == Decimal("0.0000")
    assert metrics.profit_loss_ratio == Decimal("0.0000")


# -----------------------------------------------------------------------------
# 4. 基准对比（SPY）与 Alpha/Beta
# -----------------------------------------------------------------------------


def test_performance_benchmark_spy_comparison() -> None:
    """与标普 500 (SPY) 基准对比：计算超额收益 Alpha 与 Beta。"""
    feed = MockMarketDataFeed(sp500_return=Decimal("8.5000"))  # SPY 涨幅 8.5%
    snapshots = [
        MockSnapshot(date(2026, 1, 1), Decimal("100000"), Decimal("0"), Decimal("100000.0000")),
        MockSnapshot(
            date(2026, 11, 13), Decimal("20000"), Decimal("105000"), Decimal("125000.0000")
        ),
    ]

    metrics = PerformanceAnalyzer.analyze(
        account_id=uuid.uuid4(),
        initial_cash=Decimal("100000.0000"),
        current_equity=Decimal("125000.0000"),  # 账户涨幅 +25.0%
        equity_snapshots=snapshots,
        closed_trades=[],
        benchmark_feed=feed,
    )

    assert metrics.benchmark_return_pct == Decimal("8.5000")
    # Alpha = 25.0000 - 8.5000 = 16.5000%
    assert metrics.alpha == Decimal("16.5000")
    assert metrics.beta == Decimal("1.0000")


# -----------------------------------------------------------------------------
# 5. 持仓风险体检诊断
# -----------------------------------------------------------------------------


def test_risk_analyzer_portfolio_weights_and_sectors() -> None:
    """持仓风险体检：核算现金占比、单股权重降序、行业分布及 PDT 监控。"""
    acc_id = uuid.uuid4()
    positions = [
        MockPosition(symbol="AAPL", qty=Decimal("100.0000"), avg_cost=Decimal("150.0000")),
        MockPosition(symbol="TSLA", qty=Decimal("50.0000"), avg_cost=Decimal("200.0000")),
        MockPosition(symbol="CLOSED", qty=Decimal("0.0000"), avg_cost=Decimal("0.0000")),
    ]

    # 市价设置:
    # AAPL: 100 * 180 = 18,000
    # TSLA: 50 * 240 = 12,000
    # 现金: 20,000
    # 总市值: 30,000; 总净值: 50,000
    prices = {
        "AAPL": Decimal("180.0000"),
        "TSLA": Decimal("240.0000"),
    }
    sectors = {
        "AAPL": "Technology",
        "TSLA": "Consumer Cyclical",
    }
    feed = MockMarketDataFeed(prices=prices, sectors=sectors)

    overview: RiskOverview = RiskAnalyzer.analyze(
        account_id=acc_id,
        account_cash=Decimal("20000.0000"),
        positions=positions,
        current_prices=prices,
        market_feed=feed,
        rolling_day_trades=3,
        pdt_warning=True,
    )

    assert overview.account_id == acc_id
    # 现金占比: 20,000 / 50,000 = 40.0000%
    assert overview.cash_ratio == Decimal("40.0000")

    # 单股占比:
    # AAPL: 18,000 / 50,000 = 36.0000%
    # TSLA: 12,000 / 50,000 = 24.0000%
    assert overview.single_stock_weights["AAPL"] == Decimal("36.0000")
    assert overview.single_stock_weights["TSLA"] == Decimal("24.0000")

    # 验证资产占比守恒: 现金(40%) + AAPL(36%) + TSLA(24%) == 100%
    total_weights = (
        overview.cash_ratio
        + overview.single_stock_weights["AAPL"]
        + overview.single_stock_weights["TSLA"]
    )
    assert total_weights == Decimal("100.0000")

    # 集中度降序校验
    assert overview.top_positions == [
        ("AAPL", Decimal("36.0000")),
        ("TSLA", Decimal("24.0000")),
    ]

    # 板块权重
    assert overview.sector_weights["Technology"] == Decimal("36.0000")
    assert overview.sector_weights["Consumer Cyclical"] == Decimal("24.0000")

    # PDT 状态
    assert overview.pdt_day_trades_count == 3
    assert overview.pdt_warning is True


def test_risk_analyzer_all_cash_portfolio() -> None:
    """全现金无持仓场景。"""
    overview = RiskAnalyzer.analyze(
        account_id=uuid.uuid4(),
        account_cash=Decimal("100000.0000"),
        positions=[],
    )

    assert overview.cash_ratio == Decimal("100.0000")
    assert overview.single_stock_weights == {}
    assert overview.top_positions == []
    assert overview.sector_weights == {}
    assert overview.pdt_warning is False


def test_risk_analyzer_zero_equity_defense() -> None:
    """总净值为 0 时的除以零防御。"""
    overview = RiskAnalyzer.analyze(
        account_id=uuid.uuid4(),
        account_cash=Decimal("0.0000"),
        positions=[],
    )

    assert overview.cash_ratio == Decimal("0.0000")
    assert overview.single_stock_weights == {}
