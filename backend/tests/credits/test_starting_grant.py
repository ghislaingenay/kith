"""HTTP tests for the starting grant: a Tenant created through onboarding
starts with STARTING_CREDIT_GRANT Credits (ADR-0017)."""

import uuid

from httpx import AsyncClient

from tenants.permissions import Role
from tests.documents.conftest import Caller

BALANCE_URL = "/api/v1/credit-balance"
CREATE_TENANT_URL = "/api/v1/tenants"


async def test_a_tenant_created_through_onboarding_starts_with_200_credits(
    client: AsyncClient, caller: Caller
) -> None:
    created = await client.post(CREATE_TENANT_URL, json={"name": "Globex"})
    assert created.status_code == 201
    caller.tenant_id = uuid.UUID(created.json()["tenant_id"])
    caller.role = Role.OWNER

    response = await client.get(BALANCE_URL)

    assert response.json() == {
        "credits": 200,
        "tokens": 200_000,
        "is_low": False,
        "is_exhausted": False,
    }
