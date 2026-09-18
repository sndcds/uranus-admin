from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from pydantic import EmailStr, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    app_env: Literal["development", "test", "staging", "production"] = "production"
    app_debug: bool = False
    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8000, ge=1, le=65535)
    database_url: SecretStr = SecretStr("postgresql+asyncpg://localhost/uranus")
    admin_database_url: SecretStr | None = None
    auth_public_origin: str | None = None
    auth_session_seconds: int = Field(default=3600, ge=300, le=28800)
    auth_session_heartbeat_seconds: int = Field(default=60, ge=1, le=300)
    auth_revoked_retention_seconds: int = Field(default=86400, ge=0, le=2592000)
    auth_idle_seconds: int = Field(default=900, ge=60, le=3600)
    admin_auth_management_database_url: SecretStr | None = None
    uranus_api_url: str = "http://localhost:8080"
    # Confirmed by the Uranus operator for the supplied live backup (2026-09-14).
    uranus_timestamp_timezone: str | None = "UTC"
    admin_timezone: str = "Europe/Berlin"
    event_timezone: str = "Europe/Berlin"
    check_job_lease_seconds: int = Field(default=120, ge=30, le=3600)
    check_worker_poll_seconds: int = Field(default=2, ge=1, le=60)
    url_check_concurrency: int = Field(default=8, ge=1, le=16)
    url_check_batch_size: int = Field(default=100, ge=1, le=1000)
    url_check_success_ttl_seconds: int = Field(default=86400, ge=3600, le=604800)
    url_check_failure_ttl_seconds: int = Field(default=3600, ge=300, le=86400)
    notifications_delivery_enabled: bool = False
    notification_max_emails_per_recipient_per_day: int = Field(default=3, ge=1, le=20)
    notification_smtp_host: str | None = None
    notification_smtp_port: int = Field(default=587, ge=1, le=65535)
    notification_smtp_username: str | None = None
    notification_smtp_password: SecretStr | None = None
    notification_smtp_from_email: EmailStr = "notifications@kulturbytes.de"
    notification_smtp_from_name: str = "Kulturbytes"
    notification_smtp_starttls: bool = True
    notification_smtp_timeout_seconds: int = Field(default=20, ge=1, le=60)
    notification_lease_seconds: int = Field(default=300, ge=120, le=3600)
    notification_worker_poll_seconds: int = Field(default=3600, ge=10, le=86400)
    notification_quality_start_hour: int = Field(default=8, ge=0, le=23)
    notification_important_days: int = Field(default=7, ge=3, le=30)
    notification_urgent_days: int = Field(default=2, ge=0, le=2)
    admin_public_base_url: str = "https://admin.kulturbytes.de"
    kulturbytes_app_public_base_url: str = "https://app.kulturbytes.de"
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

    @field_validator("auth_public_origin", "admin_public_base_url")
    @classmethod
    def valid_auth_origin(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.hostname
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username
            or "*" in value
        ):
            raise ValueError("AUTH_PUBLIC_ORIGIN must be one exact HTTP(S) origin")
        return value

    @field_validator("kulturbytes_app_public_base_url")
    @classmethod
    def valid_app_origin(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or any(char in value for char in "*\\?#")
            or any(ord(char) < 33 or ord(char) == 127 for char in value)
            or parsed.hostname == "admin.kulturbytes.de"
        ):
            raise ValueError("KULTURBYTES_APP_PUBLIC_BASE_URL must be an exact user-app origin")
        # Accessing port also rejects invalid/non-numeric/out-of-range ports.
        _ = parsed.port
        return value

    @field_validator("admin_auth_management_database_url")
    @classmethod
    def valid_management_url(cls, value: SecretStr | None) -> SecretStr | None:
        if value and not value.get_secret_value().startswith("postgresql+asyncpg://"):
            raise ValueError("Management database must use postgresql+asyncpg")
        return value

    @property
    def session_cookie(self) -> str:
        return (
            "admin_session" if self.app_env in {"development", "test"} else "__Host-admin_session"
        )

    @property
    def origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def secure_configuration(self) -> "Settings":
        if self.notifications_delivery_enabled:
            if not self.notification_smtp_host:
                raise ValueError("Notification delivery requires SMTP host")
        if (
            self.app_env not in {"development", "test"} or self.notifications_delivery_enabled
        ) and not self.kulturbytes_app_public_base_url.startswith("https://"):
            raise ValueError("Notification recipient links require HTTPS")
        if urlsplit(self.kulturbytes_app_public_base_url).hostname in {
            urlsplit(self.admin_public_base_url).hostname,
            urlsplit(self.auth_public_origin or "").hostname,
        }:
            raise ValueError("Notification recipient app must be separate from system admin")
        if self.notification_lease_seconds <= self.notification_smtp_timeout_seconds * 4:
            raise ValueError("Notification lease must exceed SMTP operation budget")
        for value in (self.notification_smtp_from_email, self.notification_smtp_from_name):
            if any(ord(char) < 32 for char in value):
                raise ValueError("Invalid mail header")
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
        if self.auth_session_heartbeat_seconds >= self.auth_idle_seconds:
            raise ValueError("Session heartbeat must be smaller than idle timeout")
        if self.auth_idle_seconds > self.auth_session_seconds:
            raise ValueError("Idle timeout must not exceed session lifetime")
        if self.app_env not in {"development", "test"}:
            if self.auth_public_origin and not self.auth_public_origin.startswith("https://"):
                raise ValueError("Production authentication requires an HTTPS origin")
            if self.app_debug or self.dev_auth_enabled or self.openapi_enabled:
                raise ValueError(
                    "Debug, development auth and public OpenAPI require development/test"
                )
        if self.dev_auth_enabled and (
            self.dev_admin_token is None or len(self.dev_admin_token.get_secret_value()) < 32
        ):
            raise ValueError("Development auth requires a secret of at least 32 characters")
        return self
