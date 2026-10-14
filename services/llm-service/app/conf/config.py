from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """LLM worker settings.

    Every call goes through the LiteLLM proxy (LLM gateway); this service never talks to a
    provider directly. `llm_base_url` points at the proxy and `llm_api_key` is a LiteLLM
    *virtual key* — provider keys live inside LiteLLM and are never read here. `llm_model`
    is a LiteLLM public model name (alias) that the proxy resolves to an actual model, so
    changing model or provider is done in the LiteLLM UI, not in this repository.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    llm_queue: str = "llm.rpc"

    # A LiteLLM alias, not a provider model id — define what it maps to in the LiteLLM UI.
    llm_model: str = "tutor-default"
    llm_max_tokens: int = 1024

    # LiteLLM proxy endpoint (Anthropic-compatible /v1/messages) + virtual key.
    llm_base_url: str = "http://localhost:4000"
    llm_api_key: str = ""

    prefetch_count: int = 1


@lru_cache
def get_settings() -> Settings:
    return Settings()
