import math
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from documents.exceptions import (
    DuplicateDocumentError,
    InvalidUploadRequestError,
    LimitReachedError,
    RefusedUploadError,
    TooManyPendingUploadsError,
    UploadNotFoundError,
    UploadObjectMissingError,
    UploadRateExceededError,
)


def register_document_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers for document-related exceptions."""
    app.add_exception_handler(
        InvalidUploadRequestError,
        _problem_handler(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid upload"),
    )
    app.add_exception_handler(
        RefusedUploadError,
        _problem_handler(status.HTTP_422_UNPROCESSABLE_CONTENT, "Upload refused"),
    )
    app.add_exception_handler(
        DuplicateDocumentError,
        _problem_handler(status.HTTP_409_CONFLICT, "Duplicate document"),
    )
    app.add_exception_handler(
        LimitReachedError,
        _problem_handler(status.HTTP_409_CONFLICT, "Limit reached"),
    )
    app.add_exception_handler(
        TooManyPendingUploadsError,
        _problem_handler(status.HTTP_429_TOO_MANY_REQUESTS, "Too many uploads"),
    )
    app.add_exception_handler(UploadRateExceededError, _rate_exceeded_handler)
    app.add_exception_handler(
        UploadObjectMissingError,
        _problem_handler(status.HTTP_409_CONFLICT, "Upload not received"),
    )
    app.add_exception_handler(
        UploadNotFoundError,
        _problem_handler(status.HTTP_404_NOT_FOUND, "Upload not found"),
    )


async def _rate_exceeded_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, UploadRateExceededError)
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"error": "Too many uploads", "message": str(exc)},
        headers={"Retry-After": str(math.ceil(exc.retry_after.total_seconds()))},
    )


def _problem_handler(
    status_code: int, error: str
) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
    async def handler(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content={"error": error, "message": str(exc)},
        )

    return handler
