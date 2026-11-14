"""M6 AI 研究用例事实聚合器，`CONTRACTS.md §2, §3`。

实现从行情、基础资料、财报及技术分析多数据源聚合事实数据：
- ``FactAggregator``：实现 ``FactAggregatorProtocol``
- 跟踪并严密记录 ``missing_fields`` 缺失字段列表
- 联动 ``QuantitativeEngine`` 生成防编造的确定性衍生指标与交易计划
"""

from __future__ import annotations

import inspect
from decimal import Decimal
from typing import Any

from app.modules.research.exceptions import (
    InsufficientDataError,
    InvalidParameterError,
    SymbolNotFoundError,
)
from app.modules.research.ports import (
    MarketDataServiceProtocol,
    QuantitativeEngineProtocol,
    StrategyServiceProtocol,
)
from app.modules.research.quantitative import QuantitativeEngine

__all__ = [
    "FactAggregator",
    "USE_CASE_BUY_DECISION",
    "USE_CASE_EARNINGS",
    "USE_CASE_RESEARCH",
    "USE_CASE_TECHNICAL",
    "VALID_USE_CASES",
]

USE_CASE_RESEARCH = "research"
USE_CASE_BUY_DECISION = "buy_decision"
USE_CASE_TECHNICAL = "technical"
USE_CASE_EARNINGS = "earnings"

VALID_USE_CASES: frozenset[str] = frozenset(
    {
        USE_CASE_RESEARCH,
        USE_CASE_BUY_DECISION,
        USE_CASE_TECHNICAL,
        USE_CASE_EARNINGS,
    }
)


class FactAggregator:
    """多源市场事实与代码量化派生指标聚合器。

    实现 ``FactAggregatorProtocol``：
    1. 根据用例按需从数据源提取 quote, profile, fundamentals, bars, news；
    2. 从策略服务提取技术面快照与支撑阻力；
    3. 调用 ``QuantitativeEngine`` 确定性计算想买价偏差、52周区间位置与交易计划；
    4. 严密收集并追踪 ``missing_fields`` 缺失字段；
    5. 数据缺失严重或标的不存在时抛出对应业务异常。
    """

    def __init__(
        self,
        data_service: MarketDataServiceProtocol,
        strategy_service: StrategyServiceProtocol | None = None,
        quantitative_engine: QuantitativeEngineProtocol | None = None,
    ) -> None:
        self._data_service = data_service
        self._strategy_service = strategy_service
        self._quantitative_engine = quantitative_engine or QuantitativeEngine()

    async def aggregate_facts(
        self,
        symbol: str,
        use_case: str,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], list[str]]:
        """为特定用例收集结构化事实数据并返回 (facts, missing_fields)。

        Args:
            symbol: 标的代码（如 AAPL）。
            use_case: 目标用例名称（research, buy_decision, technical, earnings）。
            **kwargs: 额外上下文参数（如 target_price, horizon, risk_level, as_of 等）。

        Returns:
            tuple[dict[str, Any], list[str]]: 聚合事实字典及缺失字段列表。

        Raises:
            InvalidParameterError: 标的代码为空或用例名称不受支持。
            SymbolNotFoundError: 标的不存在或基础市场数据无法获取。
            InsufficientDataError: 关键数据严重缺失，无法支撑分析。
        """
        sym = symbol.strip().upper()
        if not sym:
            raise InvalidParameterError(
                "Symbol must not be empty",
                details={"symbol": symbol},
            )

        uc = use_case.strip().lower()
        if uc not in VALID_USE_CASES:
            raise InvalidParameterError(
                f"Unsupported use case: '{use_case}'",
                details={"use_case": use_case, "allowed": sorted(list(VALID_USE_CASES))},
            )

        # 1. 确定当前用例所需的数据范围
        scope = self._resolve_scope_for_use_case(uc)

        # 2. 从市场数据服务拉取快照
        facts, missing_fields = await self._fetch_market_facts(sym, scope)

        # 3. 校验基础数据完整性，若标的完全无行情且无资料则判定不存在
        if facts.get("quote") is None and facts.get("profile") is None:
            raise SymbolNotFoundError(
                f"Symbol '{sym}' not found or market data unavailable",
                details={"symbol": sym, "missing_fields": missing_fields},
            )

        # 4. 根据不同用例组装派生数据与专属事实
        if uc == USE_CASE_BUY_DECISION:
            await self._enrich_buy_decision(sym, facts, missing_fields, kwargs)
        elif uc == USE_CASE_TECHNICAL:
            await self._enrich_technical(sym, facts, missing_fields, kwargs)
        elif uc == USE_CASE_EARNINGS:
            self._enrich_earnings(facts, missing_fields, kwargs)
        elif uc == USE_CASE_RESEARCH:
            self._enrich_research(facts, missing_fields)

        # 5. 统一去重并排序缺失字段
        deduped_missing = sorted(list(set(missing_fields)))
        return facts, deduped_missing

    def _resolve_scope_for_use_case(self, use_case: str) -> list[str]:
        if use_case == USE_CASE_RESEARCH:
            return ["quote", "profile", "fundamentals", "bars", "news"]
        if use_case == USE_CASE_BUY_DECISION:
            return ["quote", "profile", "fundamentals", "bars"]
        if use_case == USE_CASE_TECHNICAL:
            return ["quote", "bars"]
        if use_case == USE_CASE_EARNINGS:
            return ["quote", "fundamentals", "news"]
        return ["quote", "profile", "fundamentals"]

    async def _fetch_market_facts(
        self,
        symbol: str,
        scope: list[str],
    ) -> tuple[dict[str, Any], list[str]]:
        missing_fields: list[str] = []
        facts: dict[str, Any] = {}

        # 优先使用 build_facts
        if hasattr(self._data_service, "build_facts"):
            try:
                snap = await self._data_service.build_facts(symbol, scope=scope)
                if hasattr(snap, "facts") and isinstance(snap.facts, dict):
                    facts = dict(snap.facts)
                elif isinstance(snap, dict) and "facts" in snap:
                    facts = dict(snap["facts"])
                elif isinstance(snap, dict):
                    facts = dict(snap)
                else:
                    facts = {}

                if hasattr(snap, "missing_fields"):
                    missing_fields.extend(snap.missing_fields)
                elif isinstance(snap, dict) and "missing_fields" in snap:
                    missing_fields.extend(snap["missing_fields"])
            except Exception as exc:
                # 若直接抛出异常，判定标的无法获取
                raise SymbolNotFoundError(
                    f"Symbol '{symbol}' not found: {exc}",
                    details={"symbol": symbol, "error": str(exc)},
                ) from exc
        else:
            # 兼容逐项拉取
            if "quote" in scope and hasattr(self._data_service, "get_quote"):
                try:
                    q = await self._data_service.get_quote(symbol)
                    facts["quote"] = q.model_dump(mode="json") if hasattr(q, "model_dump") else q
                except Exception:
                    facts["quote"] = None
                    missing_fields.append("quote")

            if "profile" in scope and hasattr(self._data_service, "get_profile"):
                try:
                    p = await self._data_service.get_profile(symbol)
                    facts["profile"] = p.model_dump(mode="json") if hasattr(p, "model_dump") else p
                except Exception:
                    facts["profile"] = None
                    missing_fields.append("profile")

            if "fundamentals" in scope and hasattr(self._data_service, "get_fundamentals"):
                try:
                    f = await self._data_service.get_fundamentals(symbol)
                    facts["fundamentals"] = (
                        f.model_dump(mode="json") if hasattr(f, "model_dump") else f
                    )
                except Exception:
                    facts["fundamentals"] = None
                    missing_fields.append("fundamentals")

            if "news" in scope and hasattr(self._data_service, "get_news"):
                try:
                    n = await self._data_service.get_news(symbol)
                    facts["news"] = [
                        item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                        for item in n
                    ]
                except Exception:
                    facts["news"] = []
                    missing_fields.append("news")

        # 确保 facts 字典内的模型均序列化为纯 dict
        for k in ["quote", "profile", "fundamentals"]:
            v = facts.get(k)
            if v is not None and hasattr(v, "model_dump"):
                facts[k] = v.model_dump(mode="json")

        return facts, missing_fields

    async def _enrich_buy_decision(
        self,
        symbol: str,
        facts: dict[str, Any],
        missing_fields: list[str],
        kwargs: dict[str, Any],
    ) -> None:
        quote = facts.get("quote")
        current_price_val = quote.get("price") if isinstance(quote, dict) else None
        if current_price_val is None:
            raise InsufficientDataError(
                f"Missing current price for symbol '{symbol}'",
                details={"symbol": symbol},
            )

        current_price = Decimal(str(current_price_val))

        target_price_raw = kwargs.get("target_price")
        if target_price_raw is not None:
            target_price = Decimal(str(target_price_raw))
        else:
            target_price = current_price
            missing_fields.append("target_price")

        # 52 周高低点获取：支持 kwargs 传入或由日线行情计算
        low_52w_raw = kwargs.get("low_52w")
        high_52w_raw = kwargs.get("high_52w")

        bars = facts.get("bars") or []
        if (low_52w_raw is None or high_52w_raw is None) and bars:
            try:
                low_candidates = [
                    Decimal(str(b["low"] if isinstance(b, dict) else b.low))
                    for b in bars
                    if (b.get("low") if isinstance(b, dict) else getattr(b, "low", None))
                    is not None
                ]
                high_candidates = [
                    Decimal(str(b["high"] if isinstance(b, dict) else b.high))
                    for b in bars
                    if (b.get("high") if isinstance(b, dict) else getattr(b, "high", None))
                    is not None
                ]
                if low_candidates and high_candidates:
                    low_52w_raw = min(low_candidates)
                    high_52w_raw = max(high_candidates)
            except (ValueError, TypeError, KeyError):
                low_52w_raw = None
                high_52w_raw = None

        if low_52w_raw is None or high_52w_raw is None:
            low_52w = current_price * Decimal("0.80")
            high_52w = current_price * Decimal("1.20")
            missing_fields.extend(["low_52w", "high_52w"])
        else:
            low_52w = Decimal(str(low_52w_raw))
            high_52w = Decimal(str(high_52w_raw))

        computed = self._quantitative_engine.compute_buy_decision_metrics(
            current_price=current_price,
            target_price=target_price,
            low_52w=low_52w,
            high_52w=high_52w,
        )

        facts["computed"] = {
            "current_price": current_price,
            "target_price": target_price,
            "low_52w": low_52w,
            "high_52w": high_52w,
            "target_vs_price_pct": computed["target_vs_price_pct"],
            "pos_in_52w_range": computed["pos_in_52w_range"],
        }
        facts["context"] = {
            "target_price": target_price,
            "horizon": kwargs.get("horizon", "medium"),
            "risk_level": kwargs.get("risk_level", "medium"),
        }

    async def _enrich_technical(
        self,
        symbol: str,
        facts: dict[str, Any],
        missing_fields: list[str],
        kwargs: dict[str, Any],
    ) -> None:
        quote = facts.get("quote")
        current_price_val = quote.get("price") if isinstance(quote, dict) else None
        if current_price_val is None:
            raise InsufficientDataError(
                f"Missing current price for technical analysis on symbol '{symbol}'",
                details={"symbol": symbol},
            )
        current_price = Decimal(str(current_price_val))

        snapshot: Any = None
        if self._strategy_service is not None:
            try:
                res = self._strategy_service.compute_technical_snapshot(
                    symbol, as_of=kwargs.get("as_of")
                )
                if inspect.isawaitable(res):
                    snapshot = await res
                else:
                    snapshot = res
            except Exception:
                missing_fields.append("technical_snapshot")
        else:
            missing_fields.append("technical_snapshot")

        support = getattr(snapshot, "support", None) if snapshot else None
        resistance = getattr(snapshot, "resistance", None) if snapshot else None
        atr_14 = getattr(snapshot, "atr_14", None) if snapshot else None

        supp_dec = Decimal(str(support)) if support is not None else current_price * Decimal("0.95")
        res_dec = (
            Decimal(str(resistance)) if resistance is not None else current_price * Decimal("1.05")
        )
        atr_dec = (
            Decimal(str(atr_14))
            if (atr_14 is not None and Decimal(str(atr_14)) > Decimal("0"))
            else current_price * Decimal("0.02")
        )

        if support is None:
            missing_fields.append("technical.support")
        if resistance is None:
            missing_fields.append("technical.resistance")
        if atr_14 is None:
            missing_fields.append("technical.atr_14")

        trade_plan = self._quantitative_engine.compute_technical_trade_plan(
            current_price=current_price,
            support=supp_dec,
            resistance=res_dec,
            atr=atr_dec,
        )

        facts["computed"] = {"trade_plan": trade_plan}

        facts["technical"] = {
            "sma_20": getattr(snapshot, "sma_20", None) if snapshot else None,
            "sma_50": getattr(snapshot, "sma_50", None) if snapshot else None,
            "sma_200": getattr(snapshot, "sma_200", None) if snapshot else None,
            "ema_12": getattr(snapshot, "ema_12", None) if snapshot else None,
            "ema_26": getattr(snapshot, "ema_26", None) if snapshot else None,
            "rsi_14": getattr(snapshot, "rsi_14", None) if snapshot else None,
            "macd": getattr(snapshot, "macd", None) if snapshot else None,
            "macd_signal": getattr(snapshot, "macd_signal", None) if snapshot else None,
            "macd_hist": getattr(snapshot, "macd_hist", None) if snapshot else None,
            "atr_14": atr_14,
            "bb_upper": getattr(snapshot, "bb_upper", None) if snapshot else None,
            "bb_middle": getattr(snapshot, "bb_middle", None) if snapshot else None,
            "bb_lower": getattr(snapshot, "bb_lower", None) if snapshot else None,
            "obv": getattr(snapshot, "obv", None) if snapshot else None,
            "support": support,
            "resistance": resistance,
        }

    def _enrich_earnings(
        self,
        facts: dict[str, Any],
        missing_fields: list[str],
        kwargs: dict[str, Any],
    ) -> None:
        funds = facts.get("fundamentals") or {}
        earnings_kwargs = kwargs.get("earnings") or {}

        revenue = earnings_kwargs.get("revenue")
        eps = earnings_kwargs.get("eps")
        margins = earnings_kwargs.get("margins") or funds.get("net_margin")
        guidance = earnings_kwargs.get("guidance")
        commentary = earnings_kwargs.get("management_commentary")

        if revenue is None:
            missing_fields.append("earnings.revenue")
        if eps is None:
            missing_fields.append("earnings.eps")
        if margins is None:
            missing_fields.append("earnings.margins")
        if guidance is None:
            missing_fields.append("earnings.guidance")
        if not commentary:
            missing_fields.append("earnings.management_commentary")

        facts["earnings"] = {
            "revenue": revenue,
            "eps": eps,
            "margins": margins,
            "guidance": guidance,
            "management_commentary": commentary or [],
        }

    def _enrich_research(
        self,
        facts: dict[str, Any],
        missing_fields: list[str],
    ) -> None:
        funds = facts.get("fundamentals")
        if funds is None:
            missing_fields.append("fundamentals")
        elif isinstance(funds, dict):
            for field in ["pe_trailing", "pe_forward", "roe", "net_margin", "debt_to_equity"]:
                if funds.get(field) is None:
                    missing_fields.append(f"fundamentals.{field}")

        profile = facts.get("profile")
        if profile is None:
            missing_fields.append("profile")
        elif isinstance(profile, dict):
            for field in ["sector", "industry", "description"]:
                if not profile.get(field):
                    missing_fields.append(f"profile.{field}")
