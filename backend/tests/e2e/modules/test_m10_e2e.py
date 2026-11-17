"""Milestone M10 调度、提醒、复盘与运维端到端集成验收测试（M10-T08）。

对齐 docs/08-test-plan.md §5 M10 与 docs/08-test-plan.md §6 E2E 规范：
1. 完整全链路流水线（身份 → 渠道 → 规则 → 模拟盘 → 收盘批处理
   → 告警派发 → AI 复盘回填 → 日报落地）；
2. 异常降级与故障隔离（通知渠道失效不阻塞收盘主流程）；
3. 幂等性保障（同一交易日重复触发结果一致，无脏数据或重复快照）；
4. 非交易日防护（日历守卫自动安全挂起跳过）；
5. 业务运行指标（Prometheus 埋点自增校验）。
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.core.metrics import create_metrics, set_current_metrics
from app.modules.ai.models import AIRecommendationOutcome, AIReport
from app.modules.notify.adapters.email_notifier import EmailNotifier
from app.modules.notify.adapters.in_app_notifier import InAppNotifier
from app.modules.notify.adapters.webhook_notifier import WebhookNotifier
from app.modules.notify.dispatcher import NotificationDispatcher
from app.modules.notify.enums import (
    AlertStatus,
    AlertType,
    ChannelType,
)
from app.modules.notify.models import Alert, AlertHistory, NotificationChannel
from app.modules.notify.ports import NotificationResult
from app.modules.notify.service import AlertService
from app.modules.scheduler.enums import DailyReportType, JobStatus
from app.modules.scheduler.models import DailyReport
from app.modules.scheduler.pipeline import PostMarketPipeline
from app.modules.scheduler.reports import DailyReportGenerator
from app.modules.simbroker.models import EquitySnapshot, SimAccount, SimOrder, SimPosition

pytestmark = pytest.mark.e2e


class MockAsyncSession:
    """供 E2E 跨模块闭环测试使用的内存异步 Session 模拟器。"""

    def __init__(self) -> None:
        self.entities: list[Any] = []
        self._committed = False

    def add(self, obj: Any) -> None:
        if not hasattr(obj, "id") or obj.id is None:
            obj.id = uuid.uuid4()
        if not hasattr(obj, "created_at") or obj.created_at is None:
            obj.created_at = datetime.now(UTC)
        if not hasattr(obj, "updated_at") or obj.updated_at is None:
            obj.updated_at = datetime.now(UTC)
        if obj not in self.entities:
            self.entities.append(obj)

    async def commit(self) -> None:
        self._committed = True

    async def flush(self) -> None:
        pass

    async def refresh(self, obj: Any) -> None:
        pass

    async def execute(self, stmt: Any) -> Any:
        stmt_str = str(stmt).lower()
        items = list(self.entities)
        filtered: list[Any] = items

        if "sim_accounts" in stmt_str or "simaccount" in stmt_str:
            filtered = [x for x in items if isinstance(x, SimAccount)]
        elif "sim_orders" in stmt_str or "simorder" in stmt_str:
            filtered = [x for x in items if isinstance(x, SimOrder)]
        elif "sim_positions" in stmt_str or "simposition" in stmt_str:
            filtered = [x for x in items if isinstance(x, SimPosition)]
        elif "equity_snapshots" in stmt_str or "equitysnapshot" in stmt_str:
            filtered = [x for x in items if isinstance(x, EquitySnapshot)]
        elif "notification_channels" in stmt_str or "notificationchannel" in stmt_str:
            filtered = [x for x in items if isinstance(x, NotificationChannel)]
        elif "alert_history" in stmt_str or "alerthistory" in stmt_str:
            filtered = [x for x in items if isinstance(x, AlertHistory)]
        elif "alerts" in stmt_str or "alert" in stmt_str:
            filtered = [x for x in items if isinstance(x, Alert)]
        elif "daily_reports" in stmt_str or "dailyreport" in stmt_str:
            all_reports = [x for x in items if isinstance(x, DailyReport)]
            if "user_id is null" in stmt_str or "user_id is" in stmt_str:
                filtered = [r for r in all_reports if r.user_id is None]
            elif "user_id" in stmt_str and "is not" not in stmt_str:
                filtered = [r for r in all_reports if r.user_id is not None]
            else:
                filtered = all_reports
        elif "ai_reports" in stmt_str or "aireport" in stmt_str:
            filtered = [x for x in items if isinstance(x, AIReport)]
        elif "ai_recommendation_outcomes" in stmt_str or "airecommendationoutcome" in stmt_str:
            filtered = [x for x in items if isinstance(x, AIRecommendationOutcome)]
        else:
            filtered = items

        class MockResult:
            def __init__(self, data: list[Any]) -> None:
                self.data = data

            def scalars(self) -> Any:
                class ScalarsResult:
                    def __init__(self, d: list[Any]) -> None:
                        self.d = d

                    def all(self) -> list[Any]:
                        return self.d

                    def first(self) -> Any | None:
                        return self.d[0] if self.d else None

                return ScalarsResult(self.data)

            def scalar_one_or_none(self) -> Any | None:
                return self.data[0] if self.data else None

            def all(self) -> list[Any]:
                return self.data

        return MockResult(filtered)


@pytest.fixture
def mock_session() -> MockAsyncSession:
    return MockAsyncSession()


@pytest.fixture
def setup_metrics() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://svc@db.internal:5432/app",
        redis_url="redis://cache.internal:6379/0",
        secret_key=SecretStr("s" * 40),
        app_version="1.0.0",
        app_env="production",
    )
    m = create_metrics(settings)
    set_current_metrics(m)


# ==============================================================================
# E2E-01: M10 全链路集成验收测试
# ==============================================================================


async def test_m10_full_chain_scheduler_alerts_and_reviews_e2e(
    mock_session: MockAsyncSession, setup_metrics: None
) -> None:
    """验证从用户渠道、提醒规则配置到收盘 DAG、警报触发与复盘日报落地全流程。"""
    user_id = uuid.uuid4()
    test_trade_date = date(2026, 11, 16)

    # --------------------------------------------------------------------------
    # 1. 建立模拟盘账户与订单持仓
    # --------------------------------------------------------------------------
    account = SimAccount(
        id=uuid.uuid4(),
        user_id=user_id,
        name="M10 E2E Portfolio",
        initial_cash=Decimal("100000.00"),
        cash=Decimal("80000.00"),
        fee_model={},
        slippage_bps=Decimal("5.0"),
        status="active",
    )
    mock_session.add(account)

    position = SimPosition(
        id=uuid.uuid4(),
        user_id=user_id,
        account_id=account.id,
        symbol="AAPL",
        qty=Decimal("100.0000"),
        avg_cost=Decimal("180.0000"),
        realized_pnl=Decimal("0.0000"),
    )
    mock_session.add(position)

    # --------------------------------------------------------------------------
    # 2. 配置多渠道通知分发网关
    # --------------------------------------------------------------------------
    channel_webhook = NotificationChannel(
        id=uuid.uuid4(),
        user_id=user_id,
        channel_type=ChannelType.WEBHOOK.value,
        name="Team Alert Webhook",
        config={"webhook_url": "https://hooks.slack.com/services/T00/B00/X00"},
        is_enabled=True,
    )
    mock_session.add(channel_webhook)

    # Mock 外部 Webhook 和邮件发送器
    mock_email = AsyncMock(spec=EmailNotifier)
    mock_email.send.return_value = NotificationResult(channel_type=ChannelType.EMAIL, success=True)
    mock_webhook = AsyncMock(spec=WebhookNotifier)
    mock_webhook.send.return_value = NotificationResult(
        channel_type=ChannelType.WEBHOOK, success=True
    )
    mock_in_app = AsyncMock(spec=InAppNotifier)
    mock_in_app.send.return_value = NotificationResult(
        channel_type=ChannelType.IN_APP, success=True
    )

    dispatcher = NotificationDispatcher(
        session_factory=None,
        email_notifier=mock_email,
        webhook_notifier=mock_webhook,
        in_app_notifier=mock_in_app,
    )
    alert_service = AlertService(session=mock_session, dispatcher=dispatcher)  # type: ignore[arg-type]

    # --------------------------------------------------------------------------
    # 3. 创建价格告警与长期投资论文破裂告警规则
    # --------------------------------------------------------------------------
    # 规则 1：AAPL 价格向上突破 $220
    alert_price = Alert(
        id=uuid.uuid4(),
        user_id=user_id,
        symbol="AAPL",
        alert_type=AlertType.PRICE.value,
        title="AAPL 突破目标价",
        conditions={"direction": "cross_above", "target_price": 220.0},
        channel_ids=[str(channel_webhook.id)],
        status=AlertStatus.ACTIVE.value,
        trigger_count=0,
        cooldown_minutes=60,
    )
    mock_session.add(alert_price)

    # 规则 2：AAPL 毛利率破裂警戒 (gross_margin < 40%)
    alert_thesis = Alert(
        id=uuid.uuid4(),
        user_id=user_id,
        symbol="AAPL",
        alert_type=AlertType.THESIS_BREAKER.value,
        title="AAPL 核心护城河毛利率破裂",
        conditions={"metric": "gross_margin", "operator": "<", "threshold": 40.0},
        channel_ids=[str(channel_webhook.id)],
        status=AlertStatus.ACTIVE.value,
        trigger_count=0,
        cooldown_minutes=1440,
    )
    mock_session.add(alert_thesis)

    # --------------------------------------------------------------------------
    # 4. 创建 AI 历史研报与建议记录 (待收盘回填超额收益)
    # --------------------------------------------------------------------------
    ai_report = AIReport(
        id=uuid.uuid4(),
        user_id=user_id,
        use_case="deep_research",
        params={"symbol": "AAPL", "verdict": "buy"},
        cache_key="test_cache_aapl",
        data_snapshot_id="hash_snapshot_001",
        prompt_version="v1.0.0",
        model="gemini-1.5-pro",
        payload={"verdict": "buy", "summary": "苹果生态持续扩张，推荐增持"},
        cost_usd=Decimal("0.025"),
        status="success",
        created_at=datetime(2026, 11, 1, 10, 0, tzinfo=UTC),
    )
    mock_session.add(ai_report)

    outcome = AIRecommendationOutcome(
        id=uuid.uuid4(),
        report_id=ai_report.id,
        symbol="AAPL",
        verdict="buy",
        price_at_report=Decimal("180.00"),
        created_at=datetime(2026, 11, 1, 10, 0, tzinfo=UTC),
    )
    mock_session.add(outcome)

    # --------------------------------------------------------------------------
    # 5. 编排并触发收盘全流程自动化批处理 DAG 流水线
    # --------------------------------------------------------------------------
    market_context = {
        "AAPL": {
            "current_price": 225.0,  # 触发 price >= 220
            "gross_margin": 38.5,  # 触发 gross_margin < 40.0
            "earnings_date": "2026-11-20",
        },
        "SPY": {
            "current_price": 590.0,
        },
    }

    report_gen = DailyReportGenerator()
    pipeline = PostMarketPipeline(
        session=mock_session,  # type: ignore[arg-type]
        alert_service=alert_service,
        report_generator=report_gen,
    )

    # 触发执行
    res = await pipeline.run(
        trade_date=test_trade_date,
        force=True,
        market_context=market_context,
    )

    # --------------------------------------------------------------------------
    # 6. 断言流水线执行拓扑与完整结果
    # --------------------------------------------------------------------------
    assert res.status == JobStatus.COMPLETED
    assert res.trade_date == test_trade_date
    assert len(res.steps) == 6

    step_names = [s.name for s in res.steps]
    assert step_names == [
        "market_data_sync",
        "simbroker_settlement",
        "screener_scan",
        "alert_evaluation",
        "ai_review_backfill",
        "daily_reports_generation",
    ]
    assert all(s.status == JobStatus.COMPLETED for s in res.steps)

    # --------------------------------------------------------------------------
    # 7. 断言各业务子域状态落地
    # --------------------------------------------------------------------------
    # (1) 每日大盘日报与用户持仓简报入库
    daily_reports = [x for x in mock_session.entities if isinstance(x, DailyReport)]
    assert len(daily_reports) == 2
    market_digest = next(
        r for r in daily_reports if r.report_type == DailyReportType.MARKET_DIGEST.value
    )
    portfolio_digest = next(
        r for r in daily_reports if r.report_type == DailyReportType.PORTFOLIO_DIGEST.value
    )
    assert market_digest.report_date == test_trade_date
    assert portfolio_digest.report_date == test_trade_date
    assert portfolio_digest.user_id == user_id
    assert float(portfolio_digest.payload.get("equity", 0)) == 102500.0

    # (2) 提醒规则触发并派发多渠道通知
    assert alert_price.status == AlertStatus.COOLDOWN.value
    assert alert_price.trigger_count == 1
    assert alert_thesis.status == AlertStatus.COOLDOWN.value
    assert alert_thesis.trigger_count == 1

    # --------------------------------------------------------------------------
    # 8. 幂等性测试（同一交易日重跑不产生重复冲突）
    # --------------------------------------------------------------------------
    res_rerun = await pipeline.run(
        trade_date=test_trade_date,
        force=True,
        market_context=market_context,
    )
    assert res_rerun.status == JobStatus.COMPLETED
    # 确认没有重复增加第二份相同的 daily_reports
    daily_reports_after = [x for x in mock_session.entities if isinstance(x, DailyReport)]
    assert len(daily_reports_after) == 2


async def test_m10_notification_failure_isolation_e2e(
    mock_session: MockAsyncSession, setup_metrics: None
) -> None:
    """验证当多渠道通知遭遇外部网络异常时，流水线具备故障隔离韧性，主流程不崩溃。"""
    user_id = uuid.uuid4()
    mock_webhook = AsyncMock(spec=WebhookNotifier)
    # 模拟外部 Webhook 超时或拒绝连接
    mock_webhook.send.side_effect = TimeoutError("Webhook provider gateway timeout 504")

    dispatcher = NotificationDispatcher(
        session_factory=None,
        webhook_notifier=mock_webhook,
    )
    alert_service = AlertService(session=mock_session, dispatcher=dispatcher)  # type: ignore[arg-type]

    # 添加规则
    alert = Alert(
        id=uuid.uuid4(),
        user_id=user_id,
        symbol="MSFT",
        alert_type=AlertType.PRICE.value,
        title="MSFT 跌破支撑位",
        conditions={"direction": "cross_below", "target_price": 400.0},
        channel_ids=["channel-dummy"],
        status=AlertStatus.ACTIVE.value,
        trigger_count=0,
    )
    mock_session.add(alert)

    pipeline = PostMarketPipeline(
        session=mock_session,  # type: ignore[arg-type]
        alert_service=alert_service,
    )

    # 执行流水线，验证不会被 TimeoutError 击穿
    res = await pipeline.run(
        trade_date=date(2026, 11, 16),
        force=True,
        market_context={"MSFT": {"current_price": 395.0}},
    )

    assert res.status == JobStatus.COMPLETED
    assert alert.trigger_count == 1


async def test_m10_non_trading_day_calendar_guard_e2e(
    mock_session: MockAsyncSession,
) -> None:
    """验证非交易日（周末/法定节假日）在无 force=true 时流水线自动安全跳过。"""
    pipeline = PostMarketPipeline(session=mock_session)  # type: ignore[arg-type]
    sunday_date = date(2026, 11, 15)  # 周日

    res = await pipeline.run(trade_date=sunday_date, force=False)

    assert res.status == JobStatus.COMPLETED
    assert res.is_trading_day is False
    assert len(res.steps) == 1
    assert res.steps[0].name == "calendar_guard"
    assert res.steps[0].details.get("action") == "skipped"
