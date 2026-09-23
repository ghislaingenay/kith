from core.logging import setup_logger
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from users.exceptions import InvalidAvatarUploadError, ProfileNotFound

logger = setup_logger(__name__)


def register_user_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers for user-related exceptions."""
    app.add_exception_handler(
        InvalidAvatarUploadError, _handle_invalid_avatar_upload_exception_handler
    )
    app.add_exception_handler(
        ProfileNotFound, _handle_profile_not_found_exception_handler
    )


async def _handle_invalid_avatar_upload_exception_handler(
    _: Request, exc: InvalidAvatarUploadError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "error": "Invalid avatar upload",
            "message": str(exc),
        },
    )


async def _handle_profile_not_found_exception_handler(
    _: Request, exc: ProfileNotFound
) -> JSONResponse:
    # A server-side bug or bad data; the offending user_id stays out of the
    # response body (coding-standards §11) but goes to the logs.
    logger.error(str(exc))
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Profile not found",
            "message": "This account is missing its Profile.",
        },
    )
