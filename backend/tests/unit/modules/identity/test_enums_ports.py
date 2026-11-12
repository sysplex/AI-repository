"""M1-T01：领域枚举与端口声明（`CONTRACTS §5`）的可导入性与不变性。"""

from __future__ import annotations

import uuid
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from app.modules.identity import ports
from app.modules.identity.enums import UserRole, UserStatus
from app.modules.identity.ports import AccessClaims, MailSender, PasswordHasher, TokenCodec


def test_role_and_status_members_match_architecture() -> None:
    """`docs/02 §8`：角色 user/admin，状态 active/disabled。"""
    assert {role.value for role in UserRole} == {"user", "admin"}
    assert {status.value for status in UserStatus} == {"active", "disabled"}


def test_access_claims_is_immutable_and_utc_typed() -> None:
    """claims 是 frozen dataclass，避免解析后被业务代码改写。"""
    now = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)
    claims = AccessClaims(user_id=uuid.uuid4(), role=UserRole.USER, issued_at=now, expires_at=now)
    assert claims.role is UserRole.USER
    assert claims.issued_at.tzinfo is UTC
    with pytest.raises(FrozenInstanceError):
        claims.role = UserRole.ADMIN  # type: ignore[misc]


def test_ports_are_protocols_with_documented_names() -> None:
    """三个端口与 claims 均在公开导出清单里，且声明为 Protocol。"""
    assert set(ports.__all__) == {
        "AccessClaims",
        "MailSender",
        "PasswordHasher",
        "TokenCodec",
    }
    for protocol in (PasswordHasher, TokenCodec, MailSender):
        assert getattr(protocol, "_is_protocol", False) is True
