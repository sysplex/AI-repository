# ruff: noqa: S105, S106
# 本文件刻意使用伪造的密码/令牌字面量来验证 SecretStr 脱敏与校验边界，均非真实凭据。
"""M1-T02：`CONTRACTS §4` 领域 schema 的校验边界与脱敏行为。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest
from pydantic import ValidationError

from app.modules.identity import enums, schemas
from app.modules.identity.schemas import (
    AuthenticatedUser,
    LoginRequest,
    LogoutRequest,
    PaginatedUsers,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
    SettingsUpdate,
    TokenPair,
    UsageResponse,
    UserPublic,
    UserSettings,
)

_STRONG = "Str0ngPassw0rd!"
_WEAK = [
    "Sh0rt!",  # < 12
    "alllowercase123",  # 缺大写
    "ALLUPPERCASE123",  # 缺小写
    "NoDigitsHere!!!!",  # 缺数字
]


def test_enums_are_reexported_from_schemas() -> None:
    """T01 前移枚举定义后，`schemas.UserRole` 仍是同一对象。"""
    assert schemas.UserRole is enums.UserRole
    assert schemas.UserStatus is enums.UserStatus
    assert schemas.UserRole.ADMIN.value == "admin"
    assert schemas.UserStatus.ACTIVE.value == "active"


def test_register_request_defaults_and_secret_str() -> None:
    req = RegisterRequest(email="neo@example.com", password=_STRONG)
    assert req.password.get_secret_value() == _STRONG
    assert isinstance(req.settings, UserSettings)
    assert req.settings.risk_profile == "balanced"
    assert req.settings.language == "zh-CN"
    assert req.settings.default_account_id is None


@pytest.mark.parametrize("weak", _WEAK)
def test_register_request_rejects_weak_passwords(weak: str) -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(email="neo@example.com", password=weak)


def test_password_error_never_echoes_input() -> None:
    """Pydantic 原始异常会带 input_value，但对外只用 `msg`（M0 handler 的行为）。"""
    raw = "nouppercase123456"
    with pytest.raises(ValidationError) as exc:
        RegisterRequest(email="neo@example.com", password=raw)
    messages = " ".join(str(item.get("msg", "")) for item in exc.value.errors())
    assert raw not in messages
    assert "密码需至少 12 位" in messages


async def test_m0_validation_handler_does_not_echo_password() -> None:
    """端到端验证：M0 的 400 统一错误响应里不含密码明文。"""
    from fastapi.exceptions import RequestValidationError

    from app.core.errors import _validation_error_handler

    raw = "nouppercase123456"
    with pytest.raises(ValidationError) as exc:
        RegisterRequest(email="neo@example.com", password=raw)
    response = await _validation_error_handler(
        cast(Any, None), RequestValidationError(exc.value.errors())
    )
    body = bytes(response.body).decode("utf-8")
    assert raw not in body
    assert "密码需至少 12 位" in body
    assert "VALIDATION_ERROR" in body


def test_register_request_rejects_invalid_email() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(email="not-an-email", password=_STRONG)


def test_secret_str_does_not_leak_in_repr_or_json() -> None:
    req = RegisterRequest(email="neo@example.com", password=_STRONG)
    assert _STRONG not in repr(req)
    assert _STRONG not in req.model_dump_json()
    dumped: dict[str, Any] = req.model_dump()
    assert not isinstance(dumped["password"], str)
    assert dumped["password"].get_secret_value() == _STRONG


def test_password_reset_confirm_enforces_complexity() -> None:
    good = PasswordResetConfirm(token="tok", new_password=_STRONG)
    assert good.new_password.get_secret_value() == _STRONG
    for weak in _WEAK:
        with pytest.raises(ValidationError):
            PasswordResetConfirm(token="tok", new_password=weak)


def test_user_settings_validation() -> None:
    settings = UserSettings(
        risk_profile="aggressive", language="en-US", default_account_id=str(uuid.uuid4())
    )
    assert settings.risk_profile == "aggressive"
    assert isinstance(settings.default_account_id, uuid.UUID)
    with pytest.raises(ValidationError):
        UserSettings(risk_profile="yolo")
    with pytest.raises(ValidationError):
        UserSettings.model_validate({"unknown": 1})


def test_all_simple_request_schemas_keep_secrets() -> None:
    assert LoginRequest(email="a@example.com", password="pw").password.get_secret_value() == "pw"
    assert RefreshRequest(refresh_token="r").refresh_token.get_secret_value() == "r"
    assert LogoutRequest(refresh_token="l").refresh_token.get_secret_value() == "l"
    assert PasswordResetRequest(email="a@example.com").email == "a@example.com"
    update = SettingsUpdate(settings=UserSettings(language="fr-FR"))
    assert update.settings.language == "fr-FR"


def _orm_user() -> Any:
    return SimpleNamespace(
        id=uuid.uuid4(),
        email="neo@example.com",
        role="admin",
        status="active",
        settings={"risk_profile": "conservative", "language": "en-US"},
        created_at=datetime(2026, 11, 12, tzinfo=UTC),
    )


def test_user_public_validates_from_orm_attributes() -> None:
    public = UserPublic.model_validate(_orm_user())
    assert public.role is enums.UserRole.ADMIN
    assert public.status is enums.UserStatus.ACTIVE
    assert public.settings.risk_profile == "conservative"
    assert public.created_at.tzinfo is UTC
    assert "password" not in public.model_fields


def test_authenticated_user_validates_from_orm_attributes() -> None:
    user = AuthenticatedUser.model_validate(_orm_user())
    assert user.email == "neo@example.com"
    assert user.role is enums.UserRole.ADMIN
    assert not hasattr(user, "created_at")


def test_token_pair_defaults() -> None:
    pair = TokenPair(access_token="a", refresh_token="r", expires_in=900)
    assert pair.token_type == "bearer"
    assert pair.model_dump()["expires_in"] == 900


def test_usage_response_and_paginated_users() -> None:
    usage = UsageResponse(
        usage_date="2026-11-12",
        calls=3,
        tokens_in=100,
        tokens_out=50,
        cost_usd=Decimal("0.125000"),
        quota=20,
        quota_used=3,
    )
    assert usage.cost_usd == Decimal("0.125000")
    page = PaginatedUsers(
        items=[UserPublic.model_validate(_orm_user())], total=1, page=1, page_size=20
    )
    assert page.items[0].email == "neo@example.com"
    assert page.total == 1
