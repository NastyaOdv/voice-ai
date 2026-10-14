from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class DBSettings(BaseSettings):
    """Database connection settings (env vars prefixed with DB_)."""

    model_config = SettingsConfigDict(
        env_prefix="DB_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    username: str = "postgres"
    password: str = "postgres"
    database: str = "orchestrator_service"
    host: str = "localhost"
    port: str = "5434"
    sslmode: str = "disable"


class SystemSettings(BaseSettings):
    """Process-level settings (env var ENV)."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    env: str = "dev"  # "dev" | "prod"


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    redis_url: str = "redis://localhost:6379/0"
    session_ttl_seconds: int = 3600

    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    storage_dir: str = "storage/audio"
    llm_history_max_pairs: int = 40
    llm_history_keep_pairs: int = 25
    vad_end_silence_ms: int = 700
    vad_aggressiveness: int = 3
    jwt_public_key: str = ""
    jwt_algorithm: str = "RS256"


@lru_cache
def get_db_settings() -> DBSettings:
    return DBSettings()


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_system_settings() -> SystemSettings:
    return SystemSettings()
