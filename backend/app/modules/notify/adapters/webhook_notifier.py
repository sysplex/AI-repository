"""Webhook 通知适配器（M10-T02），支持通用 Webhook、飞书、企业微信、Discord 消息卡片格式。"""

from __future__ import annotations

import uuid
from typing import Any

import httpx

from app.core.logging import get_logger
from app.modules.notify.enums import ChannelType
from app.modules.notify.ports import BaseNotifier, NotificationMessage, NotificationResult

__all__ = ["WebhookNotifier"]

_LOGGER = get_logger(__name__)


def _format_payload(url: str, message: NotificationMessage) -> dict[str, Any]:
    """根据 Webhook 目标域名智能格式化 Payload。"""
    url_lower = url.lower()

    # 1. 飞书 / Lark Webhook
    if "feishu.cn" in url_lower or "larksuite.com" in url_lower:
        elements = [
            [{"tag": "text", "text": f"{message.body}\n"}],
        ]
        if message.triggered_value:
            metrics_text = " | ".join(f"{k}: {v}" for k, v in message.triggered_value.items())
            elements.append([{"tag": "text", "text": f"📊 触发快照: {metrics_text}"}])
        return {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": f"🚨 [StockPilot] {message.title}",
                        "content": elements,
                    }
                }
            },
        }

    # 2. 企业微信 Webhook
    if "qyapi.weixin.qq.com" in url_lower:
        markdown_text = f"### 🚨 [StockPilot 预警] {message.title}\n\n{message.body}"
        if message.symbol:
            markdown_text += f'\n\n> 标的代码：<font color="info">{message.symbol}</font>'
        if message.triggered_value:
            metrics = "\n".join(f"> {k}: **{v}**" for k, v in message.triggered_value.items())
            markdown_text += f"\n\n**触发指标：**\n{metrics}"
        return {
            "msgtype": "markdown",
            "markdown": {"content": markdown_text},
        }

    # 3. Discord Webhook
    if "discord.com" in url_lower or "discordapp.com" in url_lower:
        fields = []
        for k, v in message.triggered_value.items():
            fields.append({"name": str(k), "value": str(v), "inline": True})
        return {
            "content": f"🚨 **[StockPilot] {message.title}**",
            "embeds": [
                {
                    "title": message.title,
                    "description": message.body,
                    "color": 3718648,  # #38bdf8
                    "fields": fields,
                }
            ],
        }

    # 4. 通用 JSON Webhook
    return {
        "event": "stockpilot_alert",
        "title": message.title,
        "body": message.body,
        "symbol": message.symbol,
        "alert_type": message.alert_type,
        "triggered_value": message.triggered_value,
        "meta": message.meta,
    }


class WebhookNotifier(BaseNotifier):
    """基于 HTTP POST 的 Webhook 发送器，带超时保护与智能协议适配。"""

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._client = client
        self._timeout_seconds = timeout_seconds
        # 供单元测试断言
        self.sent_payloads: list[dict[str, Any]] = []

    async def _post(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> tuple[int, str]:
        if self._client is not None:
            res = await self._client.post(
                url,
                json=payload,
                headers=headers,
                timeout=self._timeout_seconds,
            )
            return res.status_code, res.text

        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            res = await client.post(
                url,
                json=payload,
                headers=headers,
            )
            return res.status_code, res.text

    async def send(
        self,
        *,
        recipient: str,
        message: NotificationMessage,
        config: dict[str, Any],
        channel_id: uuid.UUID | None = None,
    ) -> NotificationResult:
        """投递 Webhook，若失败记录原因绝不向外抛异常。"""
        url = config.get("webhook_url") or recipient
        if not url:
            return NotificationResult(
                channel_type=ChannelType.WEBHOOK,
                channel_id=channel_id,
                success=False,
                error_message="缺少 webhook_url 配置",
            )

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if "custom_headers" in config and isinstance(config["custom_headers"], dict):
            headers.update(config["custom_headers"])

        secret_token = config.get("secret_token")
        if secret_token:
            headers["Authorization"] = f"Bearer {secret_token}"

        payload = _format_payload(url, message)

        try:
            status_code, response_text = await self._post(url, payload, headers)
            self.sent_payloads.append({"url": url, "payload": payload, "status": status_code})

            if 200 <= status_code < 300:
                _LOGGER.info("webhook.sent", url=url, status_code=status_code)
                return NotificationResult(
                    channel_type=ChannelType.WEBHOOK,
                    channel_id=channel_id,
                    success=True,
                )

            err = f"HTTP {status_code}: {response_text[:200]}"
            _LOGGER.warning("webhook.http_error", url=url, status_code=status_code, response=err)
            return NotificationResult(
                channel_type=ChannelType.WEBHOOK,
                channel_id=channel_id,
                success=False,
                error_message=err,
            )
        except Exception as exc:
            _LOGGER.error("webhook.failed", url=url, error=str(exc))
            return NotificationResult(
                channel_type=ChannelType.WEBHOOK,
                channel_id=channel_id,
                success=False,
                error_message=str(exc),
            )
