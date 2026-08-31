from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import ResponseValidationError
from starlette.responses import JSONResponse, Response

from app.logger.logger_config import logger

CallNext = Callable[[Request], Awaitable[Response]]


async def catch_value_errors(request: Request, call_next: CallNext) -> Response:
    try:
        return await call_next(request)
    except ValueError as e:
        logger.warning(f"ValueError at {request.url.path}: {e}")
        return JSONResponse(status_code=422, content={"detail": str(e)})
    except ResponseValidationError as e:
        logger.error(f"Response validation error at {request.url.path}: {e.errors()}")
        return JSONResponse(
            status_code=422,
            content={
                "detail": jsonable_encoder(
                    e.errors(),
                    custom_encoder={
                        bytes: lambda b: b.decode("utf-8", errors="replace")
                    },
                )
            },
        )
    except Exception as e:
        logger.exception(f"Unexpected error in request {request.url.path}: {e}")
        return JSONResponse(
            status_code=500, content={"detail": "Internal Server Error"}
        )
