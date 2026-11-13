"""Fundamental quantitative screening strategies (M3 / T04).

Implements:
- ValueBasicStrategy: Low PE, low PB, high ROE, healthy balance sheet.
- GrowthBasicStrategy: High net margin, high ROE, reasonable forward PE, controlled debt.
- DividendBasicStrategy: High dividend yield, consistent profitability, modest PE, low leverage.

Strictly decoupled from marketdata.models.Fundamentals via protocol duck-typing.
Defensive against missing fields: explicitly reports missing_fields without hallucination.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from app.modules.strategy.ports import Strategy
from app.modules.strategy.registry import register_strategy
from app.modules.strategy.schemas import Signal, StrategyContext


@runtime_checkable
class FundamentalsLike(Protocol):
    """Protocol for fundamental valuation and financial metrics."""

    @property
    def pe_trailing(self) -> Decimal | None: ...

    @property
    def pe_forward(self) -> Decimal | None: ...

    @property
    def pb(self) -> Decimal | None: ...

    @property
    def ps(self) -> Decimal | None: ...

    @property
    def roe(self) -> Decimal | None: ...

    @property
    def net_margin(self) -> Decimal | None: ...

    @property
    def debt_to_equity(self) -> Decimal | None: ...

    @property
    def dividend_yield(self) -> Decimal | None: ...

    @property
    def market_cap(self) -> Decimal | None: ...


def _get_latest_price(ctx: StrategyContext) -> Decimal | None:
    """Helper to extract latest close price from context bars <= as_of if available."""
    if not ctx.bars:
        return None
    valid_bars = [b for b in ctx.bars if b.trade_date <= ctx.as_of]
    return valid_bars[-1].close if valid_bars else None


@register_strategy
class ValueBasicStrategy(Strategy):
    """Deep value investment strategy based on Graham / Buffett screening rules."""

    id = "value_basic"
    display_name = "经典价值选股策略"
    category = "value"
    description = (
        "价值选股策略：筛选低市盈率（PE < 20）、低市净率（PB < 3.0）、"
        "高资本回报率（ROE >= 15%）且稳健杠杆（Debt/Equity <= 1.0）的低估优质标的。"
    )
    requires = {"fundamentals"}
    default_params: dict[str, Any] = {
        "max_pe": Decimal("20.0"),
        "max_pb": Decimal("3.0"),
        "min_roe": Decimal("0.15"),
        "max_debt_to_equity": Decimal("1.0"),
    }

    def evaluate(self, ctx: StrategyContext) -> Signal:
        """Evaluate value screening rules."""
        if ctx.fundamentals is None:
            return Signal(
                strategy_id=self.id,
                symbol=ctx.symbol,
                as_of=ctx.as_of,
                direction="flat",
                strength=0,
                reasons=["missing_fundamentals: no fundamentals data provided in context"],
            )

        f: FundamentalsLike = ctx.fundamentals
        params = {**self.default_params, **ctx.params}
        max_pe = Decimal(str(params["max_pe"]))
        max_pb = Decimal(str(params["max_pb"]))
        min_roe = Decimal(str(params["min_roe"]))
        max_de = Decimal(str(params["max_debt_to_equity"]))

        # Identify effective PE (trailing preferred, fallback to forward)
        pe = f.pe_trailing if f.pe_trailing is not None else f.pe_forward
        pb = f.pb
        roe = f.roe
        de = f.debt_to_equity

        missing_fields: list[str] = []
        if pe is None:
            missing_fields.append("pe")
        if pb is None:
            missing_fields.append("pb")
        if roe is None:
            missing_fields.append("roe")
        if de is None:
            missing_fields.append("debt_to_equity")

        metrics: dict[str, Any] = {
            "pe": pe,
            "pb": pb,
            "roe": roe,
            "debt_to_equity": de,
        }

        if missing_fields or pe is None or pb is None or roe is None or de is None:
            return Signal(
                strategy_id=self.id,
                symbol=ctx.symbol,
                as_of=ctx.as_of,
                direction="flat",
                strength=0,
                reasons=[f"insufficient_data: missing required fields {sorted(missing_fields)}"],
                metrics=metrics,
            )

        pe_ok = Decimal(0) < pe <= max_pe
        pb_ok = Decimal(0) < pb <= max_pb
        roe_ok = roe >= min_roe
        de_ok = de <= max_de

        passed_reasons: list[str] = []
        failed_reasons: list[str] = []

        if pe_ok:
            passed_reasons.append(f"PE {pe} <= {max_pe}")
        else:
            failed_reasons.append(f"PE {pe} not in (0, {max_pe}]")

        if pb_ok:
            passed_reasons.append(f"PB {pb} <= {max_pb}")
        else:
            failed_reasons.append(f"PB {pb} not in (0, {max_pb}]")

        if roe_ok:
            passed_reasons.append(f"ROE {roe * Decimal(100):.1f}% >= {min_roe * Decimal(100):.1f}%")
        else:
            failed_reasons.append(f"ROE {roe * Decimal(100):.1f}% < {min_roe * Decimal(100):.1f}%")

        if de_ok:
            passed_reasons.append(f"Debt/Equity {de} <= {max_de}")
        else:
            failed_reasons.append(f"Debt/Equity {de} > {max_de}")

        if pe_ok and pb_ok and roe_ok and de_ok:
            levels: dict[str, Decimal] = {}
            price = _get_latest_price(ctx)
            if price is not None:
                levels = {
                    "entry": price,
                    "stop": price * Decimal("0.85"),
                    "target": price * Decimal("1.25"),
                }
            return Signal(
                strategy_id=self.id,
                symbol=ctx.symbol,
                as_of=ctx.as_of,
                direction="long",
                strength=85,
                reasons=passed_reasons,
                levels=levels,
                metrics=metrics,
            )

        return Signal(
            strategy_id=self.id,
            symbol=ctx.symbol,
            as_of=ctx.as_of,
            direction="flat",
            strength=0,
            reasons=failed_reasons,
            metrics=metrics,
        )


@register_strategy
class GrowthBasicStrategy(Strategy):
    """Quality growth stock screening strategy."""

    id = "growth_basic"
    display_name = "成长选股策略"
    category = "growth"
    description = (
        "成长选股策略：筛选具备高盈利能力（净利润率 >= 15%）、"
        "高资本回报率（ROE >= 18%）、合理估值（Forward PE <= 35）及健康财务杠杆的成长标的。"
    )
    requires = {"fundamentals"}
    default_params: dict[str, Any] = {
        "min_net_margin": Decimal("0.15"),
        "min_roe": Decimal("0.18"),
        "max_pe_forward": Decimal("35.0"),
        "max_debt_to_equity": Decimal("1.5"),
    }

    def evaluate(self, ctx: StrategyContext) -> Signal:
        """Evaluate growth screening rules."""
        if ctx.fundamentals is None:
            return Signal(
                strategy_id=self.id,
                symbol=ctx.symbol,
                as_of=ctx.as_of,
                direction="flat",
                strength=0,
                reasons=["missing_fundamentals: no fundamentals data provided in context"],
            )

        f: FundamentalsLike = ctx.fundamentals
        params = {**self.default_params, **ctx.params}
        min_nm = Decimal(str(params["min_net_margin"]))
        min_roe = Decimal(str(params["min_roe"]))
        max_pe_fwd = Decimal(str(params["max_pe_forward"]))
        max_de = Decimal(str(params["max_debt_to_equity"]))

        nm = f.net_margin
        roe = f.roe
        pe_fwd = f.pe_forward if f.pe_forward is not None else f.pe_trailing
        de = f.debt_to_equity

        missing_fields: list[str] = []
        if nm is None:
            missing_fields.append("net_margin")
        if roe is None:
            missing_fields.append("roe")
        if pe_fwd is None:
            missing_fields.append("pe_forward")
        if de is None:
            missing_fields.append("debt_to_equity")

        metrics: dict[str, Any] = {
            "net_margin": nm,
            "roe": roe,
            "pe_forward": pe_fwd,
            "debt_to_equity": de,
        }

        if missing_fields or nm is None or roe is None or pe_fwd is None or de is None:
            return Signal(
                strategy_id=self.id,
                symbol=ctx.symbol,
                as_of=ctx.as_of,
                direction="flat",
                strength=0,
                reasons=[f"insufficient_data: missing required fields {sorted(missing_fields)}"],
                metrics=metrics,
            )

        nm_ok = nm >= min_nm
        roe_ok = roe >= min_roe
        pe_ok = Decimal(0) < pe_fwd <= max_pe_fwd
        de_ok = de <= max_de

        passed_reasons: list[str] = []
        failed_reasons: list[str] = []

        if nm_ok:
            passed_reasons.append(
                f"Net Margin {nm * Decimal(100):.1f}% >= {min_nm * Decimal(100):.1f}%"
            )
        else:
            failed_reasons.append(
                f"Net Margin {nm * Decimal(100):.1f}% < {min_nm * Decimal(100):.1f}%"
            )

        if roe_ok:
            passed_reasons.append(f"ROE {roe * Decimal(100):.1f}% >= {min_roe * Decimal(100):.1f}%")
        else:
            failed_reasons.append(f"ROE {roe * Decimal(100):.1f}% < {min_roe * Decimal(100):.1f}%")

        if pe_ok:
            passed_reasons.append(f"Forward PE {pe_fwd} <= {max_pe_fwd}")
        else:
            failed_reasons.append(f"Forward PE {pe_fwd} not in (0, {max_pe_fwd}]")

        if de_ok:
            passed_reasons.append(f"Debt/Equity {de} <= {max_de}")
        else:
            failed_reasons.append(f"Debt/Equity {de} > {max_de}")

        if nm_ok and roe_ok and pe_ok and de_ok:
            levels: dict[str, Decimal] = {}
            price = _get_latest_price(ctx)
            if price is not None:
                levels = {
                    "entry": price,
                    "stop": price * Decimal("0.88"),
                    "target": price * Decimal("1.30"),
                }
            return Signal(
                strategy_id=self.id,
                symbol=ctx.symbol,
                as_of=ctx.as_of,
                direction="long",
                strength=80,
                reasons=passed_reasons,
                levels=levels,
                metrics=metrics,
            )

        return Signal(
            strategy_id=self.id,
            symbol=ctx.symbol,
            as_of=ctx.as_of,
            direction="flat",
            strength=0,
            reasons=failed_reasons,
            metrics=metrics,
        )


@register_strategy
class DividendBasicStrategy(Strategy):
    """High-dividend yield and defensive income strategy."""

    id = "dividend_basic"
    display_name = "高股息红利选股策略"
    category = "dividend"
    description = (
        "红利选股策略：筛选具备高股息率（Dividend Yield >= 3.0%）、"
        "健康稳健盈利（ROE >= 10%）、适中估值（PE <= 25）且低杠杆（Debt/Equity <= 1.2）的收息标的。"
    )
    requires = {"fundamentals"}
    default_params: dict[str, Any] = {
        "min_dividend_yield": Decimal("0.03"),
        "min_roe": Decimal("0.10"),
        "max_pe": Decimal("25.0"),
        "max_debt_to_equity": Decimal("1.2"),
    }

    def evaluate(self, ctx: StrategyContext) -> Signal:
        """Evaluate dividend screening rules."""
        if ctx.fundamentals is None:
            return Signal(
                strategy_id=self.id,
                symbol=ctx.symbol,
                as_of=ctx.as_of,
                direction="flat",
                strength=0,
                reasons=["missing_fundamentals: no fundamentals data provided in context"],
            )

        f: FundamentalsLike = ctx.fundamentals
        params = {**self.default_params, **ctx.params}
        min_dy = Decimal(str(params["min_dividend_yield"]))
        min_roe = Decimal(str(params["min_roe"]))
        max_pe = Decimal(str(params["max_pe"]))
        max_de = Decimal(str(params["max_debt_to_equity"]))

        dy = f.dividend_yield
        roe = f.roe
        pe = f.pe_trailing if f.pe_trailing is not None else f.pe_forward
        de = f.debt_to_equity

        missing_fields: list[str] = []
        if dy is None:
            missing_fields.append("dividend_yield")
        if roe is None:
            missing_fields.append("roe")
        if pe is None:
            missing_fields.append("pe")
        if de is None:
            missing_fields.append("debt_to_equity")

        metrics: dict[str, Any] = {
            "dividend_yield": dy,
            "roe": roe,
            "pe": pe,
            "debt_to_equity": de,
        }

        if missing_fields or dy is None or roe is None or pe is None or de is None:
            return Signal(
                strategy_id=self.id,
                symbol=ctx.symbol,
                as_of=ctx.as_of,
                direction="flat",
                strength=0,
                reasons=[f"insufficient_data: missing required fields {sorted(missing_fields)}"],
                metrics=metrics,
            )

        dy_ok = dy >= min_dy
        roe_ok = roe >= min_roe
        pe_ok = Decimal(0) < pe <= max_pe
        de_ok = de <= max_de

        passed_reasons: list[str] = []
        failed_reasons: list[str] = []

        if dy_ok:
            passed_reasons.append(
                f"Dividend Yield {dy * Decimal(100):.2f}% >= {min_dy * Decimal(100):.2f}%"
            )
        else:
            failed_reasons.append(
                f"Dividend Yield {dy * Decimal(100):.2f}% < {min_dy * Decimal(100):.2f}%"
            )

        if roe_ok:
            passed_reasons.append(f"ROE {roe * Decimal(100):.1f}% >= {min_roe * Decimal(100):.1f}%")
        else:
            failed_reasons.append(f"ROE {roe * Decimal(100):.1f}% < {min_roe * Decimal(100):.1f}%")

        if pe_ok:
            passed_reasons.append(f"PE {pe} <= {max_pe}")
        else:
            failed_reasons.append(f"PE {pe} not in (0, {max_pe}]")

        if de_ok:
            passed_reasons.append(f"Debt/Equity {de} <= {max_de}")
        else:
            failed_reasons.append(f"Debt/Equity {de} > {max_de}")

        if dy_ok and roe_ok and pe_ok and de_ok:
            levels: dict[str, Decimal] = {}
            price = _get_latest_price(ctx)
            if price is not None:
                levels = {
                    "entry": price,
                    "stop": price * Decimal("0.90"),
                    "target": price * Decimal("1.20"),
                }
            return Signal(
                strategy_id=self.id,
                symbol=ctx.symbol,
                as_of=ctx.as_of,
                direction="long",
                strength=80,
                reasons=passed_reasons,
                levels=levels,
                metrics=metrics,
            )

        return Signal(
            strategy_id=self.id,
            symbol=ctx.symbol,
            as_of=ctx.as_of,
            direction="flat",
            strength=0,
            reasons=failed_reasons,
            metrics=metrics,
        )
