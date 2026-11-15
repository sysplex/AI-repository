"""M8 策略筛选引擎与容错并发执行器（ScreenerExecutor），`CONTRACTS.md §3`。

实现股票池多标的并发策略评估、单标的异常隔离与故障容错、确定性排序与信号过滤。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog

from app.modules.screener.exceptions import ScreenerExecutionError, StrategyNotFoundError
from app.modules.screener.ports import (
    MarketDataServiceProtocol,
    ScreenerExecutorProtocol,
    StrategyServiceProtocol,
)
from app.modules.screener.schemas import ScreenerResultItem

logger = structlog.get_logger(__name__)

__all__ = [
    "ScreenerExecutor",
]


class ScreenerExecutor(ScreenerExecutorProtocol):
    """策略筛选引擎执行器。

    支持：
    - 基于 asyncio.Semaphore 的多标的并发受控评估
    - 单标的异常捕获与隔离，失败项记录不阻断整体流程
    - 按分值 (score) 降序、代码 (symbol) 升序的 100% 确定性排序
    - 灵活的信号 (signal)、最低分 (min_score) 与平盘 (include_flat) 过滤
    """

    def __init__(
        self,
        strategy_service: StrategyServiceProtocol | Any = None,
        data_service: MarketDataServiceProtocol | Any = None,
        default_concurrency: int = 20,
    ) -> None:
        self._strategy_service = strategy_service
        self._data_service = data_service
        self._default_concurrency = max(1, min(default_concurrency, 100))

    async def execute_screening(
        self,
        strategy_id: str,
        symbols: list[str],
        params: dict[str, Any],
        as_of: datetime | None = None,
    ) -> tuple[list[ScreenerResultItem], list[dict[str, Any]]]:
        """对股票池中的所有标的执行并发筛选评估。

        返回 (matched_results, failed_items) 元组。
        """
        if not strategy_id or not strategy_id.strip():
            raise StrategyNotFoundError("未指定有效的策略标识符")

        if self._strategy_service is None:
            raise ScreenerExecutionError("策略分析服务未注入配置")

        clean_symbols = list(dict.fromkeys(s.strip().upper() for s in symbols if s.strip()))
        if not clean_symbols:
            return [], []

        # 并发控制
        concurrency = int(params.get("concurrency", self._default_concurrency))
        concurrency = max(1, min(concurrency, 100))
        semaphore = asyncio.Semaphore(concurrency)

        # 评估日期处理
        if as_of is None:
            target_date = datetime.now(UTC).date()
        elif isinstance(as_of, datetime):
            target_date = as_of.date()
        else:
            target_date = as_of

        logger.info(
            "screener_screening_started",
            strategy_id=strategy_id,
            total_symbols=len(clean_symbols),
            concurrency=concurrency,
            target_date=str(target_date),
        )

        async def _evaluate_single(
            sym: str,
        ) -> tuple[str, Any | None, dict[str, Any] | None]:
            async with semaphore:
                try:
                    if hasattr(self._strategy_service, "evaluate"):
                        sig = await self._strategy_service.evaluate(
                            strategy_id=strategy_id,
                            symbol=sym,
                            as_of=target_date,
                            params=params,
                        )
                    elif hasattr(self._strategy_service, "run_strategy"):
                        sig = await self._strategy_service.run_strategy(
                            strategy_id=strategy_id,
                            symbol=sym,
                            params=params,
                            as_of=as_of,
                        )
                    else:
                        raise ScreenerExecutionError("策略分析服务未提供可用的评估方法")
                    return sym, sig, None
                except Exception as exc:
                    logger.warning(
                        "screener_symbol_evaluation_failed",
                        strategy_id=strategy_id,
                        symbol=sym,
                        error=str(exc),
                        error_type=exc.__class__.__name__,
                    )
                    return (
                        sym,
                        None,
                        {
                            "symbol": sym,
                            "error": str(exc),
                            "error_type": exc.__class__.__name__,
                        },
                    )

        tasks = [_evaluate_single(s) for s in clean_symbols]
        raw_evaluations = await asyncio.gather(*tasks)

        # 候选收集与过滤
        candidates: list[tuple[Decimal, str, str, dict[str, Any]]] = []
        failed_items: list[dict[str, Any]] = []

        min_score = Decimal(str(params["min_score"])) if "min_score" in params else None
        signal_filter = params.get("signal")
        include_flat = bool(params.get("include_flat", False))

        for sym, sig, err in raw_evaluations:
            if err is not None:
                failed_items.append(err)
                continue

            # 提取强度与得分
            strength_raw = (
                getattr(sig, "strength", None) if not isinstance(sig, dict) else sig.get("strength")
            )
            score_raw = (
                getattr(sig, "score", None) if not isinstance(sig, dict) else sig.get("score")
            )
            if score_raw is not None:
                score = Decimal(str(score_raw)).quantize(Decimal("0.0001"))
            elif strength_raw is not None:
                score = Decimal(str(strength_raw)).quantize(Decimal("0.0001"))
            else:
                score = Decimal("0.0000")

            # 提取方向与信号
            direction_raw = (
                getattr(sig, "direction", None)
                if not isinstance(sig, dict)
                else sig.get("direction")
            )
            sig_raw = (
                getattr(sig, "signal", None) if not isinstance(sig, dict) else sig.get("signal")
            )

            raw_str = (sig_raw or direction_raw or "neutral").lower()
            if raw_str in ("long", "buy", "strong_buy"):
                signal = (
                    "STRONG_BUY" if score >= Decimal("80") or raw_str == "strong_buy" else "BUY"
                )
            elif raw_str in ("short", "sell", "strong_sell"):
                signal = (
                    "STRONG_SELL" if score >= Decimal("80") or raw_str == "strong_sell" else "SELL"
                )
            else:
                signal = "NEUTRAL"

            # 提取指标快照
            metrics_raw = (
                getattr(sig, "metrics", None) if not isinstance(sig, dict) else sig.get("metrics")
            )
            metrics_snapshot: dict[str, Any] = dict(metrics_raw) if metrics_raw else {}

            # 过滤逻辑
            if not include_flat and signal == "NEUTRAL" and signal_filter != "NEUTRAL":
                continue

            if min_score is not None and score < min_score:
                continue

            if signal_filter:
                if isinstance(signal_filter, str) and signal != signal_filter.upper():
                    continue
                if isinstance(signal_filter, list) and signal not in [
                    s.upper() for s in signal_filter
                ]:
                    continue

            candidates.append((score, sym, signal, metrics_snapshot))

        # 确定性排序：分值降序，标的代码升序
        candidates.sort(key=lambda x: (-x[0], x[1]))

        # 可选最大返回标的数量限制
        if "max_results" in params and params["max_results"] is not None:
            max_limit = int(params["max_results"])
            if max_limit > 0:
                candidates = candidates[:max_limit]

        # 构造最终结果与分配排名
        results = [
            ScreenerResultItem(
                symbol=sym,
                rank=idx + 1,
                score=score,
                signal=sig_str,
                metrics_snapshot=metrics,
            )
            for idx, (score, sym, sig_str, metrics) in enumerate(candidates)
        ]

        logger.info(
            "screener_screening_completed",
            strategy_id=strategy_id,
            total_symbols=len(clean_symbols),
            matched_count=len(results),
            failed_count=len(failed_items),
        )

        return results, failed_items
