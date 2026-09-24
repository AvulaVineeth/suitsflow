from functools import lru_cache
from typing import Literal
from uuid import UUID

from pydantic import Field, SecretStr, model_validator
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
    development_auth_enabled: bool = False
    development_auth_token: SecretStr | None = None
    development_user_id: UUID | None = None
    development_tenant_id: UUID | None = None
    s3_bucket: str | None = Field(default=None, min_length=3, max_length=63)
    s3_region: str = "us-east-1"
    s3_profile: str | None = Field(default=None, min_length=1)
    s3_expected_bucket_owner: str | None = Field(default=None, pattern=r"^[0-9]{12}$")
    upload_timeout_seconds: float = Field(default=120, gt=0, le=600)

    @model_validator(mode="after")
    def validate_development_auth(self) -> "Settings":
        if self.development_auth_enabled:
            if self.environment not in {"local", "test"}:
                raise ValueError("Development authentication is allowed only in local/test")
            if (
                self.development_auth_token is None
                or len(self.development_auth_token.get_secret_value()) < 32
                or self.development_user_id is None
                or self.development_tenant_id is None
            ):
                raise ValueError(
                    "Development authentication needs IDs and a token of 32+ characters"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return one immutable settings object per process."""
    return Settings()
