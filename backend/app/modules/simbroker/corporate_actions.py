"""M4 公司行动处理引擎（拆股与现金分红）（T05），`CONTRACTS.md §3`。

实现正向拆股、反向合股（无损市值保值不变量）以及现金分红计入账户现金。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import structlog

from app.modules.simbroker.ports import CorporateActionFeedProtocol

logger = structlog.get_logger(__name__)

__all__ = [
    "CorporateActionsEngine",
    "CorporateActionsSummary",
    "DividendResult",
    "InvalidActionError",
    "SplitResult",
    "apply_cash_dividend",
    "apply_stock_split",
]

_DEFAULT_QUANTIZE = Decimal("0.0001")


class InvalidActionError(Exception):
    """公司行动参数非法异常。"""


@dataclass(frozen=True)
class SplitResult:
    """拆股/合股执行快照"""

    symbol: str
    split_ratio: Decimal
    qty_before: Decimal
    qty_after: Decimal
    avg_cost_before: Decimal
    avg_cost_after: Decimal
    cost_basis_before: Decimal
    cost_basis_after: Decimal
    is_reverse_split: bool


@dataclass(frozen=True)
class DividendResult:
    """现金分红派发快照"""

    symbol: str
    dividend_per_share: Decimal
    qty: Decimal
    total_dividend: Decimal
    cash_before: Decimal
    cash_after: Decimal


@dataclass(frozen=True)
class CorporateActionsSummary:
    """指定交易日全账户公司行动执行汇总"""

    trade_date: date
    splits: list[SplitResult] = field(default_factory=list)
    dividends: list[DividendResult] = field(default_factory=list)
    total_dividend_cash: Decimal = Decimal("0.0000")


def apply_stock_split(
    position: Any,
    split_ratio: Decimal,
    quantize_places: Decimal | None = _DEFAULT_QUANTIZE,
) -> SplitResult:
    """对单个持仓执行股票拆股或合股。

    不变量：拆股保值不变量（持仓成本总额在拆股前后保持恒等）。
    - 正向拆股（split_ratio > 1，例如 2:1 ratio=2）：股数增加，单股成本降低
    - 反向合股（split_ratio < 1，例如 1:4 ratio=0.25）：股数减少，单股成本提升
    """
    if split_ratio <= Decimal("0"):
        raise InvalidActionError(f"Split ratio must be positive, got {split_ratio}")

    qty_before = position.qty
    avg_cost_before = position.avg_cost

    cost_basis_before = qty_before * avg_cost_before

    raw_qty_after = qty_before * split_ratio
    raw_cost_after = avg_cost_before / split_ratio if split_ratio > 0 else Decimal("0")

    if quantize_places is not None:
        qty_after = raw_qty_after.quantize(quantize_places, rounding=ROUND_HALF_UP)
        avg_cost_after = raw_cost_after.quantize(quantize_places, rounding=ROUND_HALF_UP)
        cost_basis_before = cost_basis_before.quantize(quantize_places, rounding=ROUND_HALF_UP)
        cost_basis_after = (qty_after * avg_cost_after).quantize(
            quantize_places, rounding=ROUND_HALF_UP
        )
    else:
        qty_after = raw_qty_after
        avg_cost_after = raw_cost_after
        cost_basis_after = qty_after * avg_cost_after

    position.qty = qty_after
    position.avg_cost = avg_cost_after

    is_reverse = split_ratio < Decimal("1.0")

    logger.info(
        "Applied stock split",
        symbol=position.symbol,
        split_ratio=str(split_ratio),
        qty_before=str(qty_before),
        qty_after=str(qty_after),
        cost_before=str(avg_cost_before),
        cost_after=str(avg_cost_after),
        is_reverse=is_reverse,
    )

    return SplitResult(
        symbol=position.symbol,
        split_ratio=split_ratio,
        qty_before=qty_before,
        qty_after=qty_after,
        avg_cost_before=avg_cost_before,
        avg_cost_after=avg_cost_after,
        cost_basis_before=cost_basis_before,
        cost_basis_after=cost_basis_after,
        is_reverse_split=is_reverse,
    )


def apply_cash_dividend(
    account: Any,
    position: Any,
    dividend_per_share: Decimal,
    quantize_places: Decimal | None = _DEFAULT_QUANTIZE,
) -> DividendResult:
    """对单个持仓按每股派息发放现金分红。

    逻辑：
    total_dividend = position.qty * dividend_per_share
    account.cash += total_dividend
    """
    if dividend_per_share <= Decimal("0"):
        raise InvalidActionError(f"Dividend per share must be positive, got {dividend_per_share}")

    qty = position.qty
    if qty <= Decimal("0"):
        return DividendResult(
            symbol=position.symbol,
            dividend_per_share=dividend_per_share,
            qty=Decimal("0.0000"),
            total_dividend=Decimal("0.0000"),
            cash_before=account.cash,
            cash_after=account.cash,
        )

    raw_dividend = qty * dividend_per_share
    if quantize_places is not None:
        total_dividend = raw_dividend.quantize(quantize_places, rounding=ROUND_HALF_UP)
        cash_before = account.cash
        cash_after = (cash_before + total_dividend).quantize(
            quantize_places, rounding=ROUND_HALF_UP
        )
    else:
        total_dividend = raw_dividend
        cash_before = account.cash
        cash_after = cash_before + total_dividend

    account.cash = cash_after

    logger.info(
        "Applied cash dividend",
        symbol=position.symbol,
        dividend_per_share=str(dividend_per_share),
        qty=str(qty),
        total_dividend=str(total_dividend),
        cash_after=str(cash_after),
    )

    return DividendResult(
        symbol=position.symbol,
        dividend_per_share=dividend_per_share,
        qty=qty,
        total_dividend=total_dividend,
        cash_before=cash_before,
        cash_after=cash_after,
    )


class CorporateActionsEngine:
    """公司行动自动化批处理引擎。"""

    def __init__(self, quantize_places: Decimal | None = _DEFAULT_QUANTIZE) -> None:
        self.quantize_places = quantize_places

    def process_actions_for_account(
        self,
        account: Any,
        positions: Sequence[Any],
        trade_date: date,
        feed: CorporateActionFeedProtocol,
    ) -> CorporateActionsSummary:
        """针对指定账户在给定期日执行所有公司行动（先拆股后分红）。"""
        splits: list[SplitResult] = []
        dividends: list[DividendResult] = []
        total_div_cash = Decimal("0.0000")

        for pos in positions:
            if pos.qty <= Decimal("0"):
                continue

            # 1. 拆股检查
            split_ratio = feed.get_split_ratio(pos.symbol, trade_date)
            if split_ratio is not None and split_ratio != Decimal("1.0"):
                res_split = apply_stock_split(
                    position=pos,
                    split_ratio=split_ratio,
                    quantize_places=self.quantize_places,
                )
                splits.append(res_split)

            # 2. 现金分红检查（按拆股调整后的最新持仓数量派发）
            div_per_share = feed.get_dividend_per_share(pos.symbol, trade_date)
            if div_per_share is not None and div_per_share > Decimal("0"):
                res_div = apply_cash_dividend(
                    account=account,
                    position=pos,
                    dividend_per_share=div_per_share,
                    quantize_places=self.quantize_places,
                )
                dividends.append(res_div)
                total_div_cash += res_div.total_dividend

        if self.quantize_places is not None:
            total_div_cash = total_div_cash.quantize(self.quantize_places, rounding=ROUND_HALF_UP)

        return CorporateActionsSummary(
            trade_date=trade_date,
            splits=splits,
            dividends=dividends,
            total_dividend_cash=total_div_cash,
        )
