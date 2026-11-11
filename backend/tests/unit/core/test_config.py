"""T02 验收：配置校验、一次性错误汇总与敏感信息保护。"""

from __future__ import annotations

import os
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

# T02 阶段切换点兼容（见 PR「假设与偏差」）：CONTRACTS §2 自本任务起要求三个
# 必填变量，而 T01 的 tests/unit/test_smoke.py 会在收集期导入 app.main（模块级
# `app = create_app()`）。这两个文件都归 T01，T02 无权修改。本模块在收集顺序上
# 早于 test_smoke.py，故在此提供**仅测试进程内的占位值**（非真实凭据），让既有
# 冒烟测试仍可收集；各测试由 _isolated fixture 显式清理并验证缺失场景。
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test@db/app")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "t" * 40)

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
