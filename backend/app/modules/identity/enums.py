"""M1 identity 领域枚举（T01）。

`CONTRACTS §4` 由 `schemas.py` 对外导出这两个类型；为避免 T01 的 `ports.py`
反向依赖 T02 才创建的 `schemas.py`，枚举定义前移到本模块，`schemas.py` 重新导出，
公开签名保持不变。
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["UserRole", "UserStatus"]


class UserRole(StrEnum):
    """用户角色；M1 仅 user / admin（`docs/02-architecture.md §8`）。"""

    USER = "user"
    ADMIN = "admin"


class UserStatus(StrEnum):
    """账号状态；disabled 一律视为未认证。"""

    ACTIVE = "active"
    DISABLED = "disabled"
