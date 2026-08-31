from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """LLM worker settings. ANTHROPIC_API_KEY is read by the SDK, not stored here."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    llm_queue: str = "llm.rpc"

    llm_model: str = "claude-opus-5"
    llm_max_tokens: int = 1024

    prefetch_count: int = 1


@lru_cache
def get_settings() -> Settings:
    return Settings()
