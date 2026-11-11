"""配置占位（T01 空壳）。T02 将整体重写为完整 Settings。

阶段切换点见 CONTRACTS §2：本空壳不声明也不校验
DATABASE_URL / REDIS_URL / SECRET_KEY，T02 合并后才启用启动校验。
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """T01 最小配置：仅应用元信息 + create_app 需要的 docs 开关。"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    app_name: str = "stockpilot"
    app_version: str = "0.0.0"
    docs_enabled: bool = True


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """返回缓存的 Settings 单例；测试可用 get_settings.cache_clear()。"""
    return Settings()
