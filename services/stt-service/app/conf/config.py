from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """STT worker settings."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    stt_queue: str = "stt.rpc"

    model_size: str = "base"
    device: str = "cpu"
    compute_type: str = "int8"
    beam_size: int = 5
    prefetch_count: int = 1


@lru_cache
def get_settings() -> Settings:
    return Settings()
