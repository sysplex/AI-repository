"""本地邮件投递适配器（T03）：测试用内存实现、本地联调用日志实现。

Q3 已于 2026-11-13 裁决为 Gmail / Outlook SMTP，真实投递见 `smtp_mail.py`；
本文件只保留「零网络调用」的两个实现，供 `ci` 与未配置 SMTP 的 `local` 使用。
**生产禁用 `LoggingMailSender`**：邮件正文含一次性重置令牌，只应在本地/测试环境
出现；未配置 SMTP 的非本地环境会由组合根打 error 级占位告警。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.logging import get_logger

__all__ = ["InMemoryMailSender", "LoggingMailSender", "MailMessage"]


@dataclass(frozen=True, slots=True)
class MailMessage:
    """一封纯文本邮件；只驻留内存，不外发。"""

    to: str
    subject: str
    body: str


class InMemoryMailSender:
    """`MailSender` 端口的内存实现；`messages` 供断言。"""

    def __init__(self) -> None:
        self.messages: list[MailMessage] = []

    async def send(self, *, to: str, subject: str, body: str) -> None:
        self.messages.append(MailMessage(to=to, subject=subject, body=body))


class LoggingMailSender:
    """`MailSender` 端口的本地日志实现；不发起任何网络调用。"""

    def __init__(self, logger: Any | None = None) -> None:
        self._logger = logger if logger is not None else get_logger(__name__)

    async def send(self, *, to: str, subject: str, body: str) -> None:
        self._logger.info("mail.send", to=to, subject=subject, body=body, network_calls=0)
