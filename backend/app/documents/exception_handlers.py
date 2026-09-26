import math
from collections.abc import Awaitable, Callable
from typing import cast

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from documents.exceptions import (
    DocumentNotFoundError,
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
    app.add_exception_handler(
        UploadRateExceededError,
        _problem_handler(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many uploads",
            headers=lambda exc: {
                "Retry-After": str(
                    math.ceil(
                        cast(UploadRateExceededError, exc).retry_after.total_seconds()
                    )
                )
            },
        ),
    )
    app.add_exception_handler(
        UploadObjectMissingError,
        _problem_handler(status.HTTP_409_CONFLICT, "Upload not received"),
    )
    app.add_exception_handler(
        UploadNotFoundError,
        _problem_handler(status.HTTP_404_NOT_FOUND, "Upload not found"),
    )
    app.add_exception_handler(
        DocumentNotFoundError,
        _problem_handler(status.HTTP_404_NOT_FOUND, "Document not found"),
    )


def _problem_handler(
    status_code: int,
    error: str,
    headers: Callable[[Exception], dict[str, str]] | None = None,
) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
    async def handler(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content={"error": error, "message": str(exc)},
            headers=headers(exc) if headers else None,
        )

    return handler
