"""M1-T03：邮件端口的内存/日志适配器（裁定 C1，不接外部服务商）。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.modules.identity.adapters.mail import (
    InMemoryMailSender,
    LoggingMailSender,
    MailMessage,
)


async def test_in_memory_sender_records_messages() -> None:
    sender = InMemoryMailSender()
    assert sender.messages == []
    await sender.send(to="neo@example.com", subject="重置密码", body="link-1")
    await sender.send(to="neo@example.com", subject="重置密码", body="link-2")
    assert sender.messages == [
        MailMessage(to="neo@example.com", subject="重置密码", body="link-1"),
        MailMessage(to="neo@example.com", subject="重置密码", body="link-2"),
    ]


async def test_mail_message_is_frozen() -> None:
    message = MailMessage(to="a@example.com", subject="s", body="b")
    with pytest.raises((AttributeError, TypeError)):
        message.body = "changed"  # type: ignore[misc]


async def test_logging_sender_uses_injected_logger_and_no_network() -> None:
    logger = MagicMock()
    sender = LoggingMailSender(logger=logger)
    await sender.send(to="a@example.com", subject="s", body="b")
    logger.info.assert_called_once_with(
        "mail.send", to="a@example.com", subject="s", body="b", network_calls=0
    )


async def test_logging_sender_default_logger_path() -> None:
    """未注入 logger 时也能工作（走 M0 structlog），覆盖默认分支。"""
    sender = LoggingMailSender()
    await sender.send(to="a@example.com", subject="s", body="b")


async def test_adapters_package_exports_all_implementations() -> None:
    from app.modules.identity import adapters

    assert adapters.Argon2PasswordHasher.__name__ == "Argon2PasswordHasher"
    assert adapters.JWTTokenCodec.__name__ == "JWTTokenCodec"
    assert adapters.InMemoryMailSender is InMemoryMailSender
    assert "LoggingMailSender" in adapters.__all__
