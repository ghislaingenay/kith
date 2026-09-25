from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from documents.exceptions import (
    DuplicateDocumentError,
    InvalidUploadRequestError,
    RefusedUploadError,
    UploadNotFoundError,
    UploadObjectMissingError,
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
        UploadObjectMissingError,
        _problem_handler(status.HTTP_409_CONFLICT, "Upload not received"),
    )
    app.add_exception_handler(
        UploadNotFoundError,
        _problem_handler(status.HTTP_404_NOT_FOUND, "Upload not found"),
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
