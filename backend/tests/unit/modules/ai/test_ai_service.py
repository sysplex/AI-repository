"""M5-T07 单元测试：AIService 核心门面与智能快照缓存。

测试场景：
1. 事实快照哈希 (compute_content_hash) 与缓存键 (compute_cache_key) 确定性生成；
2. 事实快照持久化去重 (_ensure_data_snapshot)；
3. 缓存命中 (Cache HIT)：零 LLM 调用、零 Token 计费、零配额扣减、穿透放行；
4. 缓存未命中 (Cache MISS)：完整管线（风控检查 -> 提示词渲染 -> LLM 调用 ->
   Schema 校验与反馈重试 -> 数字溯源反编造 -> 记账更新 -> 落库持久化）；
5. 预算熔断拦截 (503) 与配额耗尽拦截 (429)；
6. 失败降级归档：Schema 校验失败或数字溯源违规时持久化 status='failed' 报告；
7. 报告详情查询与多租户隔离 (Tenant Isolation -> NotFound 404)；
8. 用户历史报告分页与筛选 (list_reports)；
9. 事实快照回溯与可用提示词模板列表查询。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.clock import FrozenClock, set_clock
from app.core.errors import NotFound
from app.modules.ai.adapters.mock import MockFaultMode, MockLLMClient
from app.modules.ai.circuit_breaker import BudgetCircuitBreaker
from app.modules.ai.exceptions import (
    BudgetCircuitOpenError,
    FactTracingError,
    QuotaExceededError,
    SchemaValidationError,
)
from app.modules.ai.models import AIReport
from app.modules.ai.quota import QuotaService
from app.modules.ai.schemas import AnalysisReport
from app.modules.ai.service import AIService

_TEST_USER_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_TEST_USER_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
_TEST_NOW = datetime(2026, 11, 14, 10, 0, tzinfo=UTC)

SAMPLE_FACTS = {
    "symbol": "AAPL",
    "current_price": 182.50,
    "pe_ratio": 28.5,
    "revenue_growth": 0.12,
}


@pytest.fixture(autouse=True)
def _setup_clock() -> None:
    clock = FrozenClock(_TEST_NOW)
    set_clock(clock)


def _mock_result(
    *,
    scalar: Any = None,
    scalars: list[Any] | None = None,
    row: tuple[Any, ...] | None = None,
    rowcount: int = 1,
) -> MagicMock:
    res = MagicMock()
    res.scalar_one_or_none.return_value = scalar
    res.scalar_one.return_value = scalar
    res.scalars.return_value.all.return_value = scalars or []
    res.one_or_none.return_value = row
    res.rowcount = rowcount
    return res


def _mock_session() -> AsyncMock:
    session = AsyncMock()
    session.execute.return_value = _mock_result()
    session.flush = AsyncMock()
    session.add = MagicMock()
    return session


# =============================================================================
# 1. 静态哈希与缓存键计算
# =============================================================================


def test_compute_content_hash_deterministic() -> None:
    """验证相同内容生成唯一相同 SHA-256 哈希，且键顺序无关。"""
    facts1 = {"symbol": "AAPL", "price": 180.5, "pe": 28.0}
    facts2 = {"pe": 28.0, "price": 180.5, "symbol": "AAPL"}

    hash1 = AIService.compute_content_hash(facts1)
    hash2 = AIService.compute_content_hash(facts2)

    assert hash1 == hash2
    assert len(hash1) == 64

    # 改变数值生成不同哈希
    facts3 = {"symbol": "AAPL", "price": 180.6, "pe": 28.0}
    assert AIService.compute_content_hash(facts3) != hash1


def test_compute_cache_key_deterministic() -> None:
    """验证 cache_key 包含用例、提示词版本、快照哈希与排序参数。"""
    key1 = AIService.compute_cache_key(
        use_case="stock_analysis",
        prompt_version="v1",
        content_hash="abcdef" * 10 + "1234",
        params={"horizon": "medium", "risk": "moderate"},
    )
    key2 = AIService.compute_cache_key(
        use_case="stock_analysis",
        prompt_version="v1",
        content_hash="abcdef" * 10 + "1234",
        params={"risk": "moderate", "horizon": "medium"},
    )
    assert key1 == key2
    assert len(key1) == 64


# =============================================================================
# 2. 缓存命中 (Cache HIT) 场景
# =============================================================================


async def test_cache_hit_returns_cached_report_zero_cost_zero_quota() -> None:
    """缓存命中：直接返回 cached=True 报告，无外部 LLM 调用、无费用、不扣配额。"""
    session = _mock_session()

    cached_id = uuid.uuid4()
    cached_report = AIReport(
        id=cached_id,
        user_id=_TEST_USER_A,
        use_case="facts_summary",
        params={},
        cache_key="test_cache_key",
        data_snapshot_id="snapshot_hash_123",
        prompt_version="v1",
        model="mock-gpt",
        payload={"summary": "Historical cached summary", "key_observations": []},
        cost_usd=Decimal("0.005000"),
        status="success",
        created_at=_TEST_NOW,
    )

    def fake_execute(stmt: Any) -> MagicMock:
        sql = str(stmt)
        if "data_snapshots" in sql:
            return _mock_result(scalar="snapshot_hash_123")
        if "ai_reports" in sql:
            return _mock_result(scalar=cached_report)
        return _mock_result()

    session.execute.side_effect = fake_execute

    llm_client = MockLLMClient()
    quota_service = AsyncMock(spec=QuotaService)
    circuit_breaker = BudgetCircuitBreaker()

    service = AIService(
        session=session,
        llm_client=llm_client,
        quota_service=quota_service,
        circuit_breaker=circuit_breaker,
    )

    report = await service.run(
        use_case="facts_summary",
        facts=SAMPLE_FACTS,
        user_id=_TEST_USER_A,
    )

    assert isinstance(report, AnalysisReport)
    assert report.id == cached_id
    assert report.cached is True
    assert report.cost_usd == Decimal("0.000000")
    assert report.payload["summary"] == "Historical cached summary"

    # 验证未调用 LLM，未扣减配额，未向 DB 添加新报告
    assert len(llm_client.calls) == 0
    quota_service.consume.assert_not_called()
    session.add.assert_not_called()


# =============================================================================
# 3. 缓存未命中 (Cache MISS) 端到端全链路场景
# =============================================================================


async def test_cache_miss_executes_full_pipeline_and_persists() -> None:
    """缓存未命中：执行完整 AI 分析生成、校验、记账与报告入库。"""
    session = _mock_session()

    def fake_execute(stmt: Any) -> MagicMock:
        sql = str(stmt)
        if "SELECT data_snapshots.content_hash" in sql:
            return _mock_result(scalar=None)  # snapshot 尚不存在
        if "INSERT INTO data_snapshots" in sql:
            return _mock_result(rowcount=1)
        if "ai_reports" in sql:
            return _mock_result(scalar=None)  # 缓存未命中
        return _mock_result()

    session.execute.side_effect = fake_execute

    # 配置 Mock 返回合规 JSON（包含真实 facts 中的数字 182.50 与 28.5）
    payload = {
        "symbol": "AAPL",
        "verdict": "buy",
        "confidence": "high",
        "summary": "Solid company trading at 182.50 with 28.5 PE",
        "risks": ["Competition"],
    }
    llm_client = MockLLMClient(model="gpt-4o", default_response=payload)
    quota_service = QuotaService(daily_quota=20)  # 使用内存模式
    circuit_breaker = BudgetCircuitBreaker()

    service = AIService(
        session=session,
        llm_client=llm_client,
        quota_service=quota_service,
        circuit_breaker=circuit_breaker,
    )

    report = await service.run(
        use_case="stock_analysis",
        facts=SAMPLE_FACTS,
        user_id=_TEST_USER_A,
    )

    assert isinstance(report, AnalysisReport)
    assert report.cached is False
    assert report.use_case == "stock_analysis"
    assert report.payload["symbol"] == "AAPL"
    assert report.cost_usd > Decimal("0")

    # 验证配额已扣减 1 次
    status = await quota_service.check(_TEST_USER_A)
    assert status.calls_today == 1
    assert status.remaining_calls == 19

    # 验证调用成本计入熔断器
    assert circuit_breaker.daily_cost_usd > Decimal("0")

    # 验证新报告被写入 session
    session.add.assert_called_once()
    added_report = session.add.call_args[0][0]
    assert isinstance(added_report, AIReport)
    assert added_report.status == "success"
    assert added_report.user_id == _TEST_USER_A


# =============================================================================
# 4. 风控拦截测试：预算熔断与配额超额
# =============================================================================


async def test_budget_circuit_open_blocks_cache_miss() -> None:
    """当预算熔断器处于 OPEN 状态时，未命中缓存的请求立即抛出 503。"""
    session = _mock_session()
    session.execute.return_value = _mock_result(scalar=None)

    breaker = BudgetCircuitBreaker()
    breaker.trip("daily_budget_exceeded")

    service = AIService(session=session, circuit_breaker=breaker)

    with pytest.raises(BudgetCircuitOpenError):
        await service.run(
            use_case="facts_summary",
            facts=SAMPLE_FACTS,
            user_id=_TEST_USER_A,
        )


async def test_quota_exceeded_blocks_cache_miss() -> None:
    """当用户当日配额用尽时，未命中缓存的请求抛出 429。"""
    session = _mock_session()
    session.execute.return_value = _mock_result(scalar=None)

    quota_service = AsyncMock(spec=QuotaService)
    quota_service.check.side_effect = QuotaExceededError("Quota exhausted")

    service = AIService(session=session, quota_service=quota_service)

    with pytest.raises(QuotaExceededError):
        await service.run(
            use_case="facts_summary",
            facts=SAMPLE_FACTS,
            user_id=_TEST_USER_A,
        )


# =============================================================================
# 5. 校验失败与防编造拦截及失败归档
# =============================================================================


async def test_schema_validation_failure_records_failed_report() -> None:
    """Schema 校验重试耗尽失败时，记录 status='failed' 报告并抛出 422。"""
    session = _mock_session()
    session.execute.return_value = _mock_result(scalar=None)

    # 注入返回畸形非 JSON 字符串
    llm_client = MockLLMClient(fault_mode=MockFaultMode.INVALID_JSON)
    quota_service = QuotaService(daily_quota=20)
    service = AIService(
        session=session,
        llm_client=llm_client,
        quota_service=quota_service,
    )

    with pytest.raises(SchemaValidationError):
        await service.run(
            use_case="stock_analysis",
            facts=SAMPLE_FACTS,
            user_id=_TEST_USER_A,
        )

    # 验证添加了 failed 报告
    session.add.assert_called_once()
    failed_report = session.add.call_args[0][0]
    assert failed_report.status == "failed"
    assert failed_report.error_message is not None


async def test_fact_tracing_violation_blocks_hallucination() -> None:
    """数字溯源发现编造虚假数字时拦截并记录 failed 报告。"""
    session = _mock_session()
    session.execute.return_value = _mock_result(scalar=None)

    # 模型返回了输入 facts 中不存在的编造价格 999.99
    fabricated_payload = {
        "symbol": "AAPL",
        "verdict": "buy",
        "confidence": "high",
        "summary": "Fabricated target price of 999.99 dollars",
        "risks": [],
    }
    llm_client = MockLLMClient(default_response=fabricated_payload)
    quota_service = QuotaService(daily_quota=20)
    service = AIService(
        session=session,
        llm_client=llm_client,
        quota_service=quota_service,
    )

    with pytest.raises(FactTracingError):
        await service.run(
            use_case="stock_analysis",
            facts=SAMPLE_FACTS,
            user_id=_TEST_USER_A,
        )

    session.add.assert_called_once()
    failed_report = session.add.call_args[0][0]
    assert failed_report.status == "failed"


# =============================================================================
# 6. 报告详情查询与多租户隔离
# =============================================================================


async def test_get_report_tenant_isolation_raises_404() -> None:
    """多租户隔离：用户 B 试图访问用户 A 的私有报告时返回 NotFound (404)。"""
    session = _mock_session()
    # 模拟 SQL 过滤后返回 None（即 user_id 不匹配）
    session.execute.return_value = _mock_result(scalar=None)

    service = AIService(session=session)

    with pytest.raises(NotFound, match="AI 报告不存在或无权访问"):
        await service.get_report(report_id=uuid.uuid4(), user_id=_TEST_USER_B)


async def test_get_report_success() -> None:
    """用户正常访问自己名下的报告。"""
    report_id = uuid.uuid4()
    mock_rep = AIReport(
        id=report_id,
        user_id=_TEST_USER_A,
        use_case="stock_analysis",
        params={},
        cache_key="key",
        data_snapshot_id="snapshot_123",
        prompt_version="v1",
        model="mock",
        payload={"verdict": "buy"},
        cost_usd=Decimal("0.001"),
        status="success",
        created_at=_TEST_NOW,
    )
    session = _mock_session()
    session.execute.return_value = _mock_result(scalar=mock_rep)

    service = AIService(session=session)
    res = await service.get_report(report_id=report_id, user_id=_TEST_USER_A)
    assert res.id == report_id
    assert res.user_id == _TEST_USER_A
    assert res.use_case == "stock_analysis"


async def test_list_reports() -> None:
    """列出当前用户的报告列表。"""
    session = _mock_session()
    rep1 = AIReport(
        id=uuid.uuid4(),
        user_id=_TEST_USER_A,
        use_case="stock_analysis",
        params={},
        cache_key="k1",
        data_snapshot_id="s1",
        prompt_version="v1",
        model="m",
        payload={},
        cost_usd=Decimal("0.001"),
        status="success",
        created_at=_TEST_NOW,
    )
    session.execute.return_value = _mock_result(scalars=[rep1])

    service = AIService(session=session)
    reports = await service.list_reports(user_id=_TEST_USER_A, use_case="stock_analysis")
    assert len(reports) == 1
    assert reports[0].id == rep1.id


# =============================================================================
# 7. 快照回溯、配额状态与模板清单
# =============================================================================


async def test_get_snapshot_success_and_not_found() -> None:
    """快照查询：存在时返回字典，不存在时抛出 NotFound。"""
    session = _mock_session()
    session.execute.return_value = _mock_result(
        row=(
            "hash_abc",
            "AAPL",
            _TEST_NOW,
            ["quote"],
            {"quote": 180},
            [],
            _TEST_NOW,
        )
    )

    service = AIService(session=session)
    snap = await service.get_snapshot("hash_abc")
    assert snap["content_hash"] == "hash_abc"
    assert snap["symbol"] == "AAPL"

    # 不存在场景
    session.execute.return_value = _mock_result(row=None)
    with pytest.raises(NotFound, match="未找到哈希"):
        await service.get_snapshot("missing_hash")


async def test_list_prompts() -> None:
    """列出当前所有可用提示词模板。"""
    session = _mock_session()
    service = AIService(session=session)

    prompts = service.list_prompts()
    assert len(prompts) >= 3
    use_cases = {p.use_case for p in prompts}
    assert "health_check" in use_cases
    assert "facts_summary" in use_cases
    assert "stock_analysis" in use_cases
