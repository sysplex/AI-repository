"""邮件通知适配器（M10-T02），基于标准 SMTP over STARTTLS 与金融响应式 HTML 模板。"""

from __future__ import annotations

import asyncio
import smtplib
import uuid
from collections.abc import Callable
from email.message import EmailMessage
from typing import Any

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.modules.notify.enums import ChannelType
from app.modules.notify.ports import BaseNotifier, NotificationMessage, NotificationResult

__all__ = ["EmailNotifier"]

_LOGGER = get_logger(__name__)


def _generate_alert_html(message: NotificationMessage) -> str:
    """生成金融质感的响应式 HTML 邮件正文。"""
    symbol_badge = ""
    if message.symbol:
        symbol_badge = (
            '<span style="background:#1e293b;color:#38bdf8;'
            "padding:2px 8px;border-radius:4px;font-weight:bold;"
            f'margin-right:8px;">{message.symbol}</span>'
        )

    kv_rows = ""
    if message.triggered_value:
        rows = []
        for k, v in message.triggered_value.items():
            rows.append(
                '<tr><td style="padding:6px 12px;color:#94a3b8;'
                'font-size:13px;border-bottom:1px solid #334155;">'
                f"{k}</td>"
                '<td style="padding:6px 12px;color:#f8fafc;'
                'font-size:13px;font-weight:600;border-bottom:1px solid #334155;">'
                f"{v}</td></tr>"
            )
        kv_table = "".join(rows)
        kv_rows = (
            '<table style="width:100%;border-collapse:collapse;'
            'margin:16px 0;background:#1e293b;border-radius:6px;overflow:hidden;">'
            f"{kv_table}</table>"
        )

    return f"""<!doctype html>
<html>
<head><meta charset="utf-8"/></head>
<body style="margin:0;padding:24px;background:#090d16;color:#e2e8f0;font-family:sans-serif;">
    <div style="max-width:560px;margin:0 auto;background:#0f172a;border-radius:12px;padding:24px;">
        <div style="border-bottom:1px solid #1e293b;padding-bottom:12px;margin-bottom:16px;">
            <div style="font-size:16px;font-weight:700;color:#38bdf8;">StockPilot 预警通知</div>
        </div>
        <div style="margin-bottom:12px;">
            {symbol_badge}
            <span style="font-size:18px;font-weight:bold;color:#f8fafc;">{message.title}</span>
        </div>
        <div style="color:#cbd5e1;font-size:14px;line-height:1.6;margin-bottom:16px;">
            {message.body}
        </div>
        {kv_rows}
        <div style="border-top:1px solid #1e293b;padding-top:16px;font-size:11px;color:#64748b;">
            本邮件由 StockPilot 平台自动发送。<br/>
            仅供策略研究与模拟验证参考，不构成任何实质性投资建议。市场有风险，投资需谨慎。
        </div>
    </div>
</body>
</html>"""


class EmailNotifier(BaseNotifier):
    """基于 SMTP 的邮件发送器，包含生产真实外发与测试/未配置静默模式。"""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        transport_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._transport_factory = transport_factory
        # 用于测试/离线环境下记录发送的消息列表
        self.sent_messages: list[tuple[str, str, str]] = []

    def _default_transport(self) -> smtplib.SMTP:
        return smtplib.SMTP(
            host=self._settings.smtp_resolved_host,
            port=self._settings.smtp_port,
            timeout=self._settings.smtp_timeout_seconds,
        )

    def _sync_send(self, to_addr: str, subject: str, text_body: str, html_body: str) -> None:
        from_addr = self._settings.smtp_resolved_from
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_addr
        msg.set_content(text_body)
        msg.add_alternative(html_body, subtype="html")

        transport_fn = self._transport_factory or self._default_transport
        with transport_fn() as client:
            if self._settings.smtp_starttls:
                client.starttls()
            if self._settings.smtp_user and self._settings.smtp_password:
                client.login(
                    self._settings.smtp_user,
                    self._settings.smtp_password.get_secret_value(),
                )
            client.send_message(msg)

    async def send(
        self,
        *,
        recipient: str,
        message: NotificationMessage,
        config: dict[str, Any],
        channel_id: uuid.UUID | None = None,
    ) -> NotificationResult:
        """异步发送邮件，无论成功与否绝不抛异常。"""
        target_email = config.get("target_email") or recipient
        subject = f"[StockPilot 预警] {message.title}"
        text_body = f"{message.title}\n\n{message.body}"
        html_body = message.html_body or _generate_alert_html(message)

        # 检查是否已配置真实 SMTP
        if not self._settings.smtp_configured and not self._transport_factory:
            # 未配置 SMTP 时，记录在内存中并不发起网络请求（降级模式）
            self.sent_messages.append((target_email, subject, text_body))
            _LOGGER.info(
                "email.mock_send",
                to=target_email,
                subject=subject,
                msg="SMTP 未配置，邮件已转存内存",
            )
            return NotificationResult(
                channel_type=ChannelType.EMAIL,
                channel_id=channel_id,
                success=True,
            )

        try:
            await asyncio.to_thread(self._sync_send, target_email, subject, text_body, html_body)
            self.sent_messages.append((target_email, subject, text_body))
            _LOGGER.info("email.sent", to=target_email, subject=subject)
            return NotificationResult(
                channel_type=ChannelType.EMAIL,
                channel_id=channel_id,
                success=True,
            )
        except Exception as exc:
            _LOGGER.error("email.failed", to=target_email, subject=subject, error=str(exc))
            return NotificationResult(
                channel_type=ChannelType.EMAIL,
                channel_id=channel_id,
                success=False,
                error_message=str(exc),
            )
