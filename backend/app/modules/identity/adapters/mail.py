"""邮件投递适配器（T03），裁定 C1：Q3 未拍板，不绑定任何外部服务商。

`InMemoryMailSender` 供测试断言；`LoggingMailSender` 供本地开发查看重置链接。
**生产禁用 `LoggingMailSender`**：邮件正文含一次性重置令牌，只应在本地/测试环境
出现；上线前必须换成真实 adapter 并关闭日志输出。
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
