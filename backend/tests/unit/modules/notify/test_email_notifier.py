"""M10-T02 邮件通知适配器单元测试。"""

from __future__ import annotations

import smtplib
import uuid
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.modules.notify.adapters.email_notifier import EmailNotifier, _generate_alert_html
from app.modules.notify.enums import ChannelType
from app.modules.notify.ports import NotificationMessage


@pytest.fixture
def mock_settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://stockpilot:password@localhost:5432/stockpilot",
        redis_url="redis://localhost:6379/0",
        secret_key="x" * 32,
        smtp_user="alerts@stockpilot.com",
        smtp_password=SecretStr("supersecret123"),
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_provider="custom",
    )


class TestEmailNotifier:
    """EmailNotifier 测试集。"""

    def test_generate_alert_html(self) -> None:
        msg = NotificationMessage(
            title="AAPL 突破阻力位",
            body="现价 $235.50 已突破 $230 阻力线",
            symbol="AAPL",
            triggered_value={"current_price": Decimal("235.50"), "target_price": Decimal("230.00")},
        )
        html = _generate_alert_html(msg)
        assert "AAPL" in html
        assert "突破阻力位" in html
        assert "current_price" in html
        assert "235.50" in html
        assert "StockPilot" in html

    @pytest.mark.asyncio
    async def test_send_unconfigured_mode(self) -> None:
        """未配置 SMTP 时转存内存，不发起网络请求且返回成功。"""
        unconfigured_settings = Settings(
            _env_file=None,
            database_url="postgresql+asyncpg://stockpilot:password@localhost:5432/stockpilot",
            redis_url="redis://localhost:6379/0",
            secret_key="x" * 32,
        )
        notifier = EmailNotifier(settings=unconfigured_settings)
        msg = NotificationMessage(title="测试预警", body="这是一条测试通知")

        res = await notifier.send(
            recipient="test@example.com",
            message=msg,
            config={},
            channel_id=uuid.uuid4(),
        )

        assert res.success is True
        assert res.channel_type == ChannelType.EMAIL
        assert len(notifier.sent_messages) == 1
        assert notifier.sent_messages[0][0] == "test@example.com"
        assert "[StockPilot 预警]" in notifier.sent_messages[0][1]

    @pytest.mark.asyncio
    async def test_send_with_smtp_transport_success(self, mock_settings: Settings) -> None:
        """配置有效且会话成功时调用 send_message。"""
        fake_client = MagicMock()
        fake_transport = MagicMock(return_value=fake_client)
        fake_client.__enter__.return_value = fake_client

        notifier = EmailNotifier(settings=mock_settings, transport_factory=fake_transport)
        msg = NotificationMessage(
            title="TSLA 财报提醒",
            body="特斯拉将于明天盘后公布 Q3 财报",
            symbol="TSLA",
        )

        res = await notifier.send(
            recipient="trader@domain.com",
            message=msg,
            config={"target_email": "trader@domain.com"},
        )

        assert res.success is True
        assert fake_client.starttls.called
        assert fake_client.login.called
        assert fake_client.send_message.called

    @pytest.mark.asyncio
    async def test_send_smtp_exception_safe_handling(self, mock_settings: Settings) -> None:
        """SMTP 异常时安全捕获并返回失败结果，绝不抛出异常。"""
        fake_client = MagicMock()
        fake_transport = MagicMock(return_value=fake_client)
        fake_client.__enter__.return_value = fake_client
        fake_client.send_message.side_effect = smtplib.SMTPException("SMTP 连接拒绝")

        notifier = EmailNotifier(settings=mock_settings, transport_factory=fake_transport)
        msg = NotificationMessage(title="NVDA 异动", body="股价波动剧烈")

        res = await notifier.send(
            recipient="trader@domain.com",
            message=msg,
            config={},
        )

        assert res.success is False
        assert "SMTP 连接拒绝" in str(res.error_message)
