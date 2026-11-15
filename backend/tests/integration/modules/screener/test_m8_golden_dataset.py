"""M8-T07 黄金数据集大样本（500 标的池）策略筛选与多主题场景集成测试套件。

验证范围：
1. 500 标的大股票池（S&P 500 样本池 503 只）在固定历史日期（如 2026-11-10）下
   多次运行结果 100% 确定性与可复现性；
2. 500 标的大股票池 10% 异常样本注入与故障隔离机制
   （批次成功完成且 failed_count == 50，单标的异常不中断整体批次）；
3. 500 标的大股票池并发控制与执行性能基准（Semaphore 并发限制严格生效，无死锁、无任务泄漏）；
4. 多热门主题场景（AI 芯片、GLP-1 减肥药、高股息、云 SaaS、清洁能源）
   Theme Cards 端到端生成与数字事实溯源验证；
5. 防编造与防幻觉对抗测试（数字篡改与违规收益承诺拦截，确保 100% 真实事实溯源）；
6. ScreenerService 门面全链路高层集成（多租户数据落库、历史记录回读、排序与指标快照完整性）。
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.core.clock import FrozenClock
from app.modules.screener.exceptions import ScreenerError, ScreenerRunNotFoundError
from app.modules.screener.executor import ScreenerExecutor
from app.modules.screener.models import ScreenerRun
from app.modules.screener.ports import (
    ScreenerRepositoryProtocol,
    WatchlistRepositoryProtocol,
)
from app.modules.screener.prompts import (
    DEFAULT_BANNED_TERMS,
    THEME_CARD_PROMPT_VERSION,
    ThemeCardsGenerator,
)
from app.modules.screener.schemas import (
    ExportToResearchRequest,
    ScreenerRunCreate,
    ThemeCardsResponse,
)
from app.modules.screener.service import ScreenerService
from app.modules.screener.universe import (
    SP500_SYMBOLS,
    default_universe_manager,
)
from app.modules.strategy.schemas import Signal

pytestmark = pytest.mark.integration

_FIXED_DATE = date(2026, 11, 10)
_FIXED_NOW = datetime(2026, 11, 10, 16, 0, 0, tzinfo=UTC)


# =============================================================================
# 1. 500 标的大样本可复现性与确定性策略模拟器
# =============================================================================


class GoldenDeterministicStrategyService:
    """基于标的代码与日期的确定性策略服务。

    保证：对于相同 (strategy_id, symbol, as_of)，计算出的信号与指标完全恒定。
    """

    def __init__(
        self,
        fail_symbols: set[str] | None = None,
        failure_exceptions: dict[str, Exception] | None = None,
        delay_seconds: float = 0.0,
    ) -> None:
        self.fail_symbols = fail_symbols or set()
        self.failure_exceptions = failure_exceptions or {}
        self.delay_seconds = delay_seconds
        self.max_concurrent_seen = 0
        self.current_concurrent = 0
        self._lock = asyncio.Lock()
        self.call_count = 0

    def list_strategies(self) -> list[Any]:
        return []

    async def evaluate(
        self,
        strategy_id: str,
        symbol: str,
        as_of: Any,
        params: dict[str, Any] | None = None,
    ) -> Signal:
        async with self._lock:
            self.call_count += 1
            self.current_concurrent += 1
            if self.current_concurrent > self.max_concurrent_seen:
                self.max_concurrent_seen = self.current_concurrent

        try:
            if self.delay_seconds > 0:
                await asyncio.sleep(self.delay_seconds)

            if symbol in self.fail_symbols:
                exc = self.failure_exceptions.get(
                    symbol, ValueError(f"行情数据缺失或计算失败: {symbol}")
                )
                raise exc

            # 生成确定性得分与指标 (基于 SHA256 散列种子)
            seed_key = f"{strategy_id}:{symbol}:{as_of}"
            hash_val = int(hashlib.sha256(seed_key.encode("utf-8")).hexdigest(), 16)

            # 得分 1.00 ~ 99.00
            score_int = (hash_val % 9900) + 100
            strength = Decimal(score_int) / Decimal(100)

            # 确定性方向
            direction = "long" if (hash_val % 10) >= 3 else "flat"

            rsi_val = float(Decimal((hash_val % 600) + 300) / Decimal(10))
            pe_val = float(Decimal((hash_val % 500) + 100) / Decimal(10))

            return Signal(
                strategy_id=strategy_id,
                symbol=symbol,
                as_of=as_of if isinstance(as_of, date) else _FIXED_DATE,
                direction=direction,
                strength=int(strength),
                reasons=[f"突破 20 日均线 (强度 {strength})"],
                metrics={"rsi": rsi_val, "pe": pe_val, "raw_score": float(strength)},
            )
        finally:
            async with self._lock:
                self.current_concurrent -= 1


# =============================================================================
# 2. 500 标的大样本黄金测试
# =============================================================================


@pytest.mark.asyncio
async def test_golden_500_symbols_deterministic_reproducibility() -> None:
    """验证 503 只标普 500 样本在固定日期下多次运行结果 100% 确定性与可复现。"""
    symbols = default_universe_manager.get_universe_symbols("sp500")
    assert len(symbols) == len(SP500_SYMBOLS)
    assert len(symbols) >= 500

    strategy_service = GoldenDeterministicStrategyService()
    executor = ScreenerExecutor(strategy_service=strategy_service, default_concurrency=25)

    params = {"min_score": 40.0, "signal": "BUY", "include_flat": False}

    # 第一次运行
    results1, failed1 = await executor.execute_screening(
        strategy_id="momentum_golden",
        symbols=symbols,
        params=params,
        as_of=_FIXED_NOW,
    )

    # 第二次运行（完全相同参数）
    results2, failed2 = await executor.execute_screening(
        strategy_id="momentum_golden",
        symbols=symbols,
        params=params,
        as_of=_FIXED_NOW,
    )

    # 1. 基础统计完全一致
    assert len(failed1) == 0
    assert len(failed2) == 0
    assert len(results1) == len(results2)
    assert len(results1) > 0

    # 2. 排名与分值逐项 100% 精确匹配
    for idx, (res1, res2) in enumerate(zip(results1, results2, strict=True)):
        assert res1.rank == idx + 1
        assert res2.rank == idx + 1
        assert res1.symbol == res2.symbol
        assert res1.score == res2.score
        assert res1.signal == res2.signal
        assert res1.metrics_snapshot == res2.metrics_snapshot

    # 3. 验证确定性排序规则：分值降序；分值相同时代码升序
    for i in range(len(results1) - 1):
        curr = results1[i]
        nxt = results1[i + 1]
        assert curr.score >= nxt.score
        if curr.score == nxt.score:
            assert curr.symbol < nxt.symbol


@pytest.mark.asyncio
async def test_golden_500_symbols_fault_isolation_matrix() -> None:
    """验证注入 10% 异常样本（50 只故障标的）时的单标的故障隔离机制。"""
    symbols = default_universe_manager.get_universe_symbols("sp500")

    # 选定恰好 50 只作为故障样本（约 10%）
    failing_symbols = set(symbols[::10][:50])
    assert len(failing_symbols) == 50

    # 为不同标的注入不同类型的异常模式
    failure_map: dict[str, Exception] = {}
    failing_list = list(failing_symbols)
    for i, sym in enumerate(failing_list):
        mod = i % 5
        if mod == 0:
            failure_map[sym] = TimeoutError(f"行情拉取超时: {sym}")
        elif mod == 1:
            failure_map[sym] = ValueError(f"价格数据格式无效: {sym}")
        elif mod == 2:
            failure_map[sym] = KeyError(f"缺少财务指标 pe: {sym}")
        elif mod == 3:
            failure_map[sym] = ZeroDivisionError(f"除零错误: {sym}")
        else:
            failure_map[sym] = RuntimeError(f"策略引擎内部错误: {sym}")

    strategy_service = GoldenDeterministicStrategyService(
        fail_symbols=failing_symbols,
        failure_exceptions=failure_map,
    )
    executor = ScreenerExecutor(strategy_service=strategy_service, default_concurrency=20)

    # 执行大样本并发筛选
    results, failed_items = await executor.execute_screening(
        strategy_id="momentum_golden",
        symbols=symbols,
        params={"include_flat": True},
        as_of=_FIXED_NOW,
    )

    # 验证故障隔离：批次整体成功，50 只异常全部计入 failed_items
    assert len(failed_items) == 50
    # 正常处理的标的数为 503 - 50 = 453
    assert len(results) <= len(symbols) - 50

    # 确认故障标的绝不会污染最终有效结果列表
    result_symbols = {r.symbol for r in results}
    assert result_symbols.isdisjoint(failing_symbols)

    # 确认所有产出的有效结果排名连续且无损
    for idx, item in enumerate(results):
        assert item.rank == idx + 1
        assert item.symbol not in failing_symbols
        assert item.score > Decimal("0")


@pytest.mark.asyncio
async def test_golden_500_symbols_concurrency_control_benchmark() -> None:
    """验证大样本（500+）并发控制有效性与峰值并发约束。"""
    symbols = default_universe_manager.get_universe_symbols("sp500")
    limit = 15

    strategy_service = GoldenDeterministicStrategyService(delay_seconds=0.001)
    executor = ScreenerExecutor(strategy_service=strategy_service, default_concurrency=limit)

    results, failed_items = await executor.execute_screening(
        strategy_id="concurrency_test",
        symbols=symbols,
        params={"concurrency": limit},
        as_of=_FIXED_NOW,
    )

    assert len(failed_items) == 0
    assert len(results) > 0
    # 峰值并发严格受限于 Semaphore limit
    assert strategy_service.max_concurrent_seen <= limit
    assert strategy_service.call_count == len(symbols)


# =============================================================================
# 3. 多热门主题场景（AI、减肥药、高股息、云 SaaS、清洁能源）AI 卡片与事实溯源
# =============================================================================


class MockMarketDataService:
    """黄金数据集市场数据事实模拟器。"""

    def __init__(self, stock_facts: dict[str, dict[str, Any]] | None = None) -> None:
        self.stock_facts = stock_facts or {}

    async def get_bars_daily(
        self,
        symbol: str,
        start_date: Any,
        end_date: Any,
    ) -> Any:
        return []

    async def build_facts(
        self,
        symbol: str,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        sym = symbol.upper()
        if sym in self.stock_facts:
            return self.stock_facts[sym]
        # 默认生成确定性基本面事实
        return {
            "symbol": sym,
            "pe": Decimal("28.5"),
            "roe": Decimal("18.2"),
            "revenue_growth": Decimal("15.4"),
            "gross_margin": Decimal("48.5"),
            "market_cap_tier": "large",
        }


class MockThemeAIService:
    """生成合规或篡改主题卡片的 AI 模拟器。"""

    def __init__(
        self,
        hallucinate_numbers: bool = False,
        inject_forbidden_term: str | None = None,
    ) -> None:
        self.hallucinate_numbers = hallucinate_numbers
        self.inject_forbidden_term = inject_forbidden_term

    async def run(
        self,
        use_case: str,
        facts: dict[str, Any],
        params: dict[str, Any] | None = None,
        user_id: UUID | None = None,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        stocks_facts = facts.get("stocks", [])
        cards: list[dict[str, Any]] = []

        for sf in stocks_facts:
            sym = sf.get("symbol", "UNKNOWN")
            name = sf.get("name", sym)
            pe = sf.get("pe", 25.0)
            roe = sf.get("roe", 15.0)

            financial_strengths = [
                f"最新滚动市盈率(PE)为 {pe} 倍",
                f"净资产收益率(ROE)达到 {roe}%",
            ]

            # 故意注入编造数字测试防线
            if self.hallucinate_numbers:
                financial_strengths.append("毛利率高达 99.8% 超越所有同行")

            why_watch = f"在产业链中具备核心壁垒，ROE 为 {roe}%"
            if self.inject_forbidden_term:
                why_watch += f"，属于{self.inject_forbidden_term}标的"

            cards.append(
                {
                    "symbol": sym,
                    "name": name,
                    "one_line_intro": f"{name}是细分赛道的重要标的",
                    "why_watch": why_watch,
                    "financial_strengths": financial_strengths,
                    "main_risks": ["行业竞争加剧风险", "供应链波动风险"],
                    "suitable_for": ["稳健成长型投资者"],
                    "more_attractive_when": f"PE 回调至 {pe} 倍以下时更具性价比",
                }
            )

        return {"cards": cards}


@pytest.mark.asyncio
async def test_golden_multi_theme_cards_generation_and_fact_tracing() -> None:
    """验证系统全部预设热门主题场景端到端生成与事实溯源 100% 严密合规。"""
    clock = FrozenClock(_FIXED_NOW)

    # 预设黄金基本面事实库
    golden_facts: dict[str, dict[str, Any]] = {
        # AI 芯片
        "NVDA": {"pe": Decimal("38.2"), "roe": Decimal("55.1"), "gross_margin": Decimal("75.0")},
        "TSM": {"pe": Decimal("24.0"), "roe": Decimal("28.3"), "gross_margin": Decimal("53.5")},
        # GLP-1 减肥药
        "LLY": {"pe": Decimal("48.5"), "roe": Decimal("32.0"), "gross_margin": Decimal("80.2")},
        "NVO": {"pe": Decimal("35.1"), "roe": Decimal("42.4"), "gross_margin": Decimal("84.0")},
        # 高股息
        "JNJ": {"pe": Decimal("16.8"), "roe": Decimal("18.5"), "gross_margin": Decimal("67.1")},
        "KO": {"pe": Decimal("22.3"), "roe": Decimal("38.0"), "gross_margin": Decimal("59.2")},
        # 云 SaaS
        "MSFT": {"pe": Decimal("31.2"), "roe": Decimal("35.4"), "gross_margin": Decimal("69.8")},
        "PLTR": {"pe": Decimal("65.0"), "roe": Decimal("12.5"), "gross_margin": Decimal("81.0")},
        # 清洁能源
        "FSLR": {"pe": Decimal("22.5"), "roe": Decimal("16.2"), "gross_margin": Decimal("34.1")},
        "ENPH": {"pe": Decimal("28.0"), "roe": Decimal("19.5"), "gross_margin": Decimal("38.0")},
    }

    marketdata_service = MockMarketDataService(stock_facts=golden_facts)
    ai_service = MockThemeAIService(hallucinate_numbers=False)

    generator = ThemeCardsGenerator(
        universe_manager=default_universe_manager,
        ai_service=ai_service,
        marketdata_service=marketdata_service,
        clock=clock,
    )

    theme_keys = [
        "ai_chips",
        "glp1_weightloss",
        "high_dividend",
        "cyber_security",
        "cloud_saas",
        "clean_energy",
    ]

    for theme_id in theme_keys:
        resp = await generator.generate_theme_cards(theme_id=theme_id)
        assert isinstance(resp, ThemeCardsResponse)
        assert resp.theme_id == theme_id
        assert resp.prompt_version == THEME_CARD_PROMPT_VERSION
        assert len(resp.cards) > 0

        # 验证每张卡片
        theme_def = default_universe_manager.get_theme(theme_id)
        constituent_symbols = {s.symbol for s in theme_def.stocks}

        for card in resp.cards:
            assert card.symbol in constituent_symbols
            assert card.name != ""
            assert len(card.financial_strengths) >= 1
            assert len(card.main_risks) >= 1
            assert len(card.suitable_for) >= 1

            # 校验无任何违规禁用词
            for banned in DEFAULT_BANNED_TERMS:
                assert banned not in card.one_line_intro
                assert banned not in card.why_watch
                assert banned not in " ".join(card.financial_strengths)
                assert banned not in card.more_attractive_when


# =============================================================================
# 4. 防编造与防幻觉对抗测试（Tamper & Anti-Hallucination Guard）
# =============================================================================


@pytest.mark.asyncio
async def test_golden_anti_hallucination_detects_fabricated_numbers() -> None:
    """对抗测试：当大模型输出未经事实支持的幻觉数字时，FactVerifier 严格拦截。"""
    clock = FrozenClock(_FIXED_NOW)
    marketdata_service = MockMarketDataService()
    # 注入幻觉数字
    ai_service = MockThemeAIService(hallucinate_numbers=True)

    generator = ThemeCardsGenerator(
        universe_manager=default_universe_manager,
        ai_service=ai_service,
        marketdata_service=marketdata_service,
        clock=clock,
    )

    with pytest.raises(ScreenerError, match="主题卡片数字溯源拦截"):
        await generator.generate_theme_cards(theme_id="ai_chips")


@pytest.mark.asyncio
async def test_golden_anti_hallucination_detects_banned_promises() -> None:
    """对抗测试：当大模型输出稳赚不赔、保本等违规承诺时，FactVerifier 严格拦截。"""
    clock = FrozenClock(_FIXED_NOW)
    marketdata_service = MockMarketDataService()
    # 注入违规承诺词汇
    ai_service = MockThemeAIService(inject_forbidden_term="稳赚不赔")

    generator = ThemeCardsGenerator(
        universe_manager=default_universe_manager,
        ai_service=ai_service,
        marketdata_service=marketdata_service,
        clock=clock,
    )

    with pytest.raises(ScreenerError, match="主题卡片合规拦截"):
        await generator.generate_theme_cards(theme_id="ai_chips")


@pytest.mark.asyncio
async def test_golden_deterministic_offline_fallback() -> None:
    """验证当 AI 服务离线（None）时，系统自动降级至 100% 事实确定的兜底卡片。"""
    clock = FrozenClock(_FIXED_NOW)
    marketdata_service = MockMarketDataService(
        stock_facts={
            "NVDA": {
                "pe": Decimal("35.0"),
                "roe": Decimal("45.0"),
                "revenue_growth": Decimal("110.0"),
            }
        }
    )

    generator = ThemeCardsGenerator(
        universe_manager=default_universe_manager,
        ai_service=None,  # 离线环境
        marketdata_service=marketdata_service,
        clock=clock,
    )

    resp = await generator.generate_theme_cards(theme_id="ai_chips")
    assert resp.theme_id == "ai_chips"
    assert len(resp.cards) > 0

    nvda_card = next(c for c in resp.cards if c.symbol == "NVDA")
    assert "市盈率(PE)约为 35.0 倍" in nvda_card.financial_strengths
    assert "净资产收益率(ROE)为 45.0%" in nvda_card.financial_strengths
    assert "营收增速达到 110.0%" in nvda_card.financial_strengths


# =============================================================================
# 5. ScreenerService 全链路大样本端到端持久化与租户隔离
# =============================================================================


class MockInMemoryScreenerRepository(ScreenerRepositoryProtocol):
    """内存级筛选任务仓储，验证多租户数据隔离与落库完整性。"""

    def __init__(self) -> None:
        self.runs: dict[UUID, ScreenerRun] = {}

    async def create_run(self, run: ScreenerRun) -> ScreenerRun:
        if getattr(run, "id", None) is None:
            run.id = uuid.uuid4()
        self.runs[run.id] = run
        return run

    async def update_run(self, run: ScreenerRun) -> ScreenerRun:
        self.runs[run.id] = run
        return run

    async def get_run(self, run_id: UUID, user_id: UUID) -> ScreenerRun | None:
        r = self.runs.get(run_id)
        if r and r.user_id == user_id:
            return r
        return None

    async def list_runs(self, user_id: UUID, limit: int = 20, offset: int = 0) -> list[ScreenerRun]:
        user_runs = [r for r in self.runs.values() if r.user_id == user_id]
        return user_runs[offset : offset + limit]


@pytest.mark.asyncio
async def test_golden_screener_service_full_pipeline_persistence() -> None:
    """验证 ScreenerService 对 500 标的大股票池执行、结果落库与投研导出的全流程。"""
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    clock = FrozenClock(_FIXED_NOW)

    screener_repo = MockInMemoryScreenerRepository()
    watchlist_repo = AsyncMock(spec=WatchlistRepositoryProtocol)
    strategy_service = GoldenDeterministicStrategyService()
    executor = ScreenerExecutor(strategy_service=strategy_service, default_concurrency=25)

    service = ScreenerService(
        screener_repo=screener_repo,
        watchlist_repo=watchlist_repo,
        universe_manager=default_universe_manager,
        executor=executor,
        clock=clock,
    )

    # 1. User A 执行标普 500 策略筛选
    req = ScreenerRunCreate(
        universe="sp500",
        strategy_id="momentum_golden",
        params={"min_score": 50},
    )
    run_read_a = await service.run_screener(user_id=user_a, request=req)

    assert run_read_a.user_id == user_a
    assert run_read_a.universe == "sp500"
    assert run_read_a.total_symbols == len(SP500_SYMBOLS)
    assert run_read_a.status == "succeeded"
    assert len(run_read_a.results) > 0

    # 2. 验证多租户数据隔离回读
    # User A 可正常读取自己创建的任务
    read_back_a = await service.get_screener_run(run_id=run_read_a.id, user_id=user_a)
    assert read_back_a.id == run_read_a.id
    assert len(read_back_a.results) == len(run_read_a.results)

    # User B 试图越权读取 User A 的任务 -> 抛出 404 (ScreenerRunNotFoundError)
    with pytest.raises(ScreenerRunNotFoundError):
        await service.get_screener_run(run_id=run_read_a.id, user_id=user_b)

    # 3. 验证从筛选结果一键导出到投研对比
    top_3_symbols = [r.symbol for r in run_read_a.results[:3]]
    export_payload = service.export_to_research(
        ExportToResearchRequest(symbols=top_3_symbols, target_action="compare")
    )
    assert export_payload["target_action"] == "compare"
    assert export_payload["symbols"] == top_3_symbols
    assert export_payload["status"] == "ready"
    assert export_payload["target_endpoint"] == "/api/v1/research/compare"
