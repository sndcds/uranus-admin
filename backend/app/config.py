from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    app_env: Literal["development", "test", "staging", "production"] = "production"
    app_debug: bool = False
    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8000, ge=1, le=65535)
    database_url: SecretStr = SecretStr("postgresql+asyncpg://localhost/uranus")
    admin_database_url: SecretStr | None = None
    uranus_api_url: str = "http://localhost:8080"
    # Confirmed by the Uranus operator for the supplied live backup (2026-09-14).
    uranus_timestamp_timezone: str | None = "UTC"
    admin_timezone: str = "Europe/Berlin"
    event_timezone: str = "Europe/Berlin"
    upcoming_days: int = Field(default=14, ge=1, le=365)
    image_orphan_grace_hours: int = Field(default=48, ge=1, le=8760)
    pending_age_days: int = Field(default=14, ge=1, le=3650)
    activation_age_days: int = Field(default=7, ge=1, le=3650)
    cors_origins: str = ""
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=5, ge=0, le=50)
    db_timeout_seconds: int = Field(default=10, ge=1, le=120)
    openapi_enabled: bool = False
    dev_auth_enabled: bool = False
    dev_admin_token: SecretStr | None = None

    @field_validator("admin_timezone", "event_timezone", "uranus_timestamp_timezone")
    @classmethod
    def valid_timezone(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                ZoneInfo(value)
            except (KeyError, ValueError) as exc:
                raise ValueError("Unknown IANA timezone") from exc
        return value

    @field_validator("database_url")
    @classmethod
    def valid_database(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use postgresql+asyncpg")
        return value

    @field_validator("admin_database_url")
    @classmethod
    def valid_admin_database(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value().startswith("postgresql+asyncpg://"):
            raise ValueError("ADMIN_DATABASE_URL must use postgresql+asyncpg")
        return value

    @property
    def origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def secure_configuration(self) -> "Settings":
        for origin in self.origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username
                or "*" in origin
            ):
                raise ValueError("CORS_ORIGINS must contain explicit HTTP(S) origins")
        if self.app_env not in {"development", "test"}:
            if self.app_debug or self.dev_auth_enabled or self.openapi_enabled:
                raise ValueError(
                    "Debug, development auth and public OpenAPI require development/test"
                )
        if self.dev_auth_enabled and (
            self.dev_admin_token is None or len(self.dev_admin_token.get_secret_value()) < 32
        ):
            raise ValueError("Development auth requires a secret of at least 32 characters")
        return self
