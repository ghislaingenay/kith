from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from tenants.exceptions import (
    InvalidLogoUploadError,
    TenantAlreadyExistsError,
    TenantNotFound,
    UnknownRoleOrActionError,
)


def register_tenant_exception_handlers(app: FastAPI):
    """Register exception handlers for tenant-related exceptions."""
    app.add_exception_handler(
        TenantNotFound, _handle_tenant_not_found_exception_handler
    )
    app.add_exception_handler(
        TenantAlreadyExistsError, _handle_tenant_already_exists_exception_handler
    )
    app.add_exception_handler(
        InvalidLogoUploadError, _handle_invalid_logo_upload_exception_handler
    )
    app.add_exception_handler(
        UnknownRoleOrActionError, _handle_unknown_role_or_action_exception_handler
    )


async def _handle_tenant_not_found_exception_handler(_: Request, exc: TenantNotFound):
    return JSONResponse(
        status_code=404,
        content={
            "error": "Tenant not found",
            "message": str(exc),
        },
    )


async def _handle_tenant_already_exists_exception_handler(
    _: Request, exc: TenantAlreadyExistsError
):
    return JSONResponse(
        status_code=400,
        content={
            "error": "Tenant already exists",
            "message": str(exc),
        },
    )


async def _handle_invalid_logo_upload_exception_handler(
    _: Request, exc: InvalidLogoUploadError
):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Invalid logo upload",
            "message": str(exc),
            "detail": str(exc),
        },
    )


async def _handle_unknown_role_or_action_exception_handler(
    _: Request, __: UnknownRoleOrActionError
):
    # A server-side bug or bad data; the offending values stay out of the
    # response body (coding-standards §11) and are available on the exception
    # for logging.
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Unknown role or action",
            "message": "The permission check received an unknown role or action.",
        },
    )
