"""HTTP layer for the credits domain."""

from typing import Annotated

from fastapi import APIRouter, Depends

from auth.dependencies import get_current_tenant
from auth.schemas import TenantContext
from credits.dependencies import get_credits_service
from credits.schemas import CreditBalance
from credits.service import CreditsService
from tenants.dependencies import require_permission
from tenants.permissions import Action

router = APIRouter(
    prefix="/credit-balance",
    tags=["credits"],
    dependencies=[Depends(require_permission(Action.ASK))],
)


@router.get(
    "",
    response_model=CreditBalance,
    summary="The caller's Tenant's Credit Balance",
    description="The sum of the Tenant's Credit Ledger, for Roles that may Ask.",
)
async def get_credit_balance(
    tenant: Annotated[TenantContext, Depends(get_current_tenant)],
    service: Annotated[CreditsService, Depends(get_credits_service)],
) -> CreditBalance:
    return await service.get_balance(tenant.tenant_id)
