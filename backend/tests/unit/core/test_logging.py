"""T02 验收：JSON 日志、上下文注入、标准库桥接与幂等配置。"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.core.logging import (
    get_logger,
    request_id_var,
    setup_logging,
    task_id_var,
    user_id_var,
)

_PWD = "h" * 12
_SECRET = "s" * 40
_DB = f"postgresql+asyncpg://svc:{_PWD}@db.internal:5432/app"
_REDIS = "redis://localhost:6379/0"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.chdir(tmp_path)
    for name in ("DATABASE_URL", "REDIS_URL", "SECRET_KEY", "APP_ENV", "LOG_LEVEL"):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    request_id_var.set(None)
    user_id_var.set(None)
    task_id_var.set(None)
    yield
    request_id_var.set(None)
    user_id_var.set(None)
    task_id_var.set(None)


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": _DB,
        "redis_url": _REDIS,
        "secret_key": SecretStr(_SECRET),
    }
    values.update(overrides)
    return Settings(**values)


def _last_json(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    lines = [line for line in capsys.readouterr().err.splitlines() if line.strip()]
    assert lines
    return dict(json.loads(lines[-1]))


def test_json_log_contains_required_fields(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging(_settings())
    token = request_id_var.set("rid-json-1")
    try:
        get_logger("t.json").info("hello", answer=42)
    finally:
        request_id_var.reset(token)

    payload = _last_json(capsys)
    assert {"timestamp", "level", "event", "logger", "request_id"} <= set(payload)
    assert payload["event"] == "hello"
    assert payload["logger"] == "t.json"
    assert payload["level"] == "info"
    assert payload["request_id"] == "rid-json-1"
    assert payload["answer"] == 42


def test_user_and_task_id_are_injected(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging(_settings())
    rid = request_id_var.set("rid-ctx")
    uid = user_id_var.set("user-7")
    tid = task_id_var.set("task-9")
    try:
        get_logger("t.ctx").info("with-context")
    finally:
        request_id_var.reset(rid)
        user_id_var.reset(uid)
        task_id_var.reset(tid)

    payload = _last_json(capsys)
    assert payload["user_id"] == "user-7"
    assert payload["task_id"] == "task-9"
    assert payload["request_id"] == "rid-ctx"


def test_context_keys_absent_when_unset(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging(_settings())
    get_logger("t.empty").info("no-context")
    payload = _last_json(capsys)
    assert "request_id" not in payload
    assert "user_id" not in payload
    assert "task_id" not in payload


def test_console_format_when_log_json_false(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging(_settings(log_json=False))
    get_logger("t.console").info("human-readable")
    lines = [line for line in capsys.readouterr().err.splitlines() if line.strip()]
    assert lines
    assert "human-readable" in lines[-1]
    with pytest.raises(json.JSONDecodeError):
        json.loads(lines[-1])


def test_stdlib_loggers_use_same_json_format(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging(_settings())
    logging.getLogger("uvicorn.error").info("foreign message")
    payload = _last_json(capsys)
    assert payload["event"] == "foreign message"
    assert payload["logger"] == "uvicorn.error"
    assert "timestamp" in payload
    assert "level" in payload


def test_setup_logging_is_idempotent(capsys: pytest.CaptureFixture[str]) -> None:
    settings = _settings()
    setup_logging(settings)
    setup_logging(settings)
    get_logger("t.idem").info("once")
    lines = [line for line in capsys.readouterr().err.splitlines() if line.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["event"] == "once"


def test_log_level_filters_below_threshold(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging(_settings(log_level="WARNING"))
    get_logger("t.level").info("hidden")
    get_logger("t.level").warning("shown")
    lines = [line for line in capsys.readouterr().err.splitlines() if line.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["event"] == "shown"


def test_setup_logging_removes_external_handlers() -> None:
    external = logging.getLogger("uvicorn.error")
    stale = logging.NullHandler()
    external.addHandler(stale)
    setup_logging(_settings())
    assert stale not in external.handlers


def test_get_logger_exposes_bound_logger_api() -> None:
    logger = get_logger("t.type")
    assert callable(logger.info)
    assert callable(logger.warning)
