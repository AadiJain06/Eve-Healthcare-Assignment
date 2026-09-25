"""Application configuration loaded from environment variables."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "EVE Diagnostics Booking Service"
    debug: bool = True

    # Security
    secret_key: str = "change-me-to-a-long-random-string"
    access_token_expire_minutes: int = 60
    algorithm: str = "HS256"

    # Database
    database_url: str = (
        "postgresql+psycopg://eve:eve@localhost:5432/eve_diagnostics"
    )

    # Payment simulation
    payment_success_rate: float = 1.0
    webhook_secret: str = "webhook-shared-secret"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
