"""Q3 裁决：Gmail / Outlook SMTP 适配器（假会话，零网络调用）。"""

# ruff: noqa: S105, S106, S107

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr

from app.modules.identity.adapters.smtp_mail import SmtpMailSender

_PLAINTEXT = "R" * 43  # 模拟一次性重置令牌，绝不出现在日志里
_RECIPIENT = "neo@example.com"


class _FakeSmtp:
    """记录调用顺序的假 SMTP 会话；`fail_at_send` 用于验证故障收敛。"""

    def __init__(self, fail_at_send: Exception | None = None) -> None:
        self.calls: list[str] = []
        self.message: EmailMessage | None = None
        self.tls_contexts: list[Any] = []
        self.logins: list[tuple[str, str]] = []
        self._fail_at_send = fail_at_send

    def __enter__(self) -> _FakeSmtp:
        self.calls.append("enter")
        return self

    def __exit__(self, *args: object) -> None:
        self.calls.append("exit")

    def ehlo(self) -> None:
        self.calls.append("ehlo")

    def starttls(self, *, context: Any) -> None:
        self.calls.append("starttls")
        self.tls_contexts.append(context)

    def login(self, user: str, password: str) -> None:
        self.calls.append("login")
        self.logins.append((user, password))

    def send_message(self, message: EmailMessage) -> None:
        if self._fail_at_send is not None:
            raise self._fail_at_send
        self.calls.append("send_message")
        self.message = message


def _build(
    fake: _FakeSmtp,
    *,
    use_starttls: bool = True,
    password: str = "gmail-app-password",
) -> tuple[SmtpMailSender, MagicMock]:
    logger = MagicMock()
    sender = SmtpMailSender(
        host="smtp.gmail.com",
        port=587,
        user="bot@gmail.com",
        password=SecretStr(password),
        sender="bot@gmail.com",
        use_starttls=use_starttls,
        timeout=7.5,
        transport_factory=lambda: fake,
        logger=logger,
    )
    return sender, logger


async def test_delivers_message_over_starttls_with_expected_headers() -> None:
    fake = _FakeSmtp()
    sender, logger = _build(fake)

    await sender.send(to=_RECIPIENT, subject="密码重置令牌", body=f"令牌：\n\n{_PLAINTEXT}\n")

    assert fake.calls == [
        "enter",
        "ehlo",
        "starttls",
        "ehlo",
        "login",
        "send_message",
        "exit",
    ]
    assert fake.logins == [("bot@gmail.com", "gmail-app-password")]
    assert len(fake.tls_contexts) == 1
    assert isinstance(fake.tls_contexts[0], ssl.SSLContext)
    assert fake.message is not None
    assert fake.message["From"] == "bot@gmail.com"
    assert fake.message["To"] == _RECIPIENT
    assert fake.message["Subject"] == "密码重置令牌"
    assert _PLAINTEXT in str(fake.message.get_content())
    logger.info.assert_called_once()
    assert logger.error.call_count == 0


async def test_logs_never_contain_token_recipient_or_password() -> None:
    fake = _FakeSmtp()
    sender, logger = _build(fake)
    await sender.send(to=_RECIPIENT, subject="密码重置令牌", body=_PLAINTEXT)

    logged = repr(logger.method_calls)
    assert "mail.smtp.sent" in logged
    assert "network_calls=1" in logged
    assert "recipient_digest=" in logged
    for secret in (_PLAINTEXT, _RECIPIENT, "gmail-app-password", "密码重置令牌"):
        assert secret not in logged


@pytest.mark.parametrize(
    "failure",
    [
        smtplib.SMTPException("smtp down"),
        OSError("network unreachable"),
        TimeoutError("smtp timeout"),
    ],
)
async def test_delivery_failure_is_swallowed_to_keep_response_uniform(
    failure: Exception,
) -> None:
    """投递失败不得冒泡成 500，否则「账号存在」会与「账号不存在」响应不同。"""
    fake = _FakeSmtp(fail_at_send=failure)
    sender, logger = _build(fake)

    await sender.send(to=_RECIPIENT, subject="s", body=_PLAINTEXT)  # 不抛

    logger.info.assert_not_called()
    logger.error.assert_called_once()
    assert logger.error.call_args.args == ("mail.smtp.failed",)
    kwargs = logger.error.call_args.kwargs
    assert kwargs["incident"] == "mail_delivery_failed"
    assert kwargs["error_type"] == type(failure).__name__
    assert _PLAINTEXT not in repr(logger.method_calls)
    assert _RECIPIENT not in repr(logger.method_calls)


async def test_starttls_can_be_disabled_for_internal_relay() -> None:
    fake = _FakeSmtp()
    sender, _ = _build(fake, use_starttls=False)
    await sender.send(to=_RECIPIENT, subject="s", body=_PLAINTEXT)
    assert "starttls" not in fake.calls
    assert fake.calls.count("ehlo") == 1
    assert fake.tls_contexts == []


async def test_empty_password_skips_login() -> None:
    fake = _FakeSmtp()
    sender, _ = _build(fake, password="")
    await sender.send(to=_RECIPIENT, subject="s", body=_PLAINTEXT)
    assert "login" not in fake.calls
    assert fake.logins == []
    assert "send_message" in fake.calls


async def test_default_transport_builds_smtplib_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未注入 factory 时走默认构造：仍不发起真实网络，但覆盖真实调用链。

    `smtp_mail.py` 里 `import smtplib` 引用的是同一个模块对象，替换其 `SMTP`
    名字即可拦截构造；monkeypatch 在用例结束后自动还原。
    """
    fake = _FakeSmtp()
    captured: dict[str, Any] = {}

    def fake_smtp(host: str, port: int, timeout: float) -> _FakeSmtp:
        captured.update(host=host, port=port, timeout=timeout)
        return fake

    monkeypatch.setattr(smtplib, "SMTP", fake_smtp)
    sender = SmtpMailSender(
        host="smtp.office365.com",
        port=587,
        user="bot@outlook.com",
        password=SecretStr("pw"),
        sender="bot@outlook.com",
    )
    await sender.send(to=_RECIPIENT, subject="s", body=_PLAINTEXT)

    assert captured == {"host": "smtp.office365.com", "port": 587, "timeout": 10.0}
    assert "send_message" in fake.calls


def test_adapters_package_exports_smtp_sender() -> None:
    from app.modules.identity import adapters

    assert adapters.SmtpMailSender is SmtpMailSender
    assert "SmtpMailSender" in adapters.__all__
