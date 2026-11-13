"""Q3 裁决（2026-11-13）后的真实投递：Gmail / Outlook SMTP over STARTTLS。

零第三方依赖：标准库 `smtplib` + `email.message.EmailMessage`，同步会话通过
`asyncio.to_thread` 移出事件循环（ADR-012：不在事件循环里执行阻塞 IO）。
`SMTP_PROVIDER=gmail|outlook` 只影响主机解析，本类不关心厂商差异。

安全约定：

* 邮件正文含一次性重置令牌，**绝不写入任何日志**；成功只记收件人 SHA-256 前缀。
* SMTP 故障收敛为 error 日志并静默返回：`request_password_reset` 对「账号存在」
  与「账号不存在」必须返回同一个 202 响应体，投递异常若冒泡成 500 会构成账号枚举。
  代价是用户收不到邮件却看到 202 —— 由 `mail.smtp.failed` + `incident` 供告警发现，
  接入后台队列与重试后应改为「入队即成功」（见 `docs/acceptance/M1.md §7`）。
"""

from __future__ import annotations

import asyncio
import hashlib
import smtplib
import ssl
from collections.abc import Callable
from email.message import EmailMessage
from typing import Any, Final

from pydantic import SecretStr

from app.core.logging import get_logger

__all__ = ["SmtpMailSender"]

_LOGGER = get_logger(__name__)
_DIGEST_PREFIX: Final[int] = 12


class SmtpMailSender:
    """`MailSender` 端口的 SMTP 实现；`transport_factory` 仅供测试注入假会话。"""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        user: str,
        password: SecretStr,
        sender: str,
        use_starttls: bool = True,
        timeout: float = 10.0,
        transport_factory: Callable[[], Any] | None = None,
        logger: Any | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._sender = sender
        self._use_starttls = use_starttls
        self._timeout = timeout
        self._transport_factory = transport_factory or self._default_transport
        self._logger = logger if logger is not None else _LOGGER

    def _default_transport(self) -> Any:
        """每封信新建连接：重置邮件是低频操作，避免长连接上长期驻留凭据。"""
        return smtplib.SMTP(self._host, self._port, timeout=self._timeout)

    async def send(self, *, to: str, subject: str, body: str) -> None:
        """发一封纯文本邮件；投递失败不冒泡（原因见模块 docstring）。"""
        try:
            await asyncio.to_thread(self._deliver, to, subject, body)
        except (smtplib.SMTPException, OSError) as exc:
            self._logger.error(
                "mail.smtp.failed",
                host=self._host,
                error_type=type(exc).__name__,
                incident="mail_delivery_failed",
                detail="SMTP 投递失败，对外响应保持不变以避免账号枚举",
            )
            return
        digest = hashlib.sha256(to.encode("utf-8")).hexdigest()[:_DIGEST_PREFIX]
        self._logger.info(
            "mail.smtp.sent",
            host=self._host,
            port=self._port,
            recipient_digest=digest,
            network_calls=1,
        )

    def _deliver(self, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)

        with self._transport_factory() as smtp:
            smtp.ehlo()
            if self._use_starttls:
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            secret = self._password.get_secret_value()
            if self._user and secret:
                smtp.login(self._user, secret)
            smtp.send_message(message)
