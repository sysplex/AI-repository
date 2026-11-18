"""M1 identity 领域 schema（T02），`CONTRACTS.md §4`。

所有请求/响应类型集中在这里；`UserRole` / `UserStatus` 由 `enums.py` 重新导出，
保持 `CONTRACTS §4` 的公开签名不变（T01 已把枚举定义前移）。
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator

from app.modules.identity.enums import UserRole, UserStatus

__all__ = [
    "AuthenticatedUser",
    "LoginRequest",
    "LogoutRequest",
    "PaginatedUsers",
    "PasswordResetConfirm",
    "PasswordResetRequest",
    "RefreshRequest",
    "RegisterRequest",
    "SettingsUpdate",
    "TokenPair",
    "UsageResponse",
    "UserPublic",
    "UserRole",
    "UserSettings",
    "UserStatus",
]

_MIN_PASSWORD_LENGTH: Final[int] = 12
_PASSWORD_ERROR: Final[str] = "密码需至少 12 位，且同时包含大写字母、小写字母与数字"  # noqa: S105 - 校验提示文案，非凭据


def _validate_password(value: SecretStr) -> SecretStr:
    """密码复杂度校验；错误文本固定，绝不回显输入值。"""
    secret = value.get_secret_value()
    if (
        len(secret) < _MIN_PASSWORD_LENGTH
        or not any(char.isupper() for char in secret)
        or not any(char.islower() for char in secret)
        or not any(char.isdigit() for char in secret)
    ):
        raise ValueError(_PASSWORD_ERROR)
    return value


class UserSettings(BaseModel):
    """用户可改的偏好；`users.settings` 为 JSONB，缺字段时由本模型补默认值。"""

    model_config = ConfigDict(extra="forbid")

    risk_profile: Literal["conservative", "balanced", "aggressive"] = "balanced"
    language: str = "zh-CN"
    default_account_id: uuid.UUID | None = None
    ai_provider: Literal["mock", "google", "openai", "deepseek", "anthropic"] = "mock"
    google_api_key: str | None = None
    google_model: str = "gemini-3.5-flash-lite"


class RegisterRequest(BaseModel):
    """注册请求；`settings` 缺省为默认偏好。"""

    email: EmailStr
    password: SecretStr
    settings: UserSettings = Field(default_factory=UserSettings)

    @field_validator("password")
    @classmethod
    def _check_password(cls, value: SecretStr) -> SecretStr:
        return _validate_password(value)


class LoginRequest(BaseModel):
    email: EmailStr
    password: SecretStr


class RefreshRequest(BaseModel):
    refresh_token: SecretStr


class LogoutRequest(BaseModel):
    refresh_token: SecretStr


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: SecretStr
    new_password: SecretStr

    @field_validator("new_password")
    @classmethod
    def _check_password(cls, value: SecretStr) -> SecretStr:
        return _validate_password(value)


class SettingsUpdate(BaseModel):
    settings: UserSettings


class UserPublic(BaseModel):
    """对外用户视图；不含任何凭据字段。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    role: UserRole
    status: UserStatus
    settings: UserSettings
    created_at: datetime


class AuthenticatedUser(BaseModel):
    """access 令牌校验后注入依赖的对象。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    role: UserRole
    status: UserStatus
    settings: UserSettings


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - OAuth2 固定类型标识，非凭据
    expires_in: int


class UsageResponse(BaseModel):
    usage_date: date
    calls: int
    tokens_in: int
    tokens_out: int
    cost_usd: Decimal
    quota: int
    quota_used: int


class PaginatedUsers(BaseModel):
    items: list[UserPublic]
    total: int
    page: int
    page_size: int
