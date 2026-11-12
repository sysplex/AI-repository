"""M0-F2 回归（Issue #25）：CORS 通配符必须在配置层被拒绝。

`install_middlewares` 固定 `allow_credentials=True`；CORSMiddleware 在该模式下
遇到 `*` 会回显请求的 Origin，等同于允许任意站点携带凭据读取响应。
因此 `Settings` 在任何环境下都必须拒绝含 `*` 的来源列表。
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport
from pydantic import SecretStr, ValidationError

from app.core.config import Settings, SettingsError, get_settings
from app.core.middleware import install_middlewares

_DB = "postgresql+asyncpg://svc@db.internal:5432/app"
_REDIS = "redis://localhost:6379/0"
_SECRET = "s" * 40
_WILDCARD_REASON = "CORS_ORIGINS: 启用凭据时不允许通配符 *，请列出明确来源"
_ENV_KEYS = ("APP_ENV", "DATABASE_URL", "REDIS_URL", "SECRET_KEY", "CORS_ORIGINS")


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """空临时目录 + 明确必填变量，杜绝 .env 与 lru_cache 串扰。"""
    monkeypatch.chdir(tmp_path)
    for name in _ENV_KEYS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATABASE_URL", _DB)
    monkeypatch.setenv("REDIS_URL", _REDIS)
    monkeypatch.setenv("SECRET_KEY", _SECRET)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": _DB,
        "redis_url": _REDIS,
        "secret_key": SecretStr(_SECRET),
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.parametrize("raw", ["*", '["*"]', "https://a.example,*"])
def test_wildcard_origins_fail_to_load(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    monkeypatch.setenv("CORS_ORIGINS", raw)
    with pytest.raises(SettingsError) as caught:
        get_settings()
    assert caught.value.problems == [_WILDCARD_REASON]
    message = str(caught.value)
    assert _WILDCARD_REASON in message
    assert _DB not in message
    assert _REDIS not in message
    assert _SECRET not in message


@pytest.mark.parametrize("app_env", ["local", "ci", "staging", "production"])
def test_wildcard_rejected_in_every_environment(
    monkeypatch: pytest.MonkeyPatch, app_env: str
) -> None:
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(SettingsError) as caught:
        get_settings()
    assert _WILDCARD_REASON in caught.value.problems


@pytest.mark.parametrize("raw", ["*", '["*"]', "https://a.example, *", ["*"]])
def test_direct_settings_rejects_wildcard(raw: Any) -> None:
    with pytest.raises(ValidationError):
        _settings(cors_origins=raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://a.example", ["https://a.example"]),
        (
            "https://a.example, https://b.example ,",
            ["https://a.example", "https://b.example"],
        ),
        ('["https://a.example"]', ["https://a.example"]),
        (
            '["https://a.example","https://b.example"]',
            ["https://a.example", "https://b.example"],
        ),
        (
            ["https://a.example", "https://b.example"],
            ["https://a.example", "https://b.example"],
        ),
        ("  ", []),
    ],
)
def test_explicit_origins_still_parse(raw: Any, expected: list[str]) -> None:
    assert _settings(cors_origins=raw).cors_origins == expected


def test_explicit_origins_load_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example,https://b.example")
    assert get_settings().cors_origins == ["https://a.example", "https://b.example"]


def test_wildcard_reported_together_with_missing_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("DATABASE_URL", "REDIS_URL", "SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(SettingsError) as caught:
        get_settings()
    problems = caught.value.problems
    assert _WILDCARD_REASON in problems
    assert sum("缺失必填项" in problem for problem in problems) == 3
    assert len(problems) == 4


async def test_middleware_never_echoes_unlisted_origin() -> None:
    """未改 middleware.py：明确来源列表下，陌生 Origin 不被回显。"""
    app = FastAPI()
    install_middlewares(app, _settings(cors_origins=["https://a.example"]))

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"pong": "ok"}

    headers = {"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"}
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.options("/ping", headers=headers)
    # CORSMiddleware 对未列入的 Origin 返回 400 且不下发 ACAO；浏览器因此不会放行。
    # 注意它仍会带 `Access-Control-Allow-Credentials: true`，这是中间件固定行为，
    # 缺 ACAO 时无风险，也正是为什么 `*` 必须在配置层就拦截。
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
