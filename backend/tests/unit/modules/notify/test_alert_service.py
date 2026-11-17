"""单元测试：AlertService 业务逻辑、规则生命周期与触发评估引擎（M10-T03）。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.modules.notify.dispatcher import NotificationDispatcher
from app.modules.notify.enums import (
    AlertStatus,
    AlertType,
    ChannelType,
)
from app.modules.notify.models import Alert, AlertHistory, NotificationChannel
from app.modules.notify.ports import BaseNotifier, NotificationMessage, NotificationResult
from app.modules.notify.schemas import (
    AlertCreate,
    AlertUpdate,
    NotificationChannelCreate,
    NotificationChannelUpdate,
)
from app.modules.notify.service import AlertService


class FakeSession:
    """轻量内存 AsyncSession 模拟器，支持基础 CRUD 与查询过滤。"""

    def __init__(self) -> None:
        self.entities: dict[uuid.UUID, Any] = {}
        self.added: list[Any] = []
        self.deleted: list[Any] = []

    def add(self, entity: Any) -> None:
        if not getattr(entity, "id", None):
            entity.id = uuid.uuid4()
        if not getattr(entity, "created_at", None):
            entity.created_at = datetime.now(UTC)
        if not getattr(entity, "updated_at", None):
            entity.updated_at = datetime.now(UTC)
        self.entities[entity.id] = entity
        self.added.append(entity)

    async def delete(self, entity: Any) -> None:
        if entity.id in self.entities:
            del self.entities[entity.id]
        self.deleted.append(entity)

    async def commit(self) -> None:
        pass

    async def refresh(self, entity: Any) -> None:
        pass

    async def flush(self) -> None:
        pass

    async def execute(self, stmt: Any) -> Any:
        mock_res = MagicMock()
        items = list(self.entities.values())

        filtered: list[Any]
        stmt_str = str(stmt).lower()
        if "from notification_channels" in stmt_str:
            filtered = [e for e in items if isinstance(e, NotificationChannel)]
        elif "from alert_history" in stmt_str:
            filtered = [e for e in items if isinstance(e, AlertHistory)]
        elif "from alerts" in stmt_str:
            filtered = [e for e in items if isinstance(e, Alert)]
        else:
            filtered = items

        # 根据编译参数做精确 id 与 user_id 过滤
        try:
            params = stmt.compile().params
            for k, v in params.items():
                if k.startswith("user_id"):
                    filtered = [e for e in filtered if getattr(e, "user_id", None) == v]
                elif k == "id" or k.startswith("id_"):
                    filtered = [e for e in filtered if getattr(e, "id", None) == v]
        except Exception:  # noqa: S110
            pass

        mock_res.scalars.return_value.all.return_value = filtered
        mock_res.scalar_one_or_none.return_value = filtered[0] if filtered else None
        return mock_res


class MockNotifier(BaseNotifier):
    """测试用通知适配器。"""

    def __init__(self, channel_type: ChannelType, success: bool = True) -> None:
        self._type = channel_type
        self.success = success
        self.sent_messages: list[NotificationMessage] = []

    @property
    def channel_type(self) -> ChannelType:
        return self._type

    async def send(
        self,
        recipient: str,
        message: NotificationMessage,
        config: dict[str, Any],
        channel_id: uuid.UUID | None = None,
    ) -> NotificationResult:
        self.sent_messages.append(message)
        return NotificationResult(
            channel_type=self._type,
            channel_id=channel_id,
            success=self.success,
        )


@pytest.fixture
def fake_session() -> FakeSession:
    return FakeSession()


@pytest.fixture
def mock_dispatcher() -> NotificationDispatcher:
    dispatcher = NotificationDispatcher()
    mock_email = MockNotifier(ChannelType.EMAIL, success=True)
    mock_webhook = MockNotifier(ChannelType.WEBHOOK, success=True)
    mock_in_app = MockNotifier(ChannelType.IN_APP, success=True)
    dispatcher.register_notifier(ChannelType.EMAIL, mock_email)
    dispatcher.register_notifier(ChannelType.WEBHOOK, mock_webhook)
    dispatcher.register_notifier(ChannelType.IN_APP, mock_in_app)
    return dispatcher


@pytest.fixture
def alert_service(
    fake_session: FakeSession, mock_dispatcher: NotificationDispatcher
) -> AlertService:
    return AlertService(session=fake_session, dispatcher=mock_dispatcher)  # type: ignore[arg-type]


class TestAlertServiceCRUD:
    """AlertService 基础规则与渠道增删改查测试。"""

    @pytest.mark.asyncio
    async def test_session_none_raises_value_error(self) -> None:
        svc = AlertService(session=None)
        with pytest.raises(ValueError, match="AsyncSession 必须传入"):
            await svc.list_alerts(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_create_and_get_alert(
        self, alert_service: AlertService, fake_session: FakeSession
    ) -> None:
        user_id = uuid.uuid4()
        alert_in = AlertCreate(
            symbol="AAPL",
            alert_type=AlertType.PRICE,
            title="AAPL 突破 230",
            conditions={"direction": "cross_above", "target_price": 230.0},
            cooldown_minutes=120,
        )
        read_alert = await alert_service.create_alert(user_id, alert_in)
        assert read_alert.symbol == "AAPL"
        assert read_alert.title == "AAPL 突破 230"
        assert read_alert.status == AlertStatus.ACTIVE
        assert read_alert.trigger_count == 0

        # 读取
        fetched = await alert_service.get_alert(user_id, read_alert.id)
        assert fetched is not None
        assert fetched.id == read_alert.id

    @pytest.mark.asyncio
    async def test_get_alert_not_found(self, alert_service: AlertService) -> None:
        fetched = await alert_service.get_alert(uuid.uuid4(), uuid.uuid4())
        assert fetched is None

    @pytest.mark.asyncio
    async def test_create_alert_invalid_conditions_raises(
        self, alert_service: AlertService
    ) -> None:
        user_id = uuid.uuid4()
        # 缺少 target_price
        alert_in = AlertCreate(
            symbol="AAPL",
            alert_type=AlertType.PRICE,
            title="Invalid Alert",
            conditions={"direction": "cross_above"},
        )
        with pytest.raises(ValidationError):
            await alert_service.create_alert(user_id, alert_in)

    @pytest.mark.asyncio
    async def test_update_and_delete_alert(
        self, alert_service: AlertService, fake_session: FakeSession
    ) -> None:
        user_id = uuid.uuid4()
        alert_in = AlertCreate(
            symbol="TSLA",
            alert_type=AlertType.PRICE,
            title="TSLA 跌破 200",
            conditions={"direction": "cross_below", "target_price": 200.0},
        )
        created = await alert_service.create_alert(user_id, alert_in)

        # 更新
        updated = await alert_service.update_alert(
            user_id, created.id, AlertUpdate(title="TSLA 强支撑 200", status=AlertStatus.DISABLED)
        )
        assert updated is not None
        assert updated.title == "TSLA 强支撑 200"
        assert updated.status == AlertStatus.DISABLED

        # 更新不存在的 alert
        non_existent = await alert_service.update_alert(
            user_id, uuid.uuid4(), AlertUpdate(title="X")
        )
        assert non_existent is None

        # 删除
        deleted = await alert_service.delete_alert(user_id, created.id)
        assert deleted is True

        # 再次删除返回 False
        deleted_again = await alert_service.delete_alert(user_id, created.id)
        assert deleted_again is False

    @pytest.mark.asyncio
    async def test_list_alerts_and_history(
        self, alert_service: AlertService, fake_session: FakeSession
    ) -> None:
        user_id = uuid.uuid4()
        # 创建几条
        await alert_service.create_alert(
            user_id,
            AlertCreate(
                symbol="MSFT",
                alert_type=AlertType.PRICE,
                title="MSFT 提醒",
                conditions={"direction": "cross_above", "target_price": 450.0},
            ),
        )
        alerts = await alert_service.list_alerts(user_id, symbol="MSFT")
        assert len(alerts) >= 1

        # 历史记录查询
        history = await alert_service.list_history(user_id)
        assert isinstance(history, list)

    @pytest.mark.asyncio
    async def test_channel_crud(self, alert_service: AlertService) -> None:
        user_id = uuid.uuid4()
        c_in = NotificationChannelCreate(
            channel_type=ChannelType.WEBHOOK,
            name="飞书运维群",
            config={"webhook_url": "https://open.feishu.cn/hook/123"},
        )
        created = await alert_service.create_channel(user_id, c_in)
        assert created.name == "飞书运维群"
        assert created.channel_type == ChannelType.WEBHOOK

        # 列表
        channels = await alert_service.list_channels(user_id)
        assert len(channels) >= 1

        # 查单条
        fetched = await alert_service.get_channel(user_id, created.id)
        assert fetched is not None
        assert fetched.id == created.id

        # 查不存在
        not_found = await alert_service.get_channel(user_id, uuid.uuid4())
        assert not_found is None

        # 更新
        up = await alert_service.update_channel(
            user_id, created.id, NotificationChannelUpdate(name="更新后群名")
        )
        assert up is not None
        assert up.name == "更新后群名"

        # 更新不存在
        up_none = await alert_service.update_channel(
            user_id, uuid.uuid4(), NotificationChannelUpdate(name="None")
        )
        assert up_none is None

        # 删除
        ok = await alert_service.delete_channel(user_id, created.id)
        assert ok is True

        # 删除不存在
        ok_again = await alert_service.delete_channel(user_id, created.id)
        assert ok_again is False


class TestBatchCreateThesisBreakers:
    """批量将 M7 论文破裂项转为监控规则测试。"""

    @pytest.mark.asyncio
    async def test_batch_create_thesis_breakers_dict(self, alert_service: AlertService) -> None:
        user_id = uuid.uuid4()
        m7_breakers = [
            {
                "condition": "毛利率跌破 40% 说明护城河受损",
                "metric": "gross_margin",
                "threshold": "< 40%",
                "data_field": "fundamentals.gross_margin",
            },
            {
                "condition": "市盈率超过 50 倍发生严重高估",
                "metric": "pe_trailing",
                "threshold": "> 50",
                "data_field": "fundamentals.pe_trailing",
            },
            {
                "condition": "营收增长转负",
                "metric": "revenue_growth",
                "operator": "lt",
                "threshold": "0.0",
                "data_field": "fundamentals.revenue_growth",
            },
        ]
        created_alerts = await alert_service.batch_create_thesis_breakers(
            user_id=user_id,
            symbol="NVDA",
            breakers=m7_breakers,
            cooldown_minutes=720,
        )
        assert len(created_alerts) == 3
        for a in created_alerts:
            assert a.symbol == "NVDA"
            assert a.alert_type == AlertType.THESIS_BREAKER
            assert a.cooldown_minutes == 720
            assert a.status == AlertStatus.ACTIVE
            assert "metric" in a.conditions

    @pytest.mark.asyncio
    async def test_batch_create_thesis_breakers_objects(self, alert_service: AlertService) -> None:
        user_id = uuid.uuid4()

        @dataclass
        class MockBreakerItem:
            metric: str
            condition: str
            threshold: str
            data_field: str
            operator: str | None = None

        items = [
            MockBreakerItem(
                metric="net_margin",
                condition="净利率低于 10%",
                threshold="< 10%",
                data_field="fundamentals.net_margin",
            ),
        ]
        created = await alert_service.batch_create_thesis_breakers(
            user_id=user_id,
            symbol="GOOGL",
            breakers=items,
        )
        assert len(created) == 1
        assert created[0].symbol == "GOOGL"


class TestAlertEvaluationWorkflow:
    """扫描求值引擎完整联动测试。"""

    @pytest.mark.asyncio
    async def test_evaluate_alerts_triggering_and_cooldown(
        self,
        alert_service: AlertService,
        fake_session: FakeSession,
    ) -> None:
        user_id = uuid.uuid4()

        # 1. 创建价格规则：AAPL 突破 230
        price_alert = Alert(
            id=uuid.uuid4(),
            user_id=user_id,
            symbol="AAPL",
            alert_type=AlertType.PRICE.value,
            title="AAPL 突破 230",
            conditions={"direction": "cross_above", "target_price": 230.0},
            status=AlertStatus.ACTIVE.value,
            trigger_count=0,
            cooldown_minutes=60,
        )
        fake_session.add(price_alert)

        # 2. 创建论文破裂规则：NVDA 净利率跌破 15%
        breaker_alert = Alert(
            id=uuid.uuid4(),
            user_id=user_id,
            symbol="NVDA",
            alert_type=AlertType.THESIS_BREAKER.value,
            title="NVDA 净利率破裂",
            conditions={
                "metric": "net_margin",
                "operator": "lt",
                "threshold": "0.15",
                "data_field": "fundamentals.net_margin",
                "description": "净利率跌破 15%",
            },
            status=AlertStatus.ACTIVE.value,
            trigger_count=0,
            cooldown_minutes=60,
        )
        fake_session.add(breaker_alert)

        # 3. 准备行情快照：AAPL 涨至 232（触发），NVDA 净利率 0.25（健康未触发）
        market_context = {
            "AAPL": {
                "current_price": Decimal("232.0"),
                "previous_price": Decimal("225.0"),
            },
            "NVDA": {
                "fundamentals": {"net_margin": Decimal("0.25")},
            },
        }

        as_of = datetime.now(UTC)
        results = await alert_service.evaluate_alerts(
            market_context=market_context,
            as_of=as_of,
        )

        # AAPL 触发，NVDA 未触发
        assert len(results) == 1
        trig_alert, eval_res = results[0]
        assert trig_alert.id == price_alert.id
        assert eval_res.triggered is True
        assert price_alert.status == AlertStatus.COOLDOWN.value
        assert price_alert.trigger_count == 1
        assert price_alert.last_triggered_at == as_of

        # 4. 再次评估（处于冷却时间内），应当被抑制跳过
        subsequent_time = as_of + timedelta(minutes=30)
        results_2 = await alert_service.evaluate_alerts(
            market_context=market_context,
            as_of=subsequent_time,
        )
        assert len(results_2) == 0

        # 5. 冷却时间（60分钟）过去后，状态恢复并可再次触发
        after_cooldown_time = as_of + timedelta(minutes=70)
        results_3 = await alert_service.evaluate_alerts(
            market_context=market_context,
            as_of=after_cooldown_time,
        )
        assert len(results_3) == 1
        assert price_alert.trigger_count == 2
