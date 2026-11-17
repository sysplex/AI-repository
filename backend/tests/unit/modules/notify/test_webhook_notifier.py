"""M10-T02 Webhook 通知适配器单元测试。"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import httpx
import pytest

from app.modules.notify.adapters.webhook_notifier import WebhookNotifier, _format_payload
from app.modules.notify.enums import ChannelType
from app.modules.notify.ports import NotificationMessage


class TestWebhookNotifier:
    """WebhookNotifier 测试集。"""

    def test_format_feishu_payload(self) -> None:
        msg = NotificationMessage(
            title="AAPL 破位预警",
            body="均线死叉已形成",
            symbol="AAPL",
            triggered_value={"ma5": 220, "ma20": 225},
        )
        payload = _format_payload("https://open.feishu.cn/open-apis/bot/v2/hook/xxx", msg)
        assert payload["msg_type"] == "post"
        assert "AAPL" in str(payload["content"])

    def test_format_wecom_payload(self) -> None:
        msg = NotificationMessage(
            title="MSFT 论文破裂",
            body="毛利率跌破阈值",
            symbol="MSFT",
            triggered_value={"gross_margin": 0.38},
        )
        payload = _format_payload("https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx", msg)
        assert payload["msgtype"] == "markdown"
        assert "MSFT" in payload["markdown"]["content"]

    def test_format_discord_payload(self) -> None:
        msg = NotificationMessage(
            title="NVDA 目标价到达",
            body="目标价 145 已触达",
            symbol="NVDA",
            triggered_value={"target": 145},
        )
        payload = _format_payload("https://discord.com/api/webhooks/xxx/yyy", msg)
        assert "content" in payload
        assert "embeds" in payload
        assert payload["embeds"][0]["title"] == "NVDA 目标价到达"

    def test_format_generic_payload(self) -> None:
        msg = NotificationMessage(
            title="常规提醒",
            body="系统通用通知",
            symbol="SPY",
        )
        payload = _format_payload("https://api.mycompany.com/webhook", msg)
        assert payload["event"] == "stockpilot_alert"
        assert payload["symbol"] == "SPY"

    @pytest.mark.asyncio
    async def test_send_success(self) -> None:
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = '{"code": 0, "msg": "success"}'
        mock_client.post.return_value = mock_response

        notifier = WebhookNotifier(client=mock_client)
        msg = NotificationMessage(title="买入信号", body="RSI 超卖反弹")

        res = await notifier.send(
            recipient="https://api.mycompany.com/webhook",
            message=msg,
            config={"secret_token": "secret123"},
            channel_id=uuid.uuid4(),
        )

        assert res.success is True
        assert res.channel_type == ChannelType.WEBHOOK
        assert mock_client.post.called
        headers = mock_client.post.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer secret123"

    @pytest.mark.asyncio
    async def test_send_http_error_safe_handling(self) -> None:
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = AsyncMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_client.post.return_value = mock_response

        notifier = WebhookNotifier(client=mock_client)
        msg = NotificationMessage(title="测试", body="测试错误")

        res = await notifier.send(
            recipient="https://api.mycompany.com/webhook",
            message=msg,
            config={},
        )

        assert res.success is False
        assert "HTTP 500" in str(res.error_message)

    @pytest.mark.asyncio
    async def test_send_network_exception_safe_handling(self) -> None:
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.side_effect = httpx.ConnectTimeout("网络连接超时")

        notifier = WebhookNotifier(client=mock_client)
        msg = NotificationMessage(title="测试超时", body="测试超时")

        res = await notifier.send(
            recipient="https://api.mycompany.com/webhook",
            message=msg,
            config={},
        )

        assert res.success is False
        assert "网络连接超时" in str(res.error_message)

    @pytest.mark.asyncio
    async def test_send_missing_url(self) -> None:
        notifier = WebhookNotifier()
        msg = NotificationMessage(title="测试", body="无地址")

        res = await notifier.send(
            recipient="",
            message=msg,
            config={},
        )

        assert res.success is False
        assert "缺少 webhook_url" in str(res.error_message)
