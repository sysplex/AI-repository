"""M8-T03 策略筛选执行器（ScreenerExecutor）单元测试。

测试覆盖：
- 批量标的并发扫描与评估
- 100% 确定性排序：分值降序，相同分值按股票代码字典序升序
- 单标的异常捕获与隔离（Fault Tolerance）：部分标的抛错不中断整体批次
- 信号过滤 (signal)、最低分过滤 (min_score)、平盘过滤 (include_flat) 与数量截断 (max_results)
- 并发度限制 (asyncio.Semaphore) 控制
- 边界条件与异常防御 (StrategyNotFoundError, ScreenerExecutionError)
- ScreenerExecutorProtocol 协议一致性
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.modules.screener.exceptions import ScreenerExecutionError, StrategyNotFoundError
from app.modules.screener.executor import ScreenerExecutor
from app.modules.screener.ports import ScreenerExecutorProtocol
from app.modules.strategy.schemas import Signal


class MockStrategyService:
    """可配置的策略评估服务模拟对象。"""

    def __init__(
        self,
        signals_map: dict[str, Any] | None = None,
        fail_symbols: set[str] | None = None,
        delay_seconds: float = 0.0,
    ) -> None:
        self.signals_map = signals_map or {}
        self.fail_symbols = fail_symbols or set()
        self.delay_seconds = delay_seconds
        self.max_concurrent_seen = 0
        self.current_concurrent = 0
        self._lock = asyncio.Lock()

    def list_strategies(self) -> list[Any]:
        return []

    async def evaluate(
        self,
        strategy_id: str,
        symbol: str,
        as_of: Any,
        params: dict[str, Any] | None = None,
    ) -> Any:
        async with self._lock:
            self.current_concurrent += 1
            if self.current_concurrent > self.max_concurrent_seen:
                self.max_concurrent_seen = self.current_concurrent

        try:
            if self.delay_seconds > 0:
                await asyncio.sleep(self.delay_seconds)

            if symbol in self.fail_symbols:
                raise ValueError(f"行情缺失或计算异常: {symbol}")

            if symbol in self.signals_map:
                return self.signals_map[symbol]

            # 默认生成普通多头信号
            return Signal(
                strategy_id=strategy_id,
                symbol=symbol,
                as_of=as_of if isinstance(as_of, date) else date(2026, 11, 15),
                direction="long",
                strength=75,
                reasons=["均线多头排列"],
                metrics={"rsi": 58.5, "pe": 25.0},
            )
        finally:
            async with self._lock:
                self.current_concurrent -= 1


# ==============================================================================
# 1. 确定性排序与综合排名测试
# ==============================================================================
@pytest.mark.asyncio
async def test_screener_deterministic_sorting_and_ranking() -> None:
    # 构造标的得分：
    # NVDA: 95.0000 -> rank 1
    # AAPL: 88.0000 -> rank 2 (与 MSFT 同分，AAPL 字母序在前)
    # MSFT: 88.0000 -> rank 3
    # GOOG: 80.0000 -> rank 4
    # TSLA: 65.0000 -> rank 5
    signals_map = {
        "NVDA": Signal(
            strategy_id="trend",
            symbol="NVDA",
            as_of=date(2026, 11, 15),
            direction="long",
            strength=95,
            metrics={"momentum": 95},
        ),
        "MSFT": Signal(
            strategy_id="trend",
            symbol="MSFT",
            as_of=date(2026, 11, 15),
            direction="long",
            strength=88,
            metrics={"momentum": 88},
        ),
        "AAPL": Signal(
            strategy_id="trend",
            symbol="AAPL",
            as_of=date(2026, 11, 15),
            direction="long",
            strength=88,
            metrics={"momentum": 88},
        ),
        "GOOG": Signal(
            strategy_id="trend",
            symbol="GOOG",
            as_of=date(2026, 11, 15),
            direction="long",
            strength=80,
            metrics={"momentum": 80},
        ),
        "TSLA": Signal(
            strategy_id="trend",
            symbol="TSLA",
            as_of=date(2026, 11, 15),
            direction="long",
            strength=65,
            metrics={"momentum": 65},
        ),
    }

    mock_service = MockStrategyService(signals_map=signals_map)
    executor = ScreenerExecutor(strategy_service=mock_service)

    results, failed = await executor.execute_screening(
        strategy_id="trend",
        symbols=["TSLA", "MSFT", "GOOG", "NVDA", "AAPL"],
        params={},
    )

    assert len(failed) == 0
    assert len(results) == 5

    # 验证确定性排名
    assert [r.symbol for r in results] == ["NVDA", "AAPL", "MSFT", "GOOG", "TSLA"]
    assert [r.rank for r in results] == [1, 2, 3, 4, 5]

    # 验证分值与信号映射
    assert results[0].score == Decimal("95.0000")
    assert results[0].signal == "STRONG_BUY"  # >= 80 为 STRONG_BUY
    assert results[1].score == Decimal("88.0000")
    assert results[1].signal == "STRONG_BUY"
    assert results[4].score == Decimal("65.0000")
    assert results[4].signal == "BUY"


# ==============================================================================
# 2. 单标的异常隔离容错测试 (Fault Tolerance)
# ==============================================================================
@pytest.mark.asyncio
async def test_screener_single_symbol_fault_isolation() -> None:
    symbols = ["AAPL", "FAIL_1", "MSFT", "FAIL_2", "NVDA", "FAIL_3"]
    fail_symbols = {"FAIL_1", "FAIL_2", "FAIL_3"}

    mock_service = MockStrategyService(fail_symbols=fail_symbols)
    executor = ScreenerExecutor(strategy_service=mock_service)

    results, failed = await executor.execute_screening(
        strategy_id="trend",
        symbols=symbols,
        params={},
    )

    # 验证整体批次未抛错崩溃
    assert len(results) == 3
    assert len(failed) == 3

    # 成功项正常排序赋排名
    assert {r.symbol for r in results} == {"AAPL", "MSFT", "NVDA"}
    assert [r.rank for r in results] == [1, 2, 3]

    # 失败项完整捕获明细
    failed_symbols = {f["symbol"] for f in failed}
    assert failed_symbols == fail_symbols
    for f in failed:
        assert "error" in f
        assert f["error_type"] == "ValueError"


# ==============================================================================
# 3. 过滤规则测试 (min_score, include_flat, signal, max_results)
# ==============================================================================
@pytest.mark.asyncio
async def test_screener_filtering_rules() -> None:
    signals_map = {
        "A": Signal(
            strategy_id="t",
            symbol="A",
            as_of=date(2026, 11, 15),
            direction="long",
            strength=90,
        ),
        "B": Signal(
            strategy_id="t",
            symbol="B",
            as_of=date(2026, 11, 15),
            direction="long",
            strength=70,
        ),
        "C": Signal(
            strategy_id="t",
            symbol="C",
            as_of=date(2026, 11, 15),
            direction="flat",
            strength=50,
        ),
        "D": Signal(
            strategy_id="t",
            symbol="D",
            as_of=date(2026, 11, 15),
            direction="short",
            strength=85,
        ),
    }
    mock_service = MockStrategyService(signals_map=signals_map)
    executor = ScreenerExecutor(strategy_service=mock_service)

    # 1. 默认 include_flat=False：平盘 (C) 被过滤
    r1, _ = await executor.execute_screening(
        strategy_id="t", symbols=["A", "B", "C", "D"], params={}
    )
    assert {r.symbol for r in r1} == {"A", "B", "D"}

    # 2. include_flat=True：平盘 (C) 被保留
    r2, _ = await executor.execute_screening(
        strategy_id="t", symbols=["A", "B", "C", "D"], params={"include_flat": True}
    )
    assert {r.symbol for r in r2} == {"A", "B", "C", "D"}
    c_res = [r for r in r2 if r.symbol == "C"][0]
    assert c_res.signal == "NEUTRAL"

    # 3. min_score 过滤：仅保留 >= 80 分
    r3, _ = await executor.execute_screening(
        strategy_id="t",
        symbols=["A", "B", "C", "D"],
        params={"min_score": 80, "include_flat": True},
    )
    assert {r.symbol for r in r3} == {"A", "D"}

    # 4. signal 过滤：仅保留 STRONG_BUY，并测试 list 过滤
    r4, _ = await executor.execute_screening(
        strategy_id="t",
        symbols=["A", "B", "C", "D"],
        params={"signal": "STRONG_BUY", "include_flat": True},
    )
    assert {r.symbol for r in r4} == {"A"}

    r4_list, _ = await executor.execute_screening(
        strategy_id="t",
        symbols=["A", "B", "C", "D"],
        params={"signal": ["BUY", "STRONG_BUY"], "include_flat": True},
    )
    assert {r.symbol for r in r4_list} == {"A", "B"}

    # 5. max_results 截断：仅保留前 1 名
    r5, _ = await executor.execute_screening(
        strategy_id="t",
        symbols=["A", "B", "C", "D"],
        params={"max_results": 1, "include_flat": True},
    )
    assert len(r5) == 1
    assert r5[0].symbol == "A"
    assert r5[0].rank == 1


# ==============================================================================
# 4. 并发控制 (asyncio.Semaphore) 测试
# ==============================================================================
@pytest.mark.asyncio
async def test_screener_concurrency_control() -> None:
    # 模拟 15 个标的，设置并发度为 3
    symbols = [f"SYM_{i}" for i in range(15)]
    mock_service = MockStrategyService(delay_seconds=0.02)
    executor = ScreenerExecutor(strategy_service=mock_service, default_concurrency=3)

    results, failed = await executor.execute_screening(
        strategy_id="t",
        symbols=symbols,
        params={"concurrency": 3},
    )
    assert len(results) == 15
    assert len(failed) == 0
    # 最大瞬时并发度不得超过设定的 3
    assert mock_service.max_concurrent_seen <= 3


# ==============================================================================
# 5. 日期处理与异常防御测试
# ==============================================================================
@pytest.mark.asyncio
async def test_screener_date_handling_and_validation() -> None:
    mock_service = MockStrategyService()
    executor = ScreenerExecutor(strategy_service=mock_service)

    # 1. 传入 datetime 对象
    now = datetime(2026, 11, 10, 15, 30, tzinfo=UTC)
    res_dt, _ = await executor.execute_screening(
        strategy_id="t", symbols=["AAPL"], params={}, as_of=now
    )
    assert len(res_dt) == 1

    # 2. 传入空股票列表
    empty_res, empty_failed = await executor.execute_screening(
        strategy_id="t", symbols=[], params={}
    )
    assert empty_res == []
    assert empty_failed == []

    # 3. 未传策略 ID 异常拦截
    with pytest.raises(StrategyNotFoundError):
        await executor.execute_screening(strategy_id="", symbols=["AAPL"], params={})

    # 4. 未注入服务实例异常拦截
    executor_uninit = ScreenerExecutor(strategy_service=None)
    with pytest.raises(ScreenerExecutionError):
        await executor_uninit.execute_screening(strategy_id="t", symbols=["AAPL"], params={})


# ==============================================================================
# 6. run_strategy 降级与字典信号结构测试
# ==============================================================================
@pytest.mark.asyncio
async def test_screener_run_strategy_fallback_and_dict_signals() -> None:
    class FallbackStrategyService:
        async def run_strategy(
            self,
            strategy_id: str,
            symbol: str,
            params: dict[str, Any] | None = None,
            as_of: datetime | None = None,
        ) -> dict[str, Any]:
            if symbol == "UNKNOWN_SCORE":
                return {"signal": "NEUTRAL"}
            return {
                "symbol": symbol,
                "score": 92.5,
                "signal": "STRONG_BUY",
                "metrics": {"pe": 20.0},
            }

    executor = ScreenerExecutor(strategy_service=FallbackStrategyService())
    results, failed = await executor.execute_screening(
        strategy_id="strat_fallback",
        symbols=["AAPL", "UNKNOWN_SCORE"],
        params={"include_flat": True},
    )
    assert len(results) == 2
    assert len(failed) == 0
    assert results[0].symbol == "AAPL"
    assert results[0].score == Decimal("92.5000")
    assert results[1].symbol == "UNKNOWN_SCORE"
    assert results[1].score == Decimal("0.0000")


@pytest.mark.asyncio
async def test_screener_invalid_service_methods() -> None:
    class EmptyService:
        pass

    executor = ScreenerExecutor(strategy_service=EmptyService())
    results, failed = await executor.execute_screening(
        strategy_id="any",
        symbols=["AAPL"],
        params={},
    )
    assert len(results) == 0
    assert len(failed) == 1
    assert "未提供可用的评估方法" in failed[0]["error"]


# ==============================================================================
# 7. 协议一致性测试
# ==============================================================================
def test_screener_executor_protocol_conformance() -> None:
    executor = ScreenerExecutor()
    assert isinstance(executor, ScreenerExecutorProtocol)
