import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

from app.conf.config import get_settings, get_system_settings
from app.logger.logger_config import logger
from app.routes.call import router as call_router
from app.routes.mistakes import router as mistakes_router
from app.routes.sessions import router as sessions_router
from app.utils.middleware import catch_value_errors, jwt_auth
from app.utils.rabbitmq import RpcClient


@asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logger.info("Application starting up...")

    app.state.redis = aioredis.from_url(settings.redis_url)
    app.state.broker = RpcClient(settings.rabbitmq_url)
    await app.state.broker.connect()
    logger.info("redis and broker initialized")

    try:
        yield
    finally:
        await app.state.broker.close()
        await app.state.redis.aclose()
        logger.info("Application shutdown complete.")


def get_application() -> FastAPI:
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    system = get_system_settings()
    logger.info(f"Starting FastAPI application in {system.env.upper()} mode")

    if system.env == "prod":
        application = FastAPI(
            lifespan=app_lifespan,
            default_response_class=ORJSONResponse,
            docs_url=None,
        )
    else:
        application = FastAPI(
            lifespan=app_lifespan,
            default_response_class=ORJSONResponse,
        )

    application.middleware("http")(jwt_auth)
    application.middleware("http")(catch_value_errors)

    application.include_router(sessions_router)
    application.include_router(mistakes_router)
    application.include_router(call_router)

    @application.get("/health")
    async def health_check() -> dict[str, str]:
        """Liveness probe."""
        return {"status": "ok"}

    return application
