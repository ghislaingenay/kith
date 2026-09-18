"""HTTP mapping for cross-domain security exceptions."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from core.security.exceptions import OriginNotAllowedError


def register_security_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(OriginNotAllowedError, _handle_origin_not_allowed)


async def _handle_origin_not_allowed(
    _: Request, exc: OriginNotAllowedError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"error": "origin_not_allowed", "message": str(exc)},
    )
