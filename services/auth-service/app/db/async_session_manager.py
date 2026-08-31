import contextlib
from typing import Any, AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.conf import config
from app.logger.logger_config import logger

settings = config.get_db_settings()
db_url = (
    f"postgresql+psycopg://{settings.username}:{settings.password}"
    f"@{settings.host}:{settings.port}/{settings.database}?sslmode={settings.sslmode}"
)


class Base(DeclarativeBase):
    __mapper_args__ = {"eager_defaults": True}


class DatabaseSessionManager:
    def __init__(self, host: str, engine_kwargs: dict[str, Any] | None = None) -> None:
        logger.debug(f"Connecting to {settings.host}:{settings.port}")
        try:
            self._engine = create_async_engine(host, **(engine_kwargs or {}))
            self._sessionmaker = async_sessionmaker(
                bind=self._engine,
                expire_on_commit=False,
                class_=AsyncSession,
                autocommit=False,
            )
            logger.info("Database engine created successfully")
        except Exception:
            logger.exception("Failed to create async engine")
            raise

    async def close(self) -> None:
        if self._engine is None:
            raise RuntimeError("DatabaseSessionManager is not initialized")
        logger.info("Closing database engine")
        await self._engine.dispose()
        self._engine = None
        self._sessionmaker = None

    @contextlib.asynccontextmanager
    async def connect(self) -> AsyncIterator[AsyncConnection]:
        if self._engine is None:
            raise RuntimeError("DatabaseSessionManager is not initialized")
        async with self._engine.begin() as connection:
            try:
                yield connection
            except Exception as exc:
                logger.error(f"Error during connection: {exc}, rolling back")
                await connection.rollback()
                raise

    @contextlib.asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        if self._sessionmaker is None:
            raise RuntimeError("DatabaseSessionManager is not initialized")
        session = self._sessionmaker()
        try:
            yield session
        except Exception as exc:
            logger.error(f"Session error: {exc}, performing rollback")
            await session.rollback()
            raise
        finally:
            await session.close()


sessionmanager = DatabaseSessionManager(
    db_url,
    {"echo": False, "pool_size": 10, "max_overflow": 0, "pool_pre_ping": True},
)


async def get_db_async_session() -> AsyncIterator[AsyncSession]:
    async with sessionmanager.session() as session:
        yield session
