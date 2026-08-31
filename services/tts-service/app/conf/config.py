from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """TTS worker settings."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    tts_queue: str = "tts.rpc"

    # Path to the Piper voice (.onnx). Its config is `<model_path>.json`, baked into
    # the image next to the model.
    model_path: str = "/app/voices/en_US-lessac-medium.onnx"
    prefetch_count: int = 1


@lru_cache
def get_settings() -> Settings:
    return Settings()
