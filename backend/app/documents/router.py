"""HTTP layer for uploading PDFs."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from auth.dependencies import get_current_tenant, get_current_user
from auth.schemas import AuthenticatedUser, TenantContext
from core.security.dependencies import require_allowed_origin
from documents.dependencies import get_library_service, get_upload_service
from documents.library_service import DocumentLibraryService
from documents.schemas import (
    DocumentResponse,
    InitUploadRequest,
    InitUploadResponse,
    LibraryDocumentResponse,
    LibrarySummaryResponse,
)
from documents.service import DocumentUploadService
from tenants.dependencies import require_permission
from tenants.permissions import Action

router = APIRouter(
    prefix="/uploads",
    tags=["uploads"],
    dependencies=[
        Depends(require_allowed_origin),
        Depends(require_permission(Action.UPLOAD)),
    ],
)


@router.post(
    "/init", response_model=InitUploadResponse, status_code=status.HTTP_201_CREATED
)
async def start_upload(
    data: InitUploadRequest,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    tenant: Annotated[TenantContext, Depends(get_current_tenant)],
    service: Annotated[DocumentUploadService, Depends(get_upload_service)],
) -> InitUploadResponse:
    """Creates a pending Upload and returns the presigned PUT the browser
    sends the file to."""
    return await service.init_upload(
        tenant_id=tenant.tenant_id, user_id=user.id, request=data
    )


@router.post("/{upload_id}/finalize", response_model=DocumentResponse)
async def finalize_upload(
    upload_id: uuid.UUID,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    tenant: Annotated[TenantContext, Depends(get_current_tenant)],
    service: Annotated[DocumentUploadService, Depends(get_upload_service)],
) -> DocumentResponse:
    """Validates the uploaded file and turns it into a Document. Calling it
    again for a completed Upload returns the same Document."""
    return await service.finalize_upload(
        tenant_id=tenant.tenant_id, user_id=user.id, upload_id=upload_id
    )


# Reading the library needs only what searching does, so a Viewer may.
library_router = APIRouter(
    prefix="/documents",
    tags=["documents"],
    dependencies=[Depends(require_permission(Action.SEARCH))],
)


@library_router.get("", response_model=list[LibraryDocumentResponse])
async def list_documents(
    tenant: Annotated[TenantContext, Depends(get_current_tenant)],
    service: Annotated[DocumentLibraryService, Depends(get_library_service)],
) -> list[LibraryDocumentResponse]:
    """The Tenant's non-deleted Documents, newest first."""
    return await service.list_documents(tenant_id=tenant.tenant_id)


@library_router.get("/summary", response_model=LibrarySummaryResponse)
async def summarize_documents(
    tenant: Annotated[TenantContext, Depends(get_current_tenant)],
    service: Annotated[DocumentLibraryService, Depends(get_library_service)],
) -> LibrarySummaryResponse:
    """Counts of in-progress and failed Documents, for the Uploads banner."""
    return await service.summarize(tenant_id=tenant.tenant_id)
