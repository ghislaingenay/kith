"""HTTP layer for the tenants domain."""

from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile, status
from pydantic import BaseModel

from auth.dependencies import get_current_tenant, get_current_user
from auth.schemas import AuthenticatedUser, TenantContext
from core.ratelimit.dependencies import RateLimitDependency
from core.storage.dependencies import get_storage_provider
from core.storage.exceptions import StorageObjectNotFoundError
from core.storage.provider import StorageProvider
from tenants.config import (
    LOGO_UPLOAD_RATE_LIMIT_PER_HOUR,
    LOGO_UPLOAD_RATE_LIMIT_PER_MINUTE,
    READ_RATE_LIMIT_PER_HOUR,
    READ_RATE_LIMIT_PER_MINUTE,
)
from tenants.dependencies import get_tenants_service, require_permission
from tenants.logo import (
    LOGO_KEY_EXTENSIONS,
    logo_key,
    validate_logo_upload,
)
from tenants.permissions import Action
from tenants.schemas import (
    CreateTenantRequest,
    TenantLogoResponse,
    TenantMembershipSummary,
)
from tenants.service import TenantsService

router = APIRouter(prefix="/tenants", tags=["tenants"])

# Per tenant+user rate-limit budgets for the tenants routes. Defined here
# rather than in `dependencies.py` because `auth.dependencies` imports that
# module, and `core.ratelimit.dependencies` imports `auth.dependencies` —
# routing the rate-limit deps through the router (a leaf module) avoids the
# import cycle. `tenants_logo_upload_rate_limit` is tighter since it does
# storage I/O per request.
tenants_read_rate_limit = RateLimitDependency(
    per_minute=READ_RATE_LIMIT_PER_MINUTE, per_hour=READ_RATE_LIMIT_PER_HOUR
)
tenants_logo_upload_rate_limit = RateLimitDependency(
    per_minute=LOGO_UPLOAD_RATE_LIMIT_PER_MINUTE,
    per_hour=LOGO_UPLOAD_RATE_LIMIT_PER_HOUR,
)
tenants_logo_upload_permission = require_permission(Action.SETTINGS)


@router.get("", response_model=list[TenantMembershipSummary])
async def list_my_tenants(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    service: Annotated[TenantsService, Depends(get_tenants_service)],
) -> list[TenantMembershipSummary]:
    """No tenant context required — this exists specifically so a caller
    can discover which tenants they belong to before picking one via
    X-Tenant-ID (the /me endpoint requires that header up front)."""
    return await service.list_my_memberships(user.id)


@router.post(
    "", response_model=TenantMembershipSummary, status_code=status.HTTP_201_CREATED
)
async def create_tenant(
    data: CreateTenantRequest,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    service: Annotated[TenantsService, Depends(get_tenants_service)],
) -> TenantMembershipSummary:
    """Lets an already-authenticated identity create a tenant and become
    its owner. This app enforces one active tenant per user: if the caller
    already has an active membership, this raises TenantAlreadyExistsError
    (mapped to 400) instead of creating another one. Decoupled from
    identity provider entirely."""
    return await service.create_tenant(user_id=user.id, name=data.name)


@router.post(
    "/logo",
    response_model=TenantLogoResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_tenant_logo(
    file: UploadFile,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    tenant: Annotated[TenantContext, Depends(get_current_tenant)],
    _permission: Annotated[None, Depends(tenants_logo_upload_permission)],
    _rate_limit: Annotated[None, Depends(tenants_logo_upload_rate_limit)],
    storage: Annotated[StorageProvider, Depends(get_storage_provider)],
) -> TenantLogoResponse:
    """Store the tenant's logo at a single fixed key (`tenant/<id>/logo/logo.<ext>`)
    and return a stable public URL — never presigned, since the URL is
    written straight into a template's `document` JSONB. Each upload
    overwrites the previous logo; other-extension variants are deleted so a
    tenant only ever has one logo object."""
    data = await file.read()
    ext = validate_logo_upload(file.content_type, len(data))
    url = await storage.upload(logo_key(tenant.tenant_id, ext), data, public=True)
    for other_ext in LOGO_KEY_EXTENSIONS:
        if other_ext != ext:
            await storage.delete(logo_key(tenant.tenant_id, other_ext))
    return TenantLogoResponse(url=url)


@router.get("/logo", response_model=TenantLogoResponse)
async def get_tenant_logo(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    tenant: Annotated[TenantContext, Depends(get_current_tenant)],
    _rate_limit: Annotated[None, Depends(tenants_read_rate_limit)],
    storage: Annotated[StorageProvider, Depends(get_storage_provider)],
) -> TenantLogoResponse:
    """Returns the current logo's public URL, or `null` if none has been
    uploaded. The editor calls this once to pre-fill new Logo blocks."""
    for ext in LOGO_KEY_EXTENSIONS:
        key = logo_key(tenant.tenant_id, ext)
        try:
            await storage.head(key)
        except StorageObjectNotFoundError:
            continue
        return TenantLogoResponse(url=storage.public_url(key))
    return TenantLogoResponse(url=None)

