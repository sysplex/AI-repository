"""M10-T01 Notify 领域模型与 Schema 单元测试。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.notify.enums import (
    AlertStatus,
    AlertType,
    ChannelType,
    ComparisonOperator,
    DeliveryStatus,
    PriceDirection,
)
from app.modules.notify.models import (
    Alert,
    AlertHistory,
    NotificationChannel,
)
from app.modules.notify.schemas import (
    AlertCreate,
    AlertHistoryRead,
    AlertRead,
    AlertUpdate,
    EarningsDateCondition,
    NotificationChannelCreate,
    NotificationChannelRead,
    NotificationChannelUpdate,
    PriceCondition,
    TechnicalSignalCondition,
    ThesisBreakerCondition,
)


class TestNotifyEnums:
    """枚举值规范测试。"""

    def test_enum_values(self) -> None:
        assert ChannelType.EMAIL.value == "email"
        assert ChannelType.WEBHOOK.value == "webhook"
        assert ChannelType.IN_APP.value == "in_app"

        assert AlertType.PRICE.value == "price"
        assert AlertType.TECHNICAL_SIGNAL.value == "technical_signal"
        assert AlertType.EARNINGS_DATE.value == "earnings_date"
        assert AlertType.THESIS_BREAKER.value == "thesis_breaker"

        assert AlertStatus.ACTIVE.value == "active"
        assert AlertStatus.TRIGGERED.value == "triggered"
        assert AlertStatus.DISABLED.value == "disabled"
        assert AlertStatus.COOLDOWN.value == "cooldown"

        assert PriceDirection.CROSS_ABOVE.value == "cross_above"
        assert PriceDirection.CROSS_BELOW.value == "cross_below"

        assert ComparisonOperator.LT.value == "lt"
        assert ComparisonOperator.GTE.value == "gte"

        assert DeliveryStatus.SENT.value == "sent"
        assert DeliveryStatus.PARTIAL.value == "partial"
        assert DeliveryStatus.FAILED.value == "failed"


class TestConditionSchemas:
    """条件 Schema 校验测试。"""

    def test_price_condition_valid(self) -> None:
        cond = PriceCondition(direction=PriceDirection.CROSS_ABOVE, target_price=Decimal("230.50"))
        assert cond.direction == PriceDirection.CROSS_ABOVE
        assert cond.target_price == Decimal("230.50")

    def test_price_condition_invalid_zero(self) -> None:
        with pytest.raises(ValidationError):
            PriceCondition(direction=PriceDirection.CROSS_BELOW, target_price=Decimal("0"))

    def test_technical_signal_condition(self) -> None:
        cond = TechnicalSignalCondition(
            indicator="RSI",
            operator=ComparisonOperator.LT,
            threshold=Decimal("30"),
            parameters={"period": 14},
        )
        assert cond.indicator == "RSI"
        assert cond.operator == ComparisonOperator.LT
        assert cond.threshold == Decimal("30")
        assert cond.parameters["period"] == 14

    def test_earnings_date_condition(self) -> None:
        cond = EarningsDateCondition(days_before=3)
        assert cond.days_before == 3

    def test_earnings_date_condition_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            EarningsDateCondition(days_before=35)

    def test_thesis_breaker_condition(self) -> None:
        cond = ThesisBreakerCondition(
            metric="gross_margin",
            operator=ComparisonOperator.LT,
            threshold=Decimal("0.40"),
            description="毛利率跌破40%",
        )
        assert cond.metric == "gross_margin"
        assert cond.threshold == Decimal("0.40")
        assert cond.description == "毛利率跌破40%"


class TestNotificationChannelSchemas:
    """渠道管理 Schema 测试。"""

    def test_create_email_channel(self) -> None:
        req = NotificationChannelCreate(
            channel_type=ChannelType.EMAIL,
            name="我的交易告警邮箱",
            config={"target_email": "trader@example.com"},
            is_enabled=True,
        )
        assert req.channel_type == ChannelType.EMAIL
        assert req.name == "我的交易告警邮箱"
        assert req.config["target_email"] == "trader@example.com"
        assert req.is_enabled is True

    def test_create_webhook_channel(self) -> None:
        req = NotificationChannelCreate(
            channel_type=ChannelType.WEBHOOK,
            name="企微群机器人",
            config={"webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"},
        )
        assert req.channel_type == ChannelType.WEBHOOK
        assert req.is_enabled is True

    def test_update_channel(self) -> None:
        upd = NotificationChannelUpdate(name="新名字", is_enabled=False)
        assert upd.name == "新名字"
        assert upd.is_enabled is False
        assert upd.config is None

    def test_read_channel(self) -> None:
        cid = uuid.uuid4()
        uid = uuid.uuid4()
        now = datetime.now(UTC)
        read = NotificationChannelRead(
            id=cid,
            user_id=uid,
            channel_type=ChannelType.IN_APP,
            name="站内信",
            config={},
            is_enabled=True,
            created_at=now,
            updated_at=now,
        )
        assert read.id == cid
        assert read.user_id == uid
        assert read.name == "站内信"


class TestAlertSchemas:
    """提醒规则 Schema 测试。"""

    def test_create_alert_normalize_symbol(self) -> None:
        req = AlertCreate(
            symbol="  aapl  ",
            alert_type=AlertType.PRICE,
            title="苹果股价突破250美元",
            conditions={"direction": "cross_above", "target_price": "250.00"},
            cooldown_minutes=60,
        )
        assert req.symbol == "AAPL"
        assert req.alert_type == AlertType.PRICE
        assert req.cooldown_minutes == 60
        assert req.channel_ids == []

    def test_create_market_alert_empty_symbol(self) -> None:
        req = AlertCreate(
            symbol=None,
            alert_type=AlertType.TECHNICAL_SIGNAL,
            title="大盘全市场异动",
            conditions={"indicator": "MARKET_BREADTH", "operator": "lt", "threshold": "20"},
        )
        assert req.symbol is None

    def test_alert_update(self) -> None:
        upd = AlertUpdate(status=AlertStatus.DISABLED, cooldown_minutes=720)
        assert upd.status == AlertStatus.DISABLED
        assert upd.cooldown_minutes == 720

    def test_alert_read(self) -> None:
        aid = uuid.uuid4()
        uid = uuid.uuid4()
        now = datetime.now(UTC)
        read = AlertRead(
            id=aid,
            user_id=uid,
            symbol="MSFT",
            alert_type=AlertType.THESIS_BREAKER,
            title="微软论文破裂监控",
            conditions={"metric": "revenue_growth", "operator": "lt", "threshold": "0.05"},
            channel_ids=["channel-1"],
            status=AlertStatus.ACTIVE,
            last_triggered_at=None,
            trigger_count=0,
            cooldown_minutes=1440,
            created_at=now,
            updated_at=now,
        )
        assert read.id == aid
        assert read.symbol == "MSFT"
        assert read.status == AlertStatus.ACTIVE
        assert read.last_triggered_at is None

    def test_alert_history_read(self) -> None:
        hid = uuid.uuid4()
        aid = uuid.uuid4()
        uid = uuid.uuid4()
        now = datetime.now(UTC)
        hist = AlertHistoryRead(
            id=hid,
            alert_id=aid,
            user_id=uid,
            symbol="NVDA",
            alert_type=AlertType.PRICE,
            triggered_value={"current_price": "145.20", "target_price": "145.00"},
            message="NVDA 价格突破 145 美元！当前价格 145.20",
            delivery_status=DeliveryStatus.SENT,
            delivered_channels=[{"channel": "email", "status": "ok"}],
            created_at=now,
        )
        assert hist.id == hid
        assert hist.delivery_status == DeliveryStatus.SENT
        assert len(hist.delivered_channels) == 1


class TestNotifyOrmModels:
    """ORM 实体模型属性与表配置测试。"""

    def test_notification_channel_orm_instantiation(self) -> None:
        uid = uuid.uuid4()
        channel = NotificationChannel(
            user_id=uid,
            channel_type="email",
            name="邮件通知",
            config={"email": "user@example.com"},
            is_enabled=True,
        )
        assert channel.user_id == uid
        assert channel.channel_type == "email"
        assert channel.__tablename__ == "notification_channels"

    def test_alert_orm_instantiation(self) -> None:
        uid = uuid.uuid4()
        alert = Alert(
            user_id=uid,
            symbol="TSLA",
            alert_type="price",
            title="特斯拉目标价提醒",
            conditions={"target_price": 250},
            channel_ids=["ch-1"],
            status="active",
            trigger_count=0,
            cooldown_minutes=1440,
        )
        assert alert.symbol == "TSLA"
        assert alert.trigger_count == 0
        assert alert.__tablename__ == "alerts"

    def test_alert_history_orm_instantiation(self) -> None:
        aid = uuid.uuid4()
        uid = uuid.uuid4()
        history = AlertHistory(
            alert_id=aid,
            user_id=uid,
            symbol="AAPL",
            alert_type="thesis_breaker",
            triggered_value={"gross_margin": 0.38},
            message="AAPL 毛利率跌破 40% 警戒线",
            delivery_status="sent",
            delivered_channels=[{"channel": "webhook"}],
        )
        assert history.alert_id == aid
        assert history.symbol == "AAPL"
        assert history.__tablename__ == "alert_history"
