from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated settings loaded from the environment with a stable prefix."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SUITSFLOW_",
        extra="ignore",
        frozen=True,
    )

    app_name: str = "SuitsFlow"
    environment: Literal["local", "test", "staging", "production"] = "local"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://suitsflow:suitsflow@localhost:5432/suitsflow"
    database_timeout_seconds: float = Field(default=3.0, gt=0, le=30)


@lru_cache
def get_settings() -> Settings:
    """Return one immutable settings object per process."""
    return Settings()
