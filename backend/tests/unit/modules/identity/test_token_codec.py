"""M1-T03：HS256 access 令牌签发/解码与五类失败收敛。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest

from app.core.errors import TokenExpired, Unauthenticated
from app.modules.identity.adapters.token_codec import JWTTokenCodec
from app.modules.identity.enums import UserRole

_SECRET = "a" * 48
_OTHER_SECRET = "b" * 48
_NOW = datetime(2026, 11, 12, 12, 0, 0, tzinfo=UTC)
_TTL = 900


def _codec(secret: str = _SECRET) -> JWTTokenCodec:
    return JWTTokenCodec(secret, "HS256")


def test_constructor_validates_secret_and_algorithm() -> None:
    with pytest.raises(ValueError, match="32"):
        JWTTokenCodec("short", "HS256")
    with pytest.raises(ValueError, match="HS256"):
        JWTTokenCodec(_SECRET, "RS256")


def test_roundtrip_and_exp_is_now_plus_ttl(frozen_clock: Any) -> None:
    del frozen_clock  # 冻结进程时钟，验证解码只依赖显式传入的 now
    codec = _codec()
    user_id = uuid.uuid4()
    token = codec.issue_access(user_id=user_id, role=UserRole.ADMIN, now=_NOW, ttl_seconds=_TTL)
    claims = codec.decode_access(token, now=_NOW)
    assert claims.user_id == user_id
    assert claims.role is UserRole.ADMIN
    assert claims.issued_at == _NOW
    assert claims.expires_at == _NOW + timedelta(seconds=_TTL)

    # 直接看 payload 时同样要关掉 PyJWT 的进程时钟校验：`iat` 用的是本用例的固定
    # 时间点（2026-11-12 12:00 UTC），在 CI 的真实系统时间下会被判为「尚未生效」。
    payload = jwt.decode(
        token,
        _SECRET,
        algorithms=["HS256"],
        options={"verify_exp": False, "verify_iat": False},
    )
    assert set(payload) == {"sub", "role", "iat", "exp"}
    assert payload["sub"] == str(user_id)
    assert payload["role"] == "admin"
    assert payload["iat"] == int(_NOW.timestamp())
    assert payload["exp"] == int((_NOW + timedelta(seconds=_TTL)).timestamp())


def test_frozen_claims_are_immutable() -> None:
    claims = _codec().decode_access(
        _codec().issue_access(user_id=uuid.uuid4(), role=UserRole.USER, now=_NOW, ttl_seconds=_TTL),
        now=_NOW,
    )
    with pytest.raises((AttributeError, TypeError)):
        claims.role = UserRole.ADMIN  # type: ignore[misc]


def test_expired_token_raises_token_expired() -> None:
    token = _codec().issue_access(user_id=uuid.uuid4(), role=UserRole.USER, now=_NOW, ttl_seconds=1)
    with pytest.raises(TokenExpired) as exc:
        _codec().decode_access(token, now=_NOW + timedelta(seconds=1))
    assert exc.value.__cause__ is None
    assert "Signature has expired" not in str(exc.value)


@pytest.mark.parametrize("reason", ["tampered", "wrong_secret", "missing_sub", "bad_role"])
def test_invalid_tokens_raise_unauthenticated(reason: str) -> None:
    codec = _codec()
    payload: dict[str, Any] = {
        "sub": str(uuid.uuid4()),
        "role": "user",
        "iat": int(_NOW.timestamp()),
        "exp": int((_NOW + timedelta(seconds=_TTL)).timestamp()),
    }
    if reason == "missing_sub":
        payload.pop("sub")
    if reason == "bad_role":
        payload["role"] = "superuser"
    token = jwt.encode(payload, _SECRET, algorithm="HS256")
    if reason == "tampered":
        token = token[:-3] + ("abc" if not token.endswith("abc") else "xyz")
    active = _codec(_OTHER_SECRET) if reason == "wrong_secret" else codec
    with pytest.raises(Unauthenticated) as exc:
        active.decode_access(token, now=_NOW)
    assert exc.value.__cause__ is None
    assert "Invalid" not in str(exc.value)


def test_non_string_token_and_garbage_are_rejected() -> None:
    for bad in ("", "not-a-jwt", "a.b.c"):
        with pytest.raises(Unauthenticated):
            _codec().decode_access(bad, now=_NOW)


@pytest.mark.parametrize(
    ("claim", "value"),
    [("iat", 1.5), ("exp", 1.5), ("iat", True), ("exp", False), ("exp", "1800000000")],
)
def test_non_integer_epoch_claims_are_rejected(claim: str, value: object) -> None:
    """`iat` / `exp` 必须是整数 epoch 秒；浮点、布尔、字符串一律视为非法令牌。"""
    payload: dict[str, Any] = {
        "sub": str(uuid.uuid4()),
        "role": "user",
        "iat": int(_NOW.timestamp()),
        "exp": int((_NOW + timedelta(seconds=_TTL)).timestamp()),
    }
    payload[claim] = value
    token = jwt.encode(payload, _SECRET, algorithm="HS256")
    with pytest.raises(Unauthenticated):
        _codec().decode_access(token, now=_NOW)


def test_exp_not_after_iat_is_rejected() -> None:
    """`exp <= iat` 的令牌无有效窗口，即使尚未到期也判为非法。"""
    token = _codec().issue_access(user_id=uuid.uuid4(), role=UserRole.USER, now=_NOW, ttl_seconds=0)
    with pytest.raises(Unauthenticated):
        _codec().decode_access(token, now=_NOW - timedelta(seconds=10))


def test_error_messages_are_m0_defaults() -> None:
    token = _codec().issue_access(user_id=uuid.uuid4(), role=UserRole.USER, now=_NOW, ttl_seconds=1)
    with pytest.raises(TokenExpired) as expired:
        _codec().decode_access(token, now=_NOW + timedelta(seconds=5))
    with pytest.raises(Unauthenticated) as invalid:
        _codec().decode_access("garbage", now=_NOW)
    assert expired.value.code.value == "TOKEN_EXPIRED"
    assert invalid.value.code.value == "UNAUTHENTICATED"
    assert expired.value.http_status == 401
    assert invalid.value.http_status == 401
