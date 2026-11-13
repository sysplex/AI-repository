"""T02 验收：配置校验、一次性错误汇总与敏感信息保护。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import (
    Settings,
    SettingsError,
    get_settings,
    load_settings_or_exit,
    mask_database_url,
    mask_redis_url,
)

# 收集期导入 `app.main`（模块级 `app = create_app()`）所需的三个必填变量，
# 已由 T10 的 `tests/conftest.py` 在收集前统一提供；T02 阶段为本模块写的
# `os.environ.setdefault` 兼容兜底由此成为无副作用冗余，按 M0-F3（Issue #26）移除。
# 各测试仍由 `_isolated` fixture 显式清理环境变量并验证缺失场景。

_PWD = "h" * 12
_SECRET = "s" * 40
_DB = f"postgresql+asyncpg://svc:{_PWD}@db.internal:5432/app"
_REDIS = "redis://localhost:6379/0"
_REQUIRED = ("DATABASE_URL", "REDIS_URL", "SECRET_KEY")
_ENV_KEYS = (
    *_REQUIRED,
    "APP_ENV",
    "CORS_ORIGINS",
    "DOCS_ENABLED",
    "LOG_JSON",
    "LOG_LEVEL",
    # Q3：避免开发机上的 SMTP_* 环境变量污染本模块的隔离测试
    "SMTP_PROVIDER",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "SMTP_FROM",
    "SMTP_STARTTLS",
    "SMTP_TIMEOUT_SECONDS",
)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """每个测试都在空临时目录运行，杜绝任何 .env 干扰。"""
    monkeypatch.chdir(tmp_path)
    for name in _ENV_KEYS:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": _DB,
        "redis_url": _REDIS,
        "secret_key": SecretStr(_SECRET),
    }
    values.update(overrides)
    return Settings(**values)


def _required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", _DB)
    monkeypatch.setenv("REDIS_URL", _REDIS)
    monkeypatch.setenv("SECRET_KEY", _SECRET)


def test_missing_required_variables_are_all_listed() -> None:
    with pytest.raises(SettingsError) as caught:
        get_settings()
    message = str(caught.value)
    for name in _REQUIRED:
        assert name in message
    assert message.count("缺失必填项") == 3
    assert len(caught.value.problems) == 3
    assert _PWD not in message


def test_secret_key_too_short(monkeypatch: pytest.MonkeyPatch) -> None:
    _required_env(monkeypatch)
    monkeypatch.setenv("SECRET_KEY", "t" * 8)
    with pytest.raises(SettingsError) as caught:
        get_settings()
    message = str(caught.value)
    assert "SECRET_KEY" in message
    assert "32" in message
    assert "t" * 8 not in message


def test_database_url_prefix_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    _required_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "postgresql://svc@db/app")
    with pytest.raises(SettingsError) as caught:
        get_settings()
    message = str(caught.value)
    assert "DATABASE_URL" in message
    assert "postgresql+asyncpg://" in message


def test_redis_url_prefix_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    _required_env(monkeypatch)
    monkeypatch.setenv("REDIS_URL", "http://cache")
    with pytest.raises(SettingsError) as caught:
        get_settings()
    assert "REDIS_URL" in str(caught.value)


def test_multiple_problems_listed_together(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "mysql://db/app")
    monkeypatch.setenv("REDIS_URL", "http://cache")
    with pytest.raises(SettingsError) as caught:
        get_settings()
    message = str(caught.value)
    for name in _REQUIRED:
        assert name in message


def test_invalid_app_env_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    _required_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "weird")
    with pytest.raises(SettingsError) as caught:
        get_settings()
    assert "APP_ENV" in str(caught.value)


def test_invalid_bool_uses_generic_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    _required_env(monkeypatch)
    monkeypatch.setenv("LOG_JSON", "definitely-not-bool")
    with pytest.raises(SettingsError) as caught:
        get_settings()
    assert "LOG_JSON" in str(caught.value)


def test_invalid_cors_origins_reported_by_get_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _required_env(monkeypatch)
    monkeypatch.setenv("CORS_ORIGINS", '{"origin": "https://a.example"}')
    with pytest.raises(SettingsError) as caught:
        get_settings()
    assert "CORS_ORIGINS" in str(caught.value)


def test_repr_and_str_never_leak_secrets() -> None:
    settings = _settings()
    text = repr(settings) + str(settings)
    assert _PWD not in text
    assert _SECRET not in text
    assert "***" in text
    assert "postgresql+asyncpg://" in text
    assert isinstance(settings.secret_key, SecretStr)


def test_mask_helpers() -> None:
    assert mask_database_url(_DB) == "postgresql+asyncpg://svc:***@db.internal:5432/app"
    assert mask_database_url("no-scheme") == "no-scheme"
    assert mask_database_url("redis://localhost:6379/0") == "redis://localhost:6379/0"
    assert mask_database_url("postgresql+asyncpg://user@host/db") == (
        "postgresql+asyncpg://user@host/db"
    )
    assert mask_redis_url("redis://:" + _PWD + "@host:6379/0") == "redis://:***@host:6379/0"


def test_cors_origins_json_array() -> None:
    settings = _settings(cors_origins='["https://a.example", "https://b.example"]')
    assert settings.cors_origins == ["https://a.example", "https://b.example"]


def test_cors_origins_comma_separated() -> None:
    settings = _settings(cors_origins="https://a.example, https://b.example ,")
    assert settings.cors_origins == ["https://a.example", "https://b.example"]


def test_cors_origins_blank_and_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _settings(cors_origins="  ").cors_origins == []
    _required_env(monkeypatch)
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example,https://b.example")
    get_settings.cache_clear()
    assert get_settings().cors_origins == ["https://a.example", "https://b.example"]


def test_cors_origins_non_list_json_rejected() -> None:
    with pytest.raises(ValidationError):
        _settings(cors_origins='{"origin": "https://a.example"}')


def test_env_file_only_read_in_local(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        f"DATABASE_URL={_DB}\nREDIS_URL={_REDIS}\nSECRET_KEY={_SECRET}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("APP_ENV", "local")
    get_settings.cache_clear()
    assert get_settings().database_url == _DB

    monkeypatch.setenv("APP_ENV", "ci")
    get_settings.cache_clear()
    with pytest.raises(SettingsError) as caught:
        get_settings()
    assert "DATABASE_URL" in str(caught.value)


def test_load_settings_or_exit_prints_all_and_exits_nonzero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as caught:
        load_settings_or_exit()
    assert caught.value.code == 1
    err = capsys.readouterr().err
    for name in _REQUIRED:
        assert name in err


def test_valid_settings_and_lru_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    _required_env(monkeypatch)
    get_settings.cache_clear()
    first = get_settings()
    assert first is get_settings()
    assert first.metrics_enabled is True
    assert first.log_json is True
    assert first.app_env == "local"


def test_production_disables_docs_by_default() -> None:
    assert _settings(app_env="production").docs_enabled is False
    assert _settings(app_env="production", docs_enabled=True).docs_enabled is True
    assert _settings(app_env="local").docs_enabled is True


# ---------------------------------------------------------------- Q3 / Q4 裁决


def test_q4_ai_daily_quota_default_is_20() -> None:
    """Q4 已裁决：每用户每日默认 20 次，后续只允许显式覆盖。"""
    assert _settings().ai_daily_quota == 20


def test_env_example_keeps_smtp_opt_in_and_quota_at_20() -> None:
    """模板里的 SMTP_* 必须全部注释，否则默认就会尝试真实外发（含 CI/演示）。"""
    path = Path(__file__).resolve().parents[4] / "deploy" / "env.example"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert [line for line in lines if line.startswith("SMTP_")] == []
    assert "AI_DAILY_QUOTA=20" in lines


def test_smtp_disabled_by_default_keeps_m1_behavior() -> None:
    settings = _settings()
    assert settings.smtp_configured is False
    assert settings.smtp_resolved_host == "smtp.gmail.com"
    assert settings.smtp_resolved_from == ""
    assert settings.smtp_starttls is True
    assert settings.smtp_timeout_seconds == 10.0


def test_smtp_partial_config_is_rejected() -> None:
    """半配置启动即失败，避免「以为在发信、其实在写日志」。"""
    with pytest.raises(ValidationError) as caught:
        _settings(smtp_user="bot@gmail.com")
    assert "SMTP_PASSWORD" in str(caught.value)


def test_smtp_partial_config_problem_is_readable_via_get_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _required_env(monkeypatch)
    monkeypatch.setenv("SMTP_USER", "bot@gmail.com")
    get_settings.cache_clear()
    with pytest.raises(SettingsError) as caught:
        get_settings()
    assert any("SMTP 配置不完整" in problem for problem in caught.value.problems)
    assert all("(UNKNOWN)" not in problem for problem in caught.value.problems)


def test_smtp_full_config_and_repr_masks_app_password() -> None:
    settings = _settings(
        smtp_user="bot@gmail.com",
        smtp_password=SecretStr("gmail-app-password"),
    )
    assert settings.smtp_configured is True
    assert settings.smtp_resolved_from == "bot@gmail.com"
    assert "gmail-app-password" not in repr(settings) + str(settings)


def test_smtp_provider_and_explicit_host_resolution() -> None:
    assert _settings(smtp_provider="outlook").smtp_resolved_host == "smtp.office365.com"
    assert _settings(smtp_provider="custom").smtp_resolved_host == ""
    custom = _settings(smtp_provider="custom", smtp_host="mail.internal:2525")
    assert custom.smtp_resolved_host == "mail.internal:2525"


def test_smtp_custom_provider_without_host_fails_fast() -> None:
    with pytest.raises(ValidationError) as caught:
        _settings(
            smtp_provider="custom",
            smtp_user="bot@internal.test",
            smtp_password=SecretStr("pw"),
        )
    assert "SMTP_HOST" in str(caught.value)


@pytest.mark.parametrize("port", [0, 65536])
def test_smtp_invalid_port_is_reported(monkeypatch: pytest.MonkeyPatch, port: int) -> None:
    _required_env(monkeypatch)
    monkeypatch.setenv("SMTP_PORT", str(port))
    get_settings.cache_clear()
    with pytest.raises(SettingsError) as caught:
        get_settings()
    assert "SMTP_PORT" in str(caught.value)


def test_smtp_non_positive_timeout_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    _required_env(monkeypatch)
    monkeypatch.setenv("SMTP_TIMEOUT_SECONDS", "0")
    get_settings.cache_clear()
    with pytest.raises(SettingsError) as caught:
        get_settings()
    assert "SMTP_TIMEOUT_SECONDS" in str(caught.value)
