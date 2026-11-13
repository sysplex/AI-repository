"""M5-T06 单元测试：配额管理服务 (QuotaService) 与预算熔断器 (BudgetCircuitBreaker)。

覆盖：
1. QuotaService 协议契约实现 (QuotaServiceProtocol)；
2. 正常配额检查、递增扣减与落库记账；
3. 超出当日配额拦截并抛出 QuotaExceededError (HTTP 429)；
4. 跨日配额重置与历史记录保留；
5. AsyncSession 数据库会话下的 SQL 构造与 UPSERT 行为；
6. BudgetCircuitBreaker 状态机流转 (CLOSED -> OPEN -> RESET)；
7. 日度/月度预算超额熔断与 503 拦截；
8. 缓存命中 (cached=True) 免熔断穿透放行；
9. 跨日/跨月成本自动滚转与自愈重置；
10. 管理员动态调优限额与手动触发/重置。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock, set_clock
from app.core.errors import ErrorCode
from app.modules.ai.circuit_breaker import (
    DEFAULT_DAILY_BUDGET_USD,
    DEFAULT_MONTHLY_BUDGET_USD,
    BudgetCircuitBreaker,
)
from app.modules.ai.exceptions import (
    BudgetCircuitOpenError,
    QuotaExceededError,
)
from app.modules.ai.ports import QuotaServiceProtocol
from app.modules.ai.quota import QuotaService
from app.modules.ai.schemas import BudgetCircuitStatus, QuotaStatus

_TEST_USER_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")
_TEST_NOW = datetime(2026, 11, 13, 10, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _setup_clock() -> None:
    clock = FrozenClock(_TEST_NOW)
    set_clock(clock)


# =============================================================================
# 1. QuotaService 单元测试 (In-Memory 模式)
# =============================================================================


def test_quota_service_protocol_conformance() -> None:
    """验证 QuotaService 严格实现 QuotaServiceProtocol。"""
    service = QuotaService(daily_quota=20)
    assert isinstance(service, QuotaServiceProtocol)
    assert service.daily_quota == 20


async def test_quota_service_initial_status_unconsumed() -> None:
    """未消耗时配额检查：调用次数为 0，剩余等于上限，未超额。"""
    service = QuotaService(daily_quota=20)
    status = await service.check(_TEST_USER_ID)

    assert isinstance(status, QuotaStatus)
    assert status.user_id == _TEST_USER_ID
    assert status.usage_date == _TEST_NOW.date()
    assert status.calls_today == 0
    assert status.daily_quota == 20
    assert status.remaining_calls == 20
    assert not status.is_exceeded


async def test_quota_service_consume_and_record() -> None:
    """正常扣减配额并验证用量记录累加。"""
    service = QuotaService(daily_quota=20)

    # 首次扣减
    await service.consume(
        user_id=_TEST_USER_ID,
        tokens_in=1000,
        tokens_out=200,
        cost_usd=Decimal("0.005000"),
    )

    status = await service.check(_TEST_USER_ID)
    assert status.calls_today == 1
    assert status.remaining_calls == 19
    assert not status.is_exceeded

    # 再次扣减
    await service.consume(
        user_id=_TEST_USER_ID,
        tokens_in=500,
        tokens_out=100,
        cost_usd=Decimal("0.002500"),
    )

    status2 = await service.check(_TEST_USER_ID)
    assert status2.calls_today == 2
    assert status2.remaining_calls == 18

    # 验证完整用量记录
    rec = await service.get_usage_record(_TEST_USER_ID)
    assert rec is not None
    assert rec["calls"] == 2
    assert rec["tokens_in"] == 1500
    assert rec["tokens_out"] == 300
    assert rec["cost_usd"] == Decimal("0.007500")


async def test_quota_service_exceeded_intercepted() -> None:
    """达到并超出当日配额时立即抛出 QuotaExceededError (HTTP 429)。"""
    service = QuotaService(daily_quota=3)

    # 消耗 3 次达到上限
    for _ in range(3):
        await service.consume(
            user_id=_TEST_USER_ID,
            tokens_in=100,
            tokens_out=50,
            cost_usd=Decimal("0.001000"),
        )

    # 查看状态（不抛错）
    status = await service.check(_TEST_USER_ID, raise_on_exceeded=False)
    assert status.calls_today == 3
    assert status.remaining_calls == 0
    assert status.is_exceeded is True

    # 默认检查抛出 429 异常
    with pytest.raises(QuotaExceededError) as exc_info:
        await service.check(_TEST_USER_ID, raise_on_exceeded=True)

    err = exc_info.value
    assert err.code == ErrorCode.QUOTA_EXCEEDED
    assert err.http_status == 429
    assert err.details["user_id"] == str(_TEST_USER_ID)
    assert err.details["calls_today"] == 3
    assert err.details["daily_quota"] == 3


async def test_quota_service_new_day_reset() -> None:
    """跨日后当日调用次数自动重置为 0，配额重新可用。"""
    clock = FrozenClock(_TEST_NOW)
    set_clock(clock)
    service = QuotaService(daily_quota=2)

    # 今日用满 2 次
    await service.consume(_TEST_USER_ID, 100, 50, Decimal("0.001"))
    await service.consume(_TEST_USER_ID, 100, 50, Decimal("0.001"))
    assert (await service.check(_TEST_USER_ID, raise_on_exceeded=False)).is_exceeded

    # 时钟推进到次日
    clock.advance(timedelta(days=1))
    next_day_status = await service.check(_TEST_USER_ID)
    assert next_day_status.usage_date == _TEST_NOW.date() + timedelta(days=1)
    assert next_day_status.calls_today == 0
    assert next_day_status.remaining_calls == 2
    assert not next_day_status.is_exceeded

    # 昨日历史记录仍可单独按日期查询
    yesterday_rec = await service.get_usage_record(_TEST_USER_ID, usage_date=_TEST_NOW.date())
    assert yesterday_rec is not None
    assert yesterday_rec["calls"] == 2


async def test_quota_service_custom_quota_and_reset() -> None:
    """动态调整配额与手动重置用量。"""
    service = QuotaService(daily_quota=5)
    service.set_daily_quota(10)
    assert service.daily_quota == 10

    with pytest.raises(ValueError, match="non-negative"):
        service.set_daily_quota(-1)

    await service.consume(_TEST_USER_ID, 100, 50, Decimal("0.001"))
    assert (await service.check(_TEST_USER_ID)).calls_today == 1

    await service.reset_usage(_TEST_USER_ID)
    assert (await service.check(_TEST_USER_ID)).calls_today == 0
    assert await service.get_usage_record(_TEST_USER_ID) is None


# =============================================================================
# 2. QuotaService 数据库 Session 模式单元测试
# =============================================================================


def _mock_result(
    *,
    row: tuple[Any, ...] | None = None,
    rowcount: int = 1,
) -> MagicMock:
    res = MagicMock()
    res.one_or_none.return_value = row
    res.rowcount = rowcount
    return res


def _mock_session(*, result: MagicMock | None = None) -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = result if result is not None else _mock_result()
    session.flush = AsyncMock()
    return session


async def test_quota_service_db_check_empty_row() -> None:
    """数据库无记录时，返回 calls=0。"""
    session = _mock_session(result=_mock_result(row=None))
    service = QuotaService(session=session, daily_quota=20)

    status = await service.check(_TEST_USER_ID)
    assert status.calls_today == 0
    assert status.remaining_calls == 20

    # 验证生成的 SQL 包含 ai_usage 与字段过滤
    assert session.execute.await_count == 1
    stmt = session.execute.await_args_list[0].args[0]
    sql_text = str(stmt)
    assert "ai_usage" in sql_text
    assert "ai_usage.user_id =" in sql_text
    assert "ai_usage.usage_date =" in sql_text


async def test_quota_service_db_check_existing_row() -> None:
    """数据库已有记录时，正确提取 calls。"""
    session = _mock_session(result=_mock_result(row=(15,)))
    service = QuotaService(session=session, daily_quota=20)

    status = await service.check(_TEST_USER_ID)
    assert status.calls_today == 15
    assert status.remaining_calls == 5
    assert not status.is_exceeded


async def test_quota_service_db_consume_existing_row_updates() -> None:
    """已有记录时，consume 执行 update。"""
    # rowcount=1 表示 update 成功命中行
    session = _mock_session(result=_mock_result(rowcount=1))
    service = QuotaService(session=session, daily_quota=20)

    await service.consume(_TEST_USER_ID, 200, 100, Decimal("0.002000"))

    assert session.execute.await_count == 1
    stmt = session.execute.await_args_list[0].args[0]
    sql = str(stmt)
    assert "UPDATE ai_usage" in sql
    assert "ai_usage.calls + :calls_1" in sql
    assert session.flush.await_count == 1


async def test_quota_service_db_consume_new_row_inserts() -> None:
    """无记录时（update rowcount=0），执行 insert。"""
    session = AsyncMock(spec=AsyncSession)
    # 第一次 execute (update) 返回 rowcount=0，第二次 execute (insert) 返回正常
    update_res = _mock_result(rowcount=0)
    insert_res = _mock_result(rowcount=1)
    session.execute.side_effect = [update_res, insert_res]
    session.flush = AsyncMock()

    service = QuotaService(session=session, daily_quota=20)
    await service.consume(_TEST_USER_ID, 500, 250, Decimal("0.005000"))

    assert session.execute.await_count == 2
    first_stmt = str(session.execute.await_args_list[0].args[0])
    second_stmt = str(session.execute.await_args_list[1].args[0])
    assert "UPDATE ai_usage" in first_stmt
    assert "INSERT INTO ai_usage" in second_stmt


async def test_quota_service_db_get_usage_and_reset() -> None:
    """从数据库获取完整记录及删除重置。"""
    session = _mock_session(result=_mock_result(row=(10, 5000, 2000, Decimal("0.050000"))))
    service = QuotaService(session=session, daily_quota=20)

    rec = await service.get_usage_record(_TEST_USER_ID)
    assert rec is not None
    assert rec["calls"] == 10
    assert rec["tokens_in"] == 5000
    assert rec["tokens_out"] == 2000
    assert rec["cost_usd"] == Decimal("0.050000")

    # 重置
    await service.reset_usage(_TEST_USER_ID)
    delete_stmt = str(session.execute.await_args_list[-1].args[0])
    assert "DELETE FROM ai_usage" in delete_stmt


# =============================================================================
# 3. BudgetCircuitBreaker 预算熔断器单元测试
# =============================================================================


def test_circuit_breaker_initial_state() -> None:
    """初始状态为 CLOSED，成本为 0，熔断器未开启。"""
    breaker = BudgetCircuitBreaker()
    assert breaker.state == "CLOSED"
    assert not breaker.is_open
    assert breaker.daily_cost_usd == Decimal("0.000000")
    assert breaker.monthly_cost_usd == Decimal("0.000000")
    assert breaker.daily_budget_usd == DEFAULT_DAILY_BUDGET_USD
    assert breaker.monthly_budget_usd == DEFAULT_MONTHLY_BUDGET_USD

    # 预算检查正常放行，无异常
    breaker.check_budget()


def test_circuit_breaker_daily_budget_trips_to_open() -> None:
    """累计日度成本达到阈值时自动触发熔断 (OPEN)，抛出 503。"""
    breaker = BudgetCircuitBreaker(daily_budget_usd=Decimal("10.00"))

    # 累加至 $8.50
    breaker.record_cost(Decimal("8.50"))
    assert not breaker.is_open
    breaker.check_budget()

    # 再累加 $2.00 达到 $10.50，触碰阈值
    breaker.record_cost(Decimal("2.00"))
    assert breaker.is_open
    assert breaker.state == "OPEN"

    # 校验抛出 BudgetCircuitOpenError (503)
    with pytest.raises(BudgetCircuitOpenError) as exc_info:
        breaker.check_budget()

    err = exc_info.value
    assert err.code == ErrorCode.BUDGET_CIRCUIT_OPEN
    assert err.http_status == 503
    assert "daily_budget_exceeded" in str(err)
    assert err.details["state"] == "OPEN"
    assert err.details["is_open"] is True


def test_circuit_breaker_monthly_budget_trips_to_open() -> None:
    """累计月度成本达到阈值时自动触发熔断 (OPEN)。"""
    breaker = BudgetCircuitBreaker(
        daily_budget_usd=Decimal("500.00"),
        monthly_budget_usd=Decimal("200.00"),
    )

    breaker.record_cost(Decimal("150.00"))
    assert not breaker.is_open

    # 跨越月度阈值（150 + 60 = 210 >= 200，但 210 < 500 daily）
    breaker.record_cost(Decimal("60.00"))
    assert breaker.is_open

    with pytest.raises(BudgetCircuitOpenError) as exc_info:
        breaker.check_budget()
    assert "monthly_budget_exceeded" in str(exc_info.value)


def test_circuit_breaker_cached_bypass_when_open() -> None:
    """即使熔断器处于 OPEN，快照缓存命中 (cached=True) 依然放行。"""
    breaker = BudgetCircuitBreaker(daily_budget_usd=Decimal("5.00"))
    breaker.trip("emergency_stop")
    assert breaker.is_open

    # 非缓存请求被拦截
    with pytest.raises(BudgetCircuitOpenError):
        breaker.check_budget(cached=False)

    # 缓存命中请求穿透放行，不抛错
    breaker.check_budget(cached=True)


def test_circuit_breaker_manual_trip_and_reset() -> None:
    """管理员手动触发与手动重置。"""
    breaker = BudgetCircuitBreaker()
    s0: str = breaker.state
    assert s0 == "CLOSED"

    breaker.trip("manual_admin_intervention")
    s1: str = breaker.state
    assert s1 == "OPEN"
    assert breaker.is_open

    status = breaker.get_status()
    assert isinstance(status, BudgetCircuitStatus)
    assert status.tripped_reason == "manual_admin_intervention"
    assert status.tripped_at is not None

    # 重置恢复
    breaker.reset()
    s2: str = breaker.state
    assert s2 == "CLOSED"
    assert not breaker.is_open
    assert breaker.get_status().tripped_reason is None


def test_circuit_breaker_daily_rollover_auto_recovery() -> None:
    """因日度超额触发熔断后，次日自动清零日成本并自愈恢复 CLOSED。"""
    clock = FrozenClock(_TEST_NOW)
    set_clock(clock)
    breaker = BudgetCircuitBreaker(daily_budget_usd=Decimal("10.00"))

    breaker.record_cost(Decimal("12.00"))
    assert breaker.is_open

    # 推进到次日
    clock.advance(timedelta(days=1))
    assert breaker.daily_cost_usd == Decimal("0.000000")
    assert not breaker.is_open
    assert breaker.state == "CLOSED"

    # 月度支出依然保持 $12.00
    assert breaker.monthly_cost_usd == Decimal("12.000000")


def test_circuit_breaker_monthly_rollover() -> None:
    """跨月时月度累计成本自动归零滚转。"""
    clock = FrozenClock(_TEST_NOW)  # 2026-11-13
    set_clock(clock)
    breaker = BudgetCircuitBreaker(monthly_budget_usd=Decimal("50.00"))

    breaker.record_cost(Decimal("40.00"))
    assert breaker.monthly_cost_usd == Decimal("40.000000")

    # 推进 25 天进入 12 月
    clock.advance(timedelta(days=25))
    assert breaker.monthly_cost_usd == Decimal("0.000000")


def test_circuit_breaker_configure_limits() -> None:
    """动态调整预算上限；若新阈值高于当前支出，自动解除超额熔断。"""
    breaker = BudgetCircuitBreaker(daily_budget_usd=Decimal("10.00"))
    breaker.record_cost(Decimal("15.00"))
    assert breaker.is_open

    with pytest.raises(ValueError, match="positive"):
        breaker.configure_limits(daily_budget_usd=Decimal("-5.00"))

    with pytest.raises(ValueError, match="positive"):
        breaker.configure_limits(monthly_budget_usd=Decimal("0.00"))

    # 调大日度限额至 $30.00，当前 $15.00 < $30.00，自动自愈恢复 CLOSED
    breaker.configure_limits(daily_budget_usd=Decimal("30.00"))
    assert breaker.daily_budget_usd == Decimal("30.000000")
    assert not breaker.is_open
    assert breaker.state == "CLOSED"


def test_circuit_breaker_sync_costs() -> None:
    """同步外部成本；若同步后超出阈值自动触发熔断。"""
    breaker = BudgetCircuitBreaker(daily_budget_usd=Decimal("20.00"))
    breaker.sync_costs(daily_cost_usd=Decimal("25.00"))
    assert breaker.is_open
    assert breaker.daily_cost_usd == Decimal("25.00")


async def test_quota_service_db_race_condition_retry_update() -> None:
    """并发写入冲突时捕获异常并重试 update。"""
    session = AsyncMock(spec=AsyncSession)
    update_fail = _mock_result(rowcount=0)
    insert_conflict = Exception("duplicate key")
    update_success = _mock_result(rowcount=1)

    session.execute.side_effect = [update_fail, insert_conflict, update_success]
    session.flush = AsyncMock()

    service = QuotaService(session=session, daily_quota=20)
    await service.consume(_TEST_USER_ID, 100, 50, Decimal("0.001000"))

    assert session.execute.await_count == 3


def test_circuit_breaker_check_budget_trips_if_cost_at_threshold() -> None:
    """若在 check_budget 时发现当前费用已超阈值，自动触发 trip 并抛出 503。"""
    breaker = BudgetCircuitBreaker(daily_budget_usd=Decimal("10.00"))
    # 直接修改内部费用模拟外部记账
    breaker._daily_cost_usd = Decimal("10.50")
    with pytest.raises(BudgetCircuitOpenError) as exc_info:
        breaker.check_budget()
    assert exc_info.value.details["tripped_reason"] == "daily_budget_exceeded"
    assert breaker.is_open

    breaker2 = BudgetCircuitBreaker(
        daily_budget_usd=Decimal("500.00"), monthly_budget_usd=Decimal("50.00")
    )
    breaker2._monthly_cost_usd = Decimal("55.00")
    with pytest.raises(BudgetCircuitOpenError) as exc_info2:
        breaker2.check_budget()
    assert exc_info2.value.details["tripped_reason"] == "monthly_budget_exceeded"
    assert breaker2.is_open


def test_circuit_breaker_configure_limits_monthly_auto_reset() -> None:
    """若因月度超额熔断，调大月度预算后自动恢复 CLOSED。"""
    breaker = BudgetCircuitBreaker(
        daily_budget_usd=Decimal("500.00"), monthly_budget_usd=Decimal("100.00")
    )
    breaker.record_cost(Decimal("120.00"))
    assert breaker.is_open
    assert breaker._tripped_reason == "monthly_budget_exceeded"

    breaker.configure_limits(monthly_budget_usd=Decimal("200.00"))
    assert breaker.monthly_budget_usd == Decimal("200.00")
    assert not breaker.is_open
    assert breaker.state == "CLOSED"


def test_circuit_breaker_monthly_rollover_auto_recovery() -> None:
    """因月度超额熔断后，跨月滚转自动清零月成本并恢复 CLOSED。"""
    clock = FrozenClock(_TEST_NOW)
    set_clock(clock)
    breaker = BudgetCircuitBreaker(
        daily_budget_usd=Decimal("500.00"), monthly_budget_usd=Decimal("50.00")
    )
    breaker.record_cost(Decimal("60.00"))
    assert breaker.is_open

    clock.advance(timedelta(days=25))
    assert breaker.monthly_cost_usd == Decimal("0.000000")
    assert not breaker.is_open
    assert breaker.state == "CLOSED"


def test_circuit_breaker_sync_costs_monthly_trip() -> None:
    """同步月度成本超过月度限额时触发熔断。"""
    breaker = BudgetCircuitBreaker(
        daily_budget_usd=Decimal("500.00"), monthly_budget_usd=Decimal("100.00")
    )
    breaker.sync_costs(monthly_cost_usd=Decimal("150.00"))
    assert breaker.is_open
    assert breaker._tripped_reason == "monthly_budget_exceeded"
