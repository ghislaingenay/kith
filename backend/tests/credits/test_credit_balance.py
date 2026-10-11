"""HTTP tests for the Credit Balance (ADR-0017): the sum of a Tenant's
Credit Ledger, shown in whole Credits to the Roles that may Ask."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from credits.models import CreditLedgerEntry, CreditLedgerKind
from tenants.permissions import Role
from tests.documents.conftest import Caller, make_tenant

BALANCE_URL = "/api/v1/credit-balance"
# CREDIT_LOW_THRESHOLD's default, 20 Credits, in tokens.
_LOW_THRESHOLD_TOKENS = 20_000


async def test_a_tenant_with_no_ledger_rows_has_no_credits_and_is_exhausted(
    client: AsyncClient, caller: Caller
) -> None:
    response = await client.get(BALANCE_URL)

    assert response.status_code == 200
    assert response.json() == {
        "credits": 0,
        "tokens": 0,
        "is_low": True,
        "is_exhausted": True,
    }


async def _add_ledger_rows(
    db_session: AsyncSession, tenant_id: uuid.UUID, *tokens: int
) -> None:
    for amount in tokens:
        db_session.add(
            CreditLedgerEntry(
                tenant_id=tenant_id,
                kind=CreditLedgerKind.ADJUSTMENT,
                tokens=amount,
                note="Top-up",
            )
        )
    await db_session.commit()


async def test_the_balance_is_the_sum_of_the_tenants_ledger_rows(
    client: AsyncClient, db_session: AsyncSession, caller: Caller
) -> None:
    await _add_ledger_rows(db_session, caller.tenant_id, 200_000, -57_690)

    response = await client.get(BALANCE_URL)

    assert response.json() == {
        "credits": 142,
        "tokens": 142_310,
        "is_low": False,
        "is_exhausted": False,
    }


@pytest.mark.parametrize(
    ("tokens", "credits"),
    [(142_999, 142), (999, 0), (-2_500, -3)],
)
async def test_credits_are_the_tokens_rounded_down(
    client: AsyncClient,
    db_session: AsyncSession,
    caller: Caller,
    tokens: int,
    credits: int,
) -> None:
    await _add_ledger_rows(db_session, caller.tenant_id, tokens)

    body = (await client.get(BALANCE_URL)).json()

    assert body["credits"] == credits


async def test_a_negative_sum_reads_as_a_negative_exhausted_balance(
    client: AsyncClient, db_session: AsyncSession, caller: Caller
) -> None:
    await _add_ledger_rows(db_session, caller.tenant_id, 1_000, -4_000)

    body = (await client.get(BALANCE_URL)).json()

    assert body["credits"] == -3
    assert body["tokens"] == -3_000
    assert body["is_exhausted"] is True


async def test_the_balance_is_low_below_the_threshold_and_not_at_it(
    client: AsyncClient, db_session: AsyncSession, caller: Caller
) -> None:
    await _add_ledger_rows(db_session, caller.tenant_id, _LOW_THRESHOLD_TOKENS - 1)
    just_below = (await client.get(BALANCE_URL)).json()

    await _add_ledger_rows(db_session, caller.tenant_id, 1)
    at_threshold = (await client.get(BALANCE_URL)).json()

    assert just_below["is_low"] is True
    assert just_below["is_exhausted"] is False
    assert at_threshold["is_low"] is False


async def test_another_tenants_ledger_never_counts(
    client: AsyncClient, db_session: AsyncSession, caller: Caller
) -> None:
    other_tenant_id = await make_tenant(db_session)
    await _add_ledger_rows(db_session, other_tenant_id, 500_000)

    body = (await client.get(BALANCE_URL)).json()

    assert body["tokens"] == 0


@pytest.mark.parametrize("role", [Role.OWNER, Role.ADMIN, Role.MEMBER])
async def test_every_role_that_may_ask_sees_the_balance(
    client: AsyncClient, caller: Caller, role: Role
) -> None:
    caller.role = role

    response = await client.get(BALANCE_URL)

    assert response.status_code == 200


async def test_a_viewer_is_refused(client: AsyncClient, caller: Caller) -> None:
    caller.role = Role.VIEWER

    response = await client.get(BALANCE_URL)

    assert response.status_code == 403
