"""M1-T03：`CONTRACTS §8` 安全原语组合层与 access 颁发。"""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.modules.identity.enums import UserRole
from app.modules.identity.ports import PasswordHasher, TokenCodec
from app.modules.identity.security import (
    hash_opaque_token,
    hash_password,
    new_opaque_token,
    verify_password,
)
from app.modules.identity.tokens import issue_access

_TEST_HASH = "argon2$test-hash"
_STUB_RESULT = "signed-access-token"


class _StubHasher:
    """`PasswordHasher` 端口的最小替身，用于验证组合层不擅自解包/记录。"""

    def hash(self, password: str) -> str:
        return f"stub:{password}"

    def verify(self, password: str, password_hash: str) -> bool:
        return password_hash == f"stub:{password}"


class _StubCodec:
    """记录调用参数，避免单元测试依赖真实 JWT 实现。"""

    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}

    def issue_access(
        self,
        *,
        user_id: uuid.UUID,
        role: UserRole,
        now: datetime,
        ttl_seconds: int,
    ) -> str:
        self.kwargs = {
            "user_id": user_id,
            "role": role,
            "now": now,
            "ttl_seconds": ttl_seconds,
        }
        return _STUB_RESULT

    def decode_access(self, token: str, *, now: datetime) -> Any:  # pragma: no cover
        raise NotImplementedError


def test_hash_and_verify_password_delegate_to_port() -> None:
    hasher = cast(PasswordHasher, _StubHasher())
    secret = SecretStr("Str0ngPassw0rd!")
    hashed = hash_password(hasher, secret)
    assert hashed == "stub:Str0ngPassw0rd!"
    assert verify_password(hasher, secret, hashed) is True
    assert verify_password(hasher, SecretStr("OtherPassw0rd!"), hashed) is False


def test_new_opaque_token_is_random_and_url_safe() -> None:
    tokens = [new_opaque_token() for _ in range(20)]
    assert len(set(tokens)) == len(tokens)
    for token in tokens:
        assert re.fullmatch(r"[A-Za-z0-9_-]+", token)
        assert len(token) >= 43  # 32 字节 base64url


def test_hash_opaque_token_is_fixed_length_sha256() -> None:
    token = new_opaque_token()
    digest = hash_opaque_token(token)
    assert len(digest) == 64
    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    assert digest == hash_opaque_token(token)
    assert digest != hash_opaque_token(new_opaque_token())
    assert digest == hashlib.sha256(token.encode("utf-8")).hexdigest()


def test_plain_token_never_appears_in_digest() -> None:
    token = new_opaque_token()
    assert token not in hash_opaque_token(token)
    assert _TEST_HASH not in hash_opaque_token(token)


def test_security_primitives_write_no_logs(caplog: pytest.LogCaptureFixture) -> None:
    """明文令牌绝不写日志（T03 验收项）。"""
    with caplog.at_level("DEBUG"):
        token = new_opaque_token()
        hash_opaque_token(token)
        hash_password(cast(PasswordHasher, _StubHasher()), SecretStr("SomePassw0rd!"))
    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert token not in joined
    assert "SomePassw0rd!" not in joined


def test_third_party_crypto_sdks_only_imported_in_adapters() -> None:
    """架构守卫：`argon2` / `jwt` 只允许出现在两个 adapter 里（T03 验收项）。

    用自动化扫描替代 PR 里的一次性 `grep`，后续任务若在 service / 路由里直接
    `import jwt`，这里会失败，而不是靠人肉复查。
    """
    app_root = Path(__file__).resolve().parents[4] / "app"
    allowed = {
        app_root / "modules" / "identity" / "adapters" / "password_hasher.py",
        app_root / "modules" / "identity" / "adapters" / "token_codec.py",
    }
    pattern = re.compile(r"^\s*(?:import|from)\s+(argon2|jwt)\b", re.MULTILINE)
    offenders: list[str] = []
    for path in app_root.rglob("*.py"):
        if path in allowed:
            continue
        if pattern.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(app_root)))
    assert offenders == [], f"以下文件越界 import 了外部加密 SDK：{offenders}"


def test_issue_access_uses_settings_ttl() -> None:
    codec = cast(TokenCodec, _StubCodec())
    settings = cast(Settings, SimpleNamespace(access_token_ttl_seconds=900))
    now = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
    user_id = uuid.uuid4()
    pair_access, expires_in = issue_access(
        codec, user_id=user_id, role=UserRole.ADMIN, settings=settings, now=now
    )
    assert pair_access == _STUB_RESULT
    assert expires_in == 900
    recorded = cast(_StubCodec, codec).kwargs
    assert recorded["ttl_seconds"] == 900
    assert recorded["user_id"] == user_id
    assert recorded["role"] is UserRole.ADMIN
    assert recorded["now"] == now
