"""Typed application configuration for the Cortex AI Publisher module.

Every tunable value lives in one place so the team can integrate simply
by editing ``.env``. Secrets are loaded from environment variables and
never logged.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed settings sourced from environment variables / ``.env``."""

    # ------------------------------------------------------------------ #
    # Service metadata
    # ------------------------------------------------------------------ #
    app_name: str = "Cortex AI Publisher"
    app_version: str = "1.0.0"
    environment: str = "development"

    # ------------------------------------------------------------------ #
    # Database
    # ------------------------------------------------------------------ #
    database_url: str = "sqlite+aiosqlite:///./data/cortex_publisher.db"

    # ------------------------------------------------------------------ #
    # AI providers (at least one key is required to publish)
    # ------------------------------------------------------------------ #
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # ------------------------------------------------------------------ #
    # Upstream integrations (consumed only, never implemented here)
    # ------------------------------------------------------------------ #
    member1_persona_url: str = "http://localhost:8002/api/persona"
    member2_topics_url: str = "http://localhost:8001/api/topics/approved"

    # ------------------------------------------------------------------ #
    # Scheduler
    # ------------------------------------------------------------------ #
    scheduler_enabled: bool = True
    scheduler_interval_minutes: int = 30

    # ------------------------------------------------------------------ #
    # Publish queue and retry policy
    # ------------------------------------------------------------------ #
    queue_batch_size: int = 5
    publication_batch_size: int = 1
    publish_max_attempts: int = 3
    retry_backoff_seconds: int = 60

    # ------------------------------------------------------------------ #
    # HTTP / logging
    # ------------------------------------------------------------------ #
    request_timeout_seconds: float = 15.0
    log_level: str = "INFO"
    log_file: str = "logs/publisher.log"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return the singleton settings instance."""
    return Settings()


settings = get_settings()
