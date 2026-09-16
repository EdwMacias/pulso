from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Asistente Personal API"
    app_url: str = "http://localhost:5173"
    environment: str = "development"
    database_url: str = "sqlite:///./assistant.db"
    secret_key: str = "development-only-change-me"
    session_cookie_name: str = "session"
    csrf_cookie_name: str = "csrf_token"
    cookie_secure: bool = False
    session_ttl_hours: int = Field(default=24 * 30, ge=1, le=24 * 365)
    default_timezone: str = "America/Bogota"
    dev_auto_verify_email: bool = False
    dev_outbox_enabled: bool = False
    dev_outbox_path: Path = Path("dev-outbox.jsonl")
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_starttls: bool = True
    groq_api_key: str | None = None
    groq_chat_model: str = "llama-3.3-70b-versatile"
    groq_max_tool_calls: int = Field(default=6, ge=1, le=12)
    whatsapp_api_url: str | None = None
    whatsapp_api_key: str | None = None
    whatsapp_instance: str | None = None
    whatsapp_webhook_secret: str | None = None
    whatsapp_worker_poll_seconds: int = Field(default=2, ge=1, le=300)
    tts_api_key: str | None = None
    scheduler_poll_seconds: int = Field(default=15, ge=1, le=300)
    cors_origins: str = ""

    @field_validator("secret_key")
    @classmethod
    def secure_secret_outside_development(cls, value: str, info):
        environment = info.data.get("environment", "development")
        if environment == "production" and len(value) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters in production")
        return value

    @field_validator("app_url")
    @classmethod
    def valid_app_url(cls, value: str) -> str:
        value = value.rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("APP_URL must be an absolute HTTP(S) URL")
        return value

    @field_validator("whatsapp_api_url")
    @classmethod
    def valid_whatsapp_api_url(cls, value: str | None) -> str | None:
        if not value:
            return None
        value = value.rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("WHATSAPP_API_URL must be an absolute HTTP(S) URL")
        return value

    @field_validator("whatsapp_webhook_secret")
    @classmethod
    def secure_whatsapp_webhook_secret(cls, value: str | None) -> str | None:
        if not value:
            return None
        if len(value) < 32:
            raise ValueError("WHATSAPP_WEBHOOK_SECRET must be at least 32 characters")
        return value

    @model_validator(mode="after")
    def validate_environment_safety(self):
        if self.environment == "production" and (
            self.dev_auto_verify_email or self.dev_outbox_enabled
        ):
            raise ValueError("development email flags are forbidden in production")
        return self

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def email_delivery_configured(self) -> bool:
        return self.dev_outbox_enabled or self.smtp_configured

    @property
    def whatsapp_configured(self) -> bool:
        return bool(
            self.whatsapp_api_url
            and self.whatsapp_api_key
            and self.whatsapp_instance
            and self.whatsapp_webhook_secret
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
