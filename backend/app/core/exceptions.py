"""Top-level exception-handler registration.

Domain code (services, repositories) raises domain-specific exceptions and
never `HTTPException` (see `context/coding-standards.md` §11). Each domain
owns the HTTP mapping for its own exceptions (e.g.
`upload.exception_handlers`); this module only handles exceptions from
shared, cross-domain infrastructure and aggregates every domain's
registration into one call for `main.py`.
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError, TimeoutError

from auth.exceptions import AuthenticationError, MagicLinkTokenInvalidError
from core.logging import setup_logger
from core.mail.exceptions import MailError
from core.ratelimit.exception_handlers import register_ratelimit_exception_handlers
from core.security.exception_handlers import register_security_exception_handlers
from core.storage.exceptions import StorageError
from documents.exception_handlers import register_document_exception_handlers
from tenants.exception_handlers import register_tenant_exception_handlers
from users.exception_handlers import register_user_exception_handlers

logger = setup_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    register_tenant_exception_handlers(app)
    register_document_exception_handlers(app)
    register_user_exception_handlers(app)
    register_ratelimit_exception_handlers(app)
    register_security_exception_handlers(app)
    app.add_exception_handler(AuthenticationError, _handle_authentication_error)  # type: ignore[arg-type]
    app.add_exception_handler(
        MagicLinkTokenInvalidError, _handle_magic_link_token_invalid
    )  # type: ignore[arg-type]
    # See note in upload/exception_handlers.py on this ignore.
    app.add_exception_handler(StorageError, _handle_storage_error)  # type: ignore[arg-type]
    app.add_exception_handler(MailError, _handle_mail_error)  # type: ignore[arg-type]
    app.add_exception_handler(TimeoutError, _handle_db_timeout_error)  # type: ignore[arg-type]
    # Connection/auth failures (e.g. asyncpg's InvalidPasswordError).
    app.add_exception_handler(OperationalError, _handle_db_operational_error)  # type: ignore[arg-type]


async def _handle_authentication_error(
    _: Request, exc: AuthenticationError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"error": "unauthorized", "message": str(exc)},
    )


async def _handle_magic_link_token_invalid(
    _: Request, __: MagicLinkTokenInvalidError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "invalid_magic_link",
            "message": "This sign-in link is invalid, expired, or already used.",
        },
    )


async def _handle_storage_error(_: Request, __: StorageError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "error": "storage_unavailable",
            "message": "Storage provider is temporarily unavailable",
        },
    )


async def _handle_mail_error(_: Request, __: MailError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "error": "mail_unavailable",
            "message": "Mail provider is temporarily unavailable",
        },
    )


async def _handle_db_timeout_error(_: Request, exc: Exception) -> JSONResponse:
    logger.error(str(exc))
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "error": "db_timeout",
            "message": "Database is temporarily unavailable",
        },
    )


async def _handle_db_operational_error(
    _: Request, exc: OperationalError
) -> JSONResponse:
    logger.error(f"Database operational issue: {exc}")
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "error": "db_unavailable",
            "message": "Database is temporarily unavailable",
        },
    )
