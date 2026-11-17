"""M10-T02 NotificationDispatcher 调度分发器单元测试。"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.notify.dispatcher import NotificationDispatcher
from app.modules.notify.enums import ChannelType, DeliveryStatus
from app.modules.notify.models import AlertHistory, NotificationChannel
from app.modules.notify.ports import BaseNotifier, NotificationMessage, NotificationResult


class FakeNotifier(BaseNotifier):
    """可控制成功/失败的测试 Notifier。"""

    def __init__(self, channel_type: ChannelType, should_succeed: bool = True) -> None:
        self.channel_type = channel_type
        self.should_succeed = should_succeed
        self.calls: list[dict[str, Any]] = []

    async def send(
        self,
        *,
        recipient: str,
        message: NotificationMessage,
        config: dict[str, Any],
        channel_id: uuid.UUID | None = None,
    ) -> NotificationResult:
        self.calls.append({"recipient": recipient, "message": message, "config": config})
        if self.should_succeed:
            return NotificationResult(
                channel_type=self.channel_type,
                channel_id=channel_id,
                success=True,
            )
        return NotificationResult(
            channel_type=self.channel_type,
            channel_id=channel_id,
            success=False,
            error_message="投递模拟失败",
        )


class TestNotificationDispatcher:
    """NotificationDispatcher 测试集。"""

    @pytest.mark.asyncio
    async def test_dispatch_fallback_to_in_app_when_no_channels(self) -> None:
        """用户未配置任何渠道时自动降级走站内信投递。"""
        fake_session = AsyncMock()
        fake_session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        fake_session.execute.return_value = mock_result

        in_app = FakeNotifier(ChannelType.IN_APP, should_succeed=True)
        dispatcher = NotificationDispatcher(in_app_notifier=in_app)

        user_id = uuid.uuid4()
        msg = NotificationMessage(title="提醒标题", body="内容")

        results = await dispatcher.dispatch(user_id=user_id, message=msg, session=fake_session)

        assert len(results) == 1
        assert results[0].channel_type == ChannelType.IN_APP
        assert results[0].success is True
        assert len(in_app.calls) == 1
        assert in_app.calls[0]["recipient"] == str(user_id)

    @pytest.mark.asyncio
    async def test_dispatch_multi_channels_concurrent(self) -> None:
        """用户配置多渠道时并发分发。"""
        user_id = uuid.uuid4()
        ch_email_id = uuid.uuid4()
        ch_webhook_id = uuid.uuid4()

        ch_email = NotificationChannel(
            id=ch_email_id,
            user_id=user_id,
            channel_type=ChannelType.EMAIL.value,
            name="邮件",
            config={"target_email": "user@example.com"},
            is_enabled=True,
        )
        ch_webhook = NotificationChannel(
            id=ch_webhook_id,
            user_id=user_id,
            channel_type=ChannelType.WEBHOOK.value,
            name="飞书",
            config={"webhook_url": "https://open.feishu.cn/..."},
            is_enabled=True,
        )

        fake_session = AsyncMock()
        fake_session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [ch_email, ch_webhook]
        fake_session.execute.return_value = mock_result

        email_notifier = FakeNotifier(ChannelType.EMAIL, should_succeed=True)
        webhook_notifier = FakeNotifier(ChannelType.WEBHOOK, should_succeed=True)
        dispatcher = NotificationDispatcher(
            email_notifier=email_notifier,
            webhook_notifier=webhook_notifier,
        )

        msg = NotificationMessage(
            title="AAPL 突破",
            body="现价 $235",
            alert_id=uuid.uuid4(),
            symbol="AAPL",
        )

        results = await dispatcher.dispatch(user_id=user_id, message=msg, session=fake_session)

        assert len(results) == 2
        assert all(r.success for r in results)
        assert len(email_notifier.calls) == 1
        assert len(webhook_notifier.calls) == 1

        # 验证审计流水已写入
        assert fake_session.add.called
        history_arg = fake_session.add.call_args[0][0]
        assert isinstance(history_arg, AlertHistory)
        assert history_arg.delivery_status == DeliveryStatus.SENT.value
        assert history_arg.symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_dispatch_partial_failure_history(self) -> None:
        """部分渠道失败时记录 partial 状态。"""
        user_id = uuid.uuid4()
        ch1 = NotificationChannel(
            id=uuid.uuid4(),
            user_id=user_id,
            channel_type=ChannelType.EMAIL.value,
            name="邮件",
            config={},
            is_enabled=True,
        )
        ch2 = NotificationChannel(
            id=uuid.uuid4(),
            user_id=user_id,
            channel_type=ChannelType.WEBHOOK.value,
            name="Webhook",
            config={},
            is_enabled=True,
        )

        fake_session = AsyncMock()
        fake_session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [ch1, ch2]
        fake_session.execute.return_value = mock_result

        email_notifier = FakeNotifier(ChannelType.EMAIL, should_succeed=True)
        webhook_notifier = FakeNotifier(ChannelType.WEBHOOK, should_succeed=False)
        dispatcher = NotificationDispatcher(
            email_notifier=email_notifier,
            webhook_notifier=webhook_notifier,
        )

        msg = NotificationMessage(title="预警", body="内容", alert_id=uuid.uuid4())
        results = await dispatcher.dispatch(user_id=user_id, message=msg, session=fake_session)

        assert len(results) == 2
        history_arg = fake_session.add.call_args[0][0]
        assert history_arg.delivery_status == DeliveryStatus.PARTIAL.value

    @pytest.mark.asyncio
    async def test_dispatch_all_failed_history(self) -> None:
        """全部失败时记录 failed 状态。"""
        user_id = uuid.uuid4()
        ch = NotificationChannel(
            id=uuid.uuid4(),
            user_id=user_id,
            channel_type=ChannelType.WEBHOOK.value,
            name="Webhook",
            config={},
            is_enabled=True,
        )

        fake_session = AsyncMock()
        fake_session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [ch]
        fake_session.execute.return_value = mock_result

        webhook_notifier = FakeNotifier(ChannelType.WEBHOOK, should_succeed=False)
        dispatcher = NotificationDispatcher(webhook_notifier=webhook_notifier)

        msg = NotificationMessage(title="预警", body="内容", alert_id=uuid.uuid4())
        results = await dispatcher.dispatch(user_id=user_id, message=msg, session=fake_session)

        assert len(results) == 1
        assert results[0].success is False
        history_arg = fake_session.add.call_args[0][0]
        assert history_arg.delivery_status == DeliveryStatus.FAILED.value

    @pytest.mark.asyncio
    async def test_dispatch_critical_exception_safe_fallback(self) -> None:
        """关键异常（如数据库连接断开）安全捕获，返回失败列表，绝不抛崩调用方。"""
        fake_session = AsyncMock()
        fake_session.add = MagicMock()
        fake_session.execute.side_effect = RuntimeError("DB 异常崩溃")

        dispatcher = NotificationDispatcher()
        user_id = uuid.uuid4()
        msg = NotificationMessage(title="重要提醒", body="内容")

        results = await dispatcher.dispatch(user_id=user_id, message=msg, session=fake_session)

        assert len(results) == 1
        assert results[0].success is False
        assert "分发关键异常" in str(results[0].error_message)
