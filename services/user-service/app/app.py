import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

from app.conf.config import get_system_settings
from app.logger.logger_config import logger
from app.routes.users import router as users_router
from app.utils.middleware import catch_value_errors, jwt_auth


@asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Application starting up...")
    app.state.http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(10.0), limits=httpx.Limits(max_connections=50)
    )
    logger.info("httpx.AsyncClient initialized")
    try:
        yield
    finally:
        await app.state.http_client.aclose()
        logger.info("httpx.AsyncClient closed. Application shutdown complete.")


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
        logger.info("Documentation disabled (production mode)")
    else:
        application = FastAPI(
            lifespan=app_lifespan,
            default_response_class=ORJSONResponse,
        )
        logger.info("Documentation enabled (non-production mode)")

    # jwt_auth runs first (inner); catch_value_errors is added last so it wraps all.
    application.middleware("http")(jwt_auth)
    application.middleware("http")(catch_value_errors)

    application.include_router(users_router)

    @application.get("/health")
    async def health_check() -> dict[str, str]:
        """Liveness probe."""
        return {"status": "ok"}

    return application
