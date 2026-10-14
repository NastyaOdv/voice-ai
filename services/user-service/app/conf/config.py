from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class DBSettings(BaseSettings):
    """Database connection settings (env vars prefixed with DB_)."""

    model_config = SettingsConfigDict(
        env_prefix="DB_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    username: str = "postgres"
    password: str = "postgres"
    database: str = "user_service"
    host: str = "localhost"
    port: str = "5432"
    # "disable" for local Docker Postgres; set DB_SSLMODE=require for managed/cloud PG.
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

    # JWT validation: auth-service's RS256 public key (PEM), used to verify forwarded
    # tokens. Newlines may be real line breaks or escaped "\n" (friendlier for .env).
    jwt_public_key: str = ""
    jwt_algorithm: str = "RS256"


# Instantiated on first use and cached — call these where the settings are needed.
@lru_cache
def get_db_settings() -> DBSettings:
    return DBSettings()


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_system_settings() -> SystemSettings:
    return SystemSettings()
