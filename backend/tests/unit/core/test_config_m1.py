"""M1-T01：新增配置字段的默认值、正整数校验与 M0 三必填变量回归。"""

from __future__ import annotations

import pytest

from app.core.config import Settings, SettingsError, get_settings

_DEFAULTS: dict[str, object] = {
    "jwt_algorithm": "HS256",
    "access_token_ttl_seconds": 900,
    "refresh_token_ttl_seconds": 2592000,
    "password_reset_ttl_seconds": 3600,
    "login_rate_limit_max": 5,
    "login_rate_limit_window_seconds": 60,
    "ai_daily_quota": 20,
}


def test_m1_settings_have_documented_defaults(settings: Settings) -> None:
    """`CONTRACTS §2` 的 7 个字段全部可选且默认值一致。"""
    for name, expected in _DEFAULTS.items():
        assert getattr(settings, name) == expected


@pytest.mark.parametrize(
    ("env_name", "field"),
    [
        ("ACCESS_TOKEN_TTL_SECONDS", "access_token_ttl_seconds"),
        ("REFRESH_TOKEN_TTL_SECONDS", "refresh_token_ttl_seconds"),
        ("PASSWORD_RESET_TTL_SECONDS", "password_reset_ttl_seconds"),
        ("LOGIN_RATE_LIMIT_MAX", "login_rate_limit_max"),
        ("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "login_rate_limit_window_seconds"),
    ],
)
@pytest.mark.parametrize("raw", ["0", "-1", "not-an-int"])
def test_non_positive_or_invalid_values_are_rejected(
    monkeypatch: pytest.MonkeyPatch, env_name: str, field: str, raw: str
) -> None:
    """0 / 负数 / 非整数都给出「变量名 + 原因」，且不含输入值。"""
    monkeypatch.setenv(env_name, raw)
    get_settings.cache_clear()
    try:
        with pytest.raises(SettingsError) as exc_info:
            get_settings()
        problems = exc_info.value.problems
        assert len(problems) == 1
        assert env_name in problems[0]
        assert raw not in problems[0]
        assert "正整数" in problems[0] or "不合法" in problems[0]
        assert field not in problems[0]
    finally:
        get_settings.cache_clear()


def test_ai_daily_quota_allows_zero_but_not_negative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """配额 0 表示禁用 AI（合法），负数拒绝。"""
    monkeypatch.setenv("AI_DAILY_QUOTA", "0")
    get_settings.cache_clear()
    try:
        assert get_settings().ai_daily_quota == 0
    finally:
        get_settings.cache_clear()

    monkeypatch.setenv("AI_DAILY_QUOTA", "-1")
    get_settings.cache_clear()
    try:
        with pytest.raises(SettingsError) as exc_info:
            get_settings()
        assert "AI_DAILY_QUOTA" in exc_info.value.problems[0]
    finally:
        get_settings.cache_clear()


def test_m0_required_variables_still_aggregate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """新增可选字段不得破坏 M0 验收项 3：一次列出三个必填变量。"""
    for name in ("DATABASE_URL", "REDIS_URL", "SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(SettingsError) as exc_info:
            get_settings()
        problems = exc_info.value.problems
        assert len(problems) == 3
        assert all("缺失必填项" in problem for problem in problems)
        assert {problem.split(":")[0] for problem in problems} == {
            "DATABASE_URL",
            "REDIS_URL",
            "SECRET_KEY",
        }
    finally:
        get_settings.cache_clear()
