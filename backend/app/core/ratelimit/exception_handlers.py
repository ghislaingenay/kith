"""HTTP mapping for rate limit exceptions."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from core.ratelimit.exceptions import RateLimitExceededError, RateLimitUnavailableError


def register_ratelimit_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers for rate limit exceptions."""
    app.add_exception_handler(RateLimitExceededError, _handle_rate_limit_exceeded)
    app.add_exception_handler(RateLimitUnavailableError, _handle_rate_limit_unavailable)


async def _handle_rate_limit_exceeded(
    _: Request, exc: RateLimitExceededError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": "too many requests"},
        headers={
            "X-RateLimit-Limit": str(exc.limit),
            "X-RateLimit-Remaining": str(exc.remaining),
            "Retry-After": str(int(exc.retry_after.total_seconds())),
        },
    )


async def _handle_rate_limit_unavailable(
    _: Request, exc: RateLimitUnavailableError
) -> JSONResponse:
    """Only reached when a route opts into `fail_open=False` — the default
    (`fail_open=True`) swallows this in the dependency and allows the
    request through instead."""
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "rate limiting service temporarily unavailable"},
    )
