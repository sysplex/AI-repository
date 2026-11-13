"""M4 持仓风险体检引擎（T06），`CONTRACTS.md §1 & §3`。

实现投资组合健康度与风险体检诊断：
1. 现金仓位占比（Cash Ratio）；
2. 单个股票仓位权重（Single Stock Weights）；
3. 前 N 大持仓集中度排序（Top Positions）；
4. 行业板块权重分布（Sector Weights）；
5. PDT 交易频率与风险预警评估；
6. 输出标准化 RiskOverview DTO。
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import structlog

from app.modules.simbroker.ports import MarketDataFeedProtocol
from app.modules.simbroker.schemas import RiskOverview

logger = structlog.get_logger(__name__)

__all__ = ["RiskAnalyzer"]

_QUANTIZE_RATIO = Decimal("0.0001")
_QUANTIZE_CASH = Decimal("0.0001")


class RiskAnalyzer:
    """投资组合风险诊断分析器。"""

    @classmethod
    def analyze(
        cls,
        account_id: uuid.UUID,
        account_cash: Decimal,
        positions: Sequence[Any],
        current_prices: Mapping[str, Decimal] | None = None,
        market_feed: MarketDataFeedProtocol | None = None,
        rolling_day_trades: int = 0,
        pdt_warning: bool = False,
    ) -> RiskOverview:
        """评估当前投资组合的集中度、资产分布与监管风险。

        :param account_id: 账户唯一标识
        :param account_cash: 账户可用现金
        :param positions: 账户当前持仓列表
        :param current_prices: 标的现价字典映射
        :param market_feed: 行情与板块数据源协议（用于获取行业分类）
        :param rolling_day_trades: 近 5 个交易日日内交易次数
        :param pdt_warning: 是否触及 PDT 预警线
        :return: RiskOverview 规范 DTO
        """
        # 1. 计算每个持仓的市值
        position_market_values: dict[str, Decimal] = {}
        total_market_value = Decimal("0.0000")

        for pos in positions:
            if pos.qty <= Decimal("0"):
                continue

            symbol = pos.symbol
            price: Decimal | None = None
            if current_prices is not None and symbol in current_prices:
                price = current_prices[symbol]
            elif market_feed is not None:
                price = market_feed.get_latest_price(symbol)

            if price is None:
                price = pos.avg_cost

            mv = (pos.qty * price).quantize(_QUANTIZE_CASH, rounding=ROUND_HALF_UP)
            position_market_values[symbol] = mv
            total_market_value += mv

        cash = account_cash.quantize(_QUANTIZE_CASH, rounding=ROUND_HALF_UP)
        total_equity = (cash + total_market_value).quantize(_QUANTIZE_CASH, rounding=ROUND_HALF_UP)

        # 2. 现金仓位占比
        if total_equity > Decimal("0"):
            cash_ratio = (cash / total_equity * Decimal("100")).quantize(
                _QUANTIZE_RATIO, rounding=ROUND_HALF_UP
            )
        else:
            cash_ratio = Decimal("0.0000")

        # 3. 单股仓位占比
        single_stock_weights: dict[str, Decimal] = {}
        for symbol, mv in position_market_values.items():
            if total_equity > Decimal("0"):
                weight = (mv / total_equity * Decimal("100")).quantize(
                    _QUANTIZE_RATIO, rounding=ROUND_HALF_UP
                )
            else:
                weight = Decimal("0.0000")
            single_stock_weights[symbol] = weight

        # 4. 前 N 大持仓集中度排序（按持仓权重由大到小）
        sorted_positions = sorted(
            single_stock_weights.items(),
            key=lambda item: item[1],
            reverse=True,
        )
        top_positions: list[tuple[str, Decimal]] = [(sym, wt) for sym, wt in sorted_positions]

        # 5. 行业板块权重分布统计
        sector_totals: dict[str, Decimal] = {}
        for symbol, mv in position_market_values.items():
            sector: str | None = None
            if market_feed is not None:
                sector = market_feed.get_symbol_sector(symbol)
            if not sector:
                sector = "Other"

            sector_totals[sector] = sector_totals.get(sector, Decimal("0.0000")) + mv

        sector_weights: dict[str, Decimal] = {}
        for sector, sec_mv in sector_totals.items():
            if total_equity > Decimal("0"):
                sec_wt = (sec_mv / total_equity * Decimal("100")).quantize(
                    _QUANTIZE_RATIO, rounding=ROUND_HALF_UP
                )
            else:
                sec_wt = Decimal("0.0000")
            sector_weights[sector] = sec_wt

        logger.info(
            "Analyzed risk overview",
            account_id=str(account_id),
            cash_ratio=str(cash_ratio),
            position_count=len(position_market_values),
            pdt_day_trades=rolling_day_trades,
            pdt_warning=pdt_warning,
        )

        return RiskOverview(
            account_id=account_id,
            cash_ratio=cash_ratio,
            single_stock_weights=single_stock_weights,
            top_positions=top_positions,
            sector_weights=sector_weights,
            pdt_day_trades_count=rolling_day_trades,
            pdt_warning=pdt_warning,
        )
