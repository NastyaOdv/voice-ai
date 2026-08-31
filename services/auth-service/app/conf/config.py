from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class DBSettings(BaseSettings):
    """Database connection settings (env vars prefixed with DB_)."""

    model_config = SettingsConfigDict(
        env_prefix="DB_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    username: str = "postgres"
    password: str = "postgres"
    database: str = "auth_service"
    host: str = "localhost"
    port: str = "5433"
    # "disable" for local Docker Postgres; set DB_SSLMODE=require for managed/cloud PG.
    sslmode: str = "disable"


class SystemSettings(BaseSettings):
    """Process-level settings (env var ENV)."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    env: str = "dev"  # "dev" | "prod"


class Settings(BaseSettings):
    """Application settings (JWT + Google OAuth)."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    jwt_algorithm: str = "RS256"
    jwt_private_key_path: str = "keys/private.pem"
    jwt_public_key_path: str = "keys/public.pem"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Auth cookies. `Secure` must be True over HTTPS (prod); False for local http.
    cookie_secure: bool = False

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8001/auth/google/callback"

    # Where to send the browser back to after the Google OAuth dance. The callback
    # sets the auth cookies and redirects here (SPA route), instead of returning JSON.
    frontend_url: str = "http://localhost:4200"


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
