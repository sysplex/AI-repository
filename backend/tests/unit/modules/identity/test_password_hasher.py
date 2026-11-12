# ruff: noqa: S105, S106
# 本文件使用伪造密码字面量验证哈希行为，均非真实凭据。
"""M1-T03：Argon2 适配器行为与第三方 SDK 边界（CONTRACTS §6 / T03 验收）。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

from app.modules.identity.adapters.password_hasher import Argon2PasswordHasher

_PASSWORD = "Str0ngPassw0rd!"


def test_hash_is_salted_and_roundtrips() -> None:
    hasher = Argon2PasswordHasher()
    first = hasher.hash(_PASSWORD)
    second = hasher.hash(_PASSWORD)
    assert first.startswith("$argon2")
    assert second.startswith("$argon2")
    assert first != second  # 每次盐不同
    assert hasher.verify(_PASSWORD, first) is True
    assert hasher.verify(_PASSWORD, second) is True


def test_verify_rejects_wrong_password() -> None:
    hasher = Argon2PasswordHasher()
    hashed = hasher.hash(_PASSWORD)
    assert hasher.verify("OtherPassw0rd!", hashed) is False


def test_verify_never_raises_on_malformed_hash() -> None:
    hasher = Argon2PasswordHasher()
    malformed = ["", "not-a-hash", "$argon2$broken", "$2b$12$abcdef", "a" * 500]
    for candidate in malformed:
        assert hasher.verify(_PASSWORD, candidate) is False
    assert hasher.verify(_PASSWORD, cast(str, None)) is False
    assert hasher.verify(_PASSWORD, cast(str, 123)) is False


def test_verify_handles_wrong_password_type() -> None:
    hasher = Argon2PasswordHasher()
    hashed = hasher.hash(_PASSWORD)
    assert hasher.verify(cast(Any, None), hashed) is False


def test_third_party_sdk_imports_are_confined_to_adapters() -> None:
    """`argon2` / `jwt` 的直接 import 只允许出现在各自适配器文件里。"""
    app_root = Path(__file__).resolve().parents[4] / "app"
    allowed = {
        "argon2": "modules/identity/adapters/password_hasher.py",
        "jwt": "modules/identity/adapters/token_codec.py",
    }
    found: dict[str, list[str]] = {name: [] for name in allowed}
    for path in app_root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        relative = path.relative_to(app_root).as_posix()
        for library in allowed:
            if re.search(rf"^\s*(?:import|from)\s+{library}\b", source, re.MULTILINE):
                found[library].append(relative)
    assert found["argon2"] == [allowed["argon2"]]
    assert found["jwt"] == [allowed["jwt"]]
