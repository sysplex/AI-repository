"""应用配置（M0 / T02）。严格实现 `CONTRACTS.md §2`。

阶段切换点：T01 空壳不校验三必填变量；本任务合并后启用
「缺失/非法即启动失败并一次性列出」，见 CONTRACTS §2。
"""

from __future__ import annotations

import json
import os
import sys
from functools import lru_cache
from typing import Annotated, Any, Literal

from pydantic import (
    SecretStr,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_REASONS: dict[str, str] = {
    "DATABASE_URL": "必须以 postgresql+asyncpg:// 开头",
    "REDIS_URL": "必须以 redis:// 或 rediss:// 开头",
    "SECRET_KEY": "长度必须 ≥ 32 字符",
    # M1-T01：所有时限/阈值必须为正整数，失败提示沿用「变量名 + 原因」格式。
    "ACCESS_TOKEN_TTL_SECONDS": "必须为正整数",
    "REFRESH_TOKEN_TTL_SECONDS": "必须为正整数",
    "PASSWORD_RESET_TTL_SECONDS": "必须为正整数",
    "LOGIN_RATE_LIMIT_MAX": "必须为正整数",
    "LOGIN_RATE_LIMIT_WINDOW_SECONDS": "必须为正整数",
    "AI_DAILY_QUOTA": "必须为非负整数",
    # Q3（2026-11-13 裁决）：Gmail / Outlook SMTP 投递配置。
    "SMTP_PORT": "必须为 1–65535 的整数",
    "SMTP_TIMEOUT_SECONDS": "必须为正数",
}

_CORS_WILDCARD_REASON = "CORS_ORIGINS: 启用凭据时不允许通配符 *，请列出明确来源"


class _CorsWildcardError(ValueError):
    """内部标记：cors_origins 含 `*`，供 `_problems_from` 生成专用提示。"""


class SettingsError(Exception):
    """配置校验失败：消息含全部问题变量名与原因，不含任何输入值。"""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("配置校验失败：\n" + "\n".join(f"  - {p}" for p in problems))


def mask_database_url(url: str) -> str:
    """把连接串 userinfo 中的密码替换为 `***`，供 repr / 日志使用。"""
    scheme, separator, rest = url.partition("://")
    if not separator or "@" not in rest:
        return url
    userinfo, _, host = rest.rpartition("@")
    if ":" not in userinfo:
        return url
    user = userinfo.split(":", 1)[0]
    return f"{scheme}://{user}:***@{host}"


def mask_redis_url(url: str) -> str:
    """Redis 连接串也可能带密码（`redis://:pass@host`），同样遮蔽。"""
    return mask_database_url(url)


def _problems_from(exc: ValidationError) -> list[str]:
    """把 pydantic 的聚合错误转成「变量名 + 原因」列表，绝不携带原始值。"""
    problems: list[str] = []
    for error in exc.errors():
        location = error.get("loc", ())
        if not location:
            # model_validator(mode="after") 抛出的根级错误：消息本身已是完整可读文案，
            # 不能套「变量名 + 原因」模板，否则会退化成 `(UNKNOWN): 取值不合法`。
            message = str(error.get("msg", "")).removeprefix("Value error, ")
            problems.append(message or "配置取值不合法")
            continue
        field = str(location[0])
        env_name = field.upper()
        if error.get("type") == "missing":
            problems.append(f"{env_name}: 缺失必填项")
        elif field == "cors_origins":
            inner = error.get("ctx", {}).get("error")
            if isinstance(inner, _CorsWildcardError):
                problems.append(_CORS_WILDCARD_REASON)
            else:
                problems.append("CORS_ORIGINS: 需为 JSON 数组或逗号分隔字符串")
        elif field == "app_env":
            problems.append("APP_ENV: 必须是 local / ci / staging / production 之一")
        else:
            problems.append(f"{env_name}: {_REASONS.get(env_name, '取值不合法')}")
    return problems


class Settings(BaseSettings):
    """全应用配置；环境变量名为字段名大写。"""

    model_config = SettingsConfigDict(
        env_file=None,  # 仅 app_env=local 时由 get_settings() 传入 _env_file
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        # cors_origins 需同时支持 JSON 数组与逗号分隔字符串，由下面的
        # before-validator 自己解析；禁用 pydantic-settings 的默认 JSON 解码。
        enable_decoding=False,
    )

    app_env: Literal["local", "ci", "staging", "production"] = "local"
    app_name: str = "stockpilot"
    app_version: str = "0.0.0"
    log_level: str = "INFO"
    log_json: bool = True
    database_url: str
    redis_url: str
    secret_key: SecretStr
    cors_origins: Annotated[list[str], NoDecode()] = []
    metrics_enabled: bool = True
    docs_enabled: bool = True  # production 下默认关闭，由部署环境变量覆盖

    # M1-T01（CONTRACTS §2）：全部可选，不破坏 M0 的三必填变量语义。
    jwt_algorithm: Literal["HS256"] = "HS256"
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_seconds: int = 2592000
    password_reset_ttl_seconds: int = 3600
    login_rate_limit_max: int = 5
    login_rate_limit_window_seconds: int = 60
    ai_daily_quota: int = 20  # Q4（2026-11-13 裁决）：每用户每日默认 20 次

    # Q3（2026-11-13 裁决）：真实邮件走 Gmail / Outlook 的 SMTP + STARTTLS。
    # 全部可选：只有显式提供 SMTP_USER + SMTP_PASSWORD 才启用真实投递，
    # 未配置时保持 M1 结项时的内存 / 日志行为，CI 与本地演示零影响。
    smtp_provider: Literal["gmail", "outlook", "custom"] = "gmail"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str | None = None
    smtp_starttls: bool = True
    smtp_timeout_seconds: float = 10.0

    @field_validator(
        "access_token_ttl_seconds",
        "refresh_token_ttl_seconds",
        "password_reset_ttl_seconds",
        "login_rate_limit_max",
        "login_rate_limit_window_seconds",
    )
    @classmethod
    def _check_positive_int(cls, value: int, info: ValidationInfo) -> int:
        """令牌时限与限流阈值必须 > 0；字段名由 _problems_from 转成环境变量名。"""
        if value <= 0:
            raise ValueError(f"{info.field_name} 必须为正整数")
        return value

    @field_validator("ai_daily_quota")
    @classmethod
    def _check_non_negative_int(cls, value: int) -> int:
        """配额允许 0（禁用 AI），但不得为负。"""
        if value < 0:
            raise ValueError("ai_daily_quota 必须为非负整数")
        return value

    @field_validator("smtp_port")
    @classmethod
    def _check_smtp_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("smtp_port 必须在 1–65535 之间")
        return value

    @field_validator("smtp_timeout_seconds")
    @classmethod
    def _check_smtp_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("smtp_timeout_seconds 必须为正数")
        return value

    @field_validator("database_url")
    @classmethod
    def _check_database_url(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("database_url 前缀不合法")
        return value

    @field_validator("redis_url")
    @classmethod
    def _check_redis_url(cls, value: str) -> str:
        if not (value.startswith("redis://") or value.startswith("rediss://")):
            raise ValueError("redis_url 前缀不合法")
        return value

    @field_validator("secret_key")
    @classmethod
    def _check_secret_key(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("secret_key 过短")
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: Any) -> Any:
        """同时支持 JSON 数组与逗号分隔字符串（CONTRACTS §2 / T02 验收项）。"""
        if not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            return []
        if text.startswith(("[", "{")):
            parsed = json.loads(text)
            if not isinstance(parsed, list):
                raise ValueError("cors_origins 必须是数组")
            return parsed
        return [item.strip() for item in text.split(",") if item.strip()]

    @field_validator("cors_origins")
    @classmethod
    def _reject_cors_wildcard(cls, value: list[str]) -> list[str]:
        """`install_middlewares` 固定 `allow_credentials=True`；`*` 会反射任意来源。

        CORSMiddleware 在 allow_credentials=True 下遇到 `*` 会把请求 Origin 原样
        回显，等同于允许任意站点携带凭据读取响应，故在配置层直接拒绝。
        """
        if any(origin.strip() == "*" for origin in value):
            raise _CorsWildcardError("wildcard origin is unsafe with credentials")
        return value

    @model_validator(mode="after")
    def _check_smtp_is_complete(self) -> Settings:
        """半配置的 SMTP 一律启动失败：避免「以为在发信、其实在写日志」。

        只要显式设置了任一认证项（`SMTP_USER` / `SMTP_PASSWORD` / `SMTP_FROM`），
        就视为意图启用真实投递，此时 `SMTP_USER` / `SMTP_PASSWORD` 必须同时存在；
        `custom` 且已启用投递时还要求 `SMTP_HOST`。仅填连接参数（如 `SMTP_HOST`）
        不视为启用，允许先写模板、后补凭据。
        """
        intended = {"smtp_user", "smtp_password", "smtp_from"} & self.model_fields_set
        if not intended:
            return self
        missing = [
            name.upper() for name in ("smtp_user", "smtp_password") if getattr(self, name) is None
        ]
        if (
            self.smtp_provider == "custom"
            and self.smtp_host is None
            and self.smtp_user is not None
            and self.smtp_password is not None
        ):
            missing.append("SMTP_HOST")
        if missing:
            raise ValueError(
                "SMTP 配置不完整：启用真实投递需同时设置 "
                + ", ".join(sorted(missing))
                + "（或全部留空以使用本地适配器）"
            )
        return self

    @model_validator(mode="after")
    def _disable_docs_in_production(self) -> Settings:
        if self.app_env == "production" and "docs_enabled" not in self.model_fields_set:
            self.docs_enabled = False
        return self

    @property
    def smtp_configured(self) -> bool:
        """是否启用真实 SMTP 投递（凭据齐全且通过完整性校验）。"""
        return self.smtp_user is not None and self.smtp_password is not None

    @property
    def smtp_resolved_host(self) -> str:
        """`SMTP_PROVIDER` 解析为厂商默认主机；显式 `SMTP_HOST` 优先。"""
        if self.smtp_host:
            return self.smtp_host
        if self.smtp_provider == "outlook":
            return "smtp.office365.com"
        if self.smtp_provider == "custom":
            return ""
        return "smtp.gmail.com"

    @property
    def smtp_resolved_from(self) -> str:
        """未设置 `SMTP_FROM` 时直接用登录账号作为发件人。"""
        return self.smtp_from or self.smtp_user or ""

    def __repr__(self) -> str:
        """显式遮蔽 secret_key 与连接串密码，避免 repr 泄露。"""
        data = self.model_dump()
        data["secret_key"] = "***"  # noqa: S105 - 这是遮蔽后的占位符，不是真实口令
        data["smtp_password"] = "***"  # noqa: S105 - 同上，SMTP 应用专用密码
        data["database_url"] = mask_database_url(self.database_url)
        data["redis_url"] = mask_redis_url(self.redis_url)
        body = ", ".join(f"{key}={value!r}" for key, value in data.items())
        return f"Settings({body})"

    def __str__(self) -> str:
        return self.__repr__()


def _build_settings() -> Settings:
    app_env = os.getenv("APP_ENV", "local").lower()
    env_file: str | None = ".env" if app_env == "local" else None
    try:
        return Settings(_env_file=env_file)
    except ValidationError as exc:
        raise SettingsError(_problems_from(exc)) from None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """lru_cache 单例；测试可 `get_settings.cache_clear()`。异常可读且不含值。"""
    return _build_settings()


def load_settings_or_exit() -> Settings:
    """供 `main` / `worker` 使用：失败时一次性列出问题并以非 0 退出码终止。

    T02 不得修改 `main.py`（仅 T01/T11 可改），故本函数只提供、不接线；
    当前 `create_app()` 已通过 `get_settings()` 触发同样的可读异常。
    """
    try:
        return get_settings()
    except SettingsError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
