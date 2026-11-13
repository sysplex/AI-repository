"""Q3 裁决：`make_mail_sender` 的四条选择分支与「CI 绝不外发」约束。"""

# ruff: noqa: S105, S106

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.modules.identity import service as service_module
from app.modules.identity.adapters.mail import InMemoryMailSender, LoggingMailSender
from app.modules.identity.adapters.smtp_mail import SmtpMailSender
from app.modules.identity.service import make_mail_sender


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": "postgresql+asyncpg://svc@db.internal:5432/app",
        "redis_url": "redis://localhost:6379/0",
        "secret_key": SecretStr("s" * 40),
    }
    values.update(overrides)
    return Settings(**values)


def _configured(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "app_env": "production",
        "smtp_user": "bot@gmail.com",
        "smtp_password": SecretStr("app-password"),
    }
    values.update(overrides)
    return _settings(**values)


@pytest.fixture(autouse=True)
def service_logger(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """替换模块级 logger，便于断言占位告警且不污染真实日志。"""
    logger = MagicMock()
    monkeypatch.setattr(service_module, "_LOGGER", logger)
    return logger


def test_ci_always_uses_memory_even_when_smtp_is_configured() -> None:
    """CI 优先级最高：配了凭据也不许向 Gmail/Outlook 发信。"""
    settings = _configured(app_env="ci")
    assert settings.smtp_configured is True
    assert isinstance(make_mail_sender(settings), InMemoryMailSender)


@pytest.mark.parametrize("env", ["local", "staging", "production"])
def test_configured_smtp_is_selected_outside_ci(env: str) -> None:
    sender = make_mail_sender(_configured(app_env=env))
    assert isinstance(sender, SmtpMailSender)
    assert sender._host == "smtp.gmail.com"
    assert sender._port == 587
    assert sender._sender == "bot@gmail.com"


def test_outlook_provider_resolves_office365_host() -> None:
    sender = make_mail_sender(_configured(smtp_provider="outlook"))
    assert isinstance(sender, SmtpMailSender)
    assert sender._host == "smtp.office365.com"


def test_explicit_host_and_from_override_provider_defaults() -> None:
    sender = make_mail_sender(
        _configured(smtp_host="mail.internal:2525", smtp_from="no-reply@internal.test")
    )
    assert isinstance(sender, SmtpMailSender)
    assert sender._host == "mail.internal:2525"
    assert sender._sender == "no-reply@internal.test"


def test_local_without_smtp_uses_logging_without_warning(service_logger: MagicMock) -> None:
    settings = _settings(app_env="local")
    assert settings.smtp_configured is False
    assert isinstance(make_mail_sender(settings), LoggingMailSender)
    service_logger.error.assert_not_called()


@pytest.mark.parametrize("env", ["staging", "production"])
def test_non_local_without_smtp_keeps_placeholder_warning(
    env: str, service_logger: MagicMock
) -> None:
    settings = _settings(app_env=env)
    assert isinstance(make_mail_sender(settings), LoggingMailSender)
    service_logger.error.assert_called_once()
    assert service_logger.error.call_args.args == ("mail.adapter.placeholder",)
    assert service_logger.error.call_args.kwargs["incident"] == "mail_adapter_missing"
