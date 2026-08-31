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

    # Realtime-call VAD: how long a silence (ms) ends the learner's utterance, and how
    # aggressively webrtcvad classifies speech (0=lenient .. 3=aggressive).
    vad_end_silence_ms: int = 1000
    vad_aggressiveness: int = 2

    # JWT validation: fetch auth-service's RS256 public key and verify forwarded tokens.
    auth_public_key_url: str = "http://localhost:8001/auth/public-key"
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
