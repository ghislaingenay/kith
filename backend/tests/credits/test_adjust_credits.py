"""Tests for `make adjust-credits` (ADR-0017): the operator gives a Tenant
Credits or takes back a mistaken top-up. `adjust_credits` is called as a
function against real Postgres, and the balance is read back from
`GET /api/v1/credit-balance`."""

import os
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from core.database import DatabaseSettings, create_engine, create_session_factory
from credits.adjustment import CreditAdjustmentResult, adjust_credits
from credits.config import CreditSettings
from credits.exceptions import BlankAdjustmentNoteError, InvalidCreditAmountError
from credits.models import CreditLedgerEntry, CreditLedgerKind
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tenants.exceptions import TenantNotFound
from tenants.models import Tenant

from tests.documents.conftest import Caller, make_tenant

BALANCE_URL = "/api/v1/credit-balance"
_TOP_UP_NOTE = "Pilot top-up"


@pytest.fixture
async def session_factory(_database_url: str) -> AsyncIterator[async_sessionmaker]:
    engine = create_engine(DatabaseSettings(database_url=_database_url))
    yield create_session_factory(engine)
    await engine.dispose()


async def _adjust(
    session_factory: async_sessionmaker,
    tenant_id: uuid.UUID,
    credits: int,
    note: str = _TOP_UP_NOTE,
) -> CreditAdjustmentResult:
    return await adjust_credits(
        session_factory,
        CreditSettings(),
        tenant_id=tenant_id,
        credits=credits,
        note=note,
    )


async def _ledger_rows(
    db_session: AsyncSession, tenant_id: uuid.UUID
) -> list[CreditLedgerEntry]:
    result = await db_session.scalars(
        select(CreditLedgerEntry)
        .where(CreditLedgerEntry.tenant_id == tenant_id)
        .order_by(CreditLedgerEntry.created_at)
    )
    return list(result)


async def _ledger_row_count(db_session: AsyncSession) -> int:
    return await db_session.scalar(select(func.count()).select_from(CreditLedgerEntry))


async def test_a_positive_adjustment_raises_the_balance_by_that_many_credits(
    client: AsyncClient, session_factory: async_sessionmaker, caller: Caller
) -> None:
    await _adjust(session_factory, caller.tenant_id, 50)

    body = (await client.get(BALANCE_URL)).json()

    assert body["credits"] == 50
    assert body["tokens"] == 50_000


async def test_a_negative_adjustment_lowers_the_balance(
    client: AsyncClient, session_factory: async_sessionmaker, caller: Caller
) -> None:
    await _adjust(session_factory, caller.tenant_id, 500)
    await _adjust(session_factory, caller.tenant_id, -450, "Undo mistaken top-up")

    body = (await client.get(BALANCE_URL)).json()

    assert body["credits"] == 50


async def test_the_returned_balance_matches_the_balance_endpoint(
    client: AsyncClient, session_factory: async_sessionmaker, caller: Caller
) -> None:
    await _adjust(session_factory, caller.tenant_id, 30)

    adjustment = await _adjust(session_factory, caller.tenant_id, -45)

    assert adjustment.balance.model_dump() == (await client.get(BALANCE_URL)).json()
    assert adjustment.balance.credits == -15
    assert adjustment.tokens == -45_000


async def test_the_result_names_the_tenant(
    session_factory: async_sessionmaker, caller: Caller
) -> None:
    adjustment = await _adjust(session_factory, caller.tenant_id, 10)

    assert adjustment.tenant_id == caller.tenant_id
    assert adjustment.tenant_name == "Acme"
    assert adjustment.credits == 10


async def test_each_adjustment_is_one_new_row_with_its_note(
    db_session: AsyncSession, session_factory: async_sessionmaker, caller: Caller
) -> None:
    await _adjust(session_factory, caller.tenant_id, 100, "First top-up")
    first_row = (await _ledger_rows(db_session, caller.tenant_id))[0]
    first_row_before = (first_row.id, first_row.tokens, first_row.note)

    await _adjust(session_factory, caller.tenant_id, -20, "Correct first top-up")

    db_session.expire_all()
    rows = await _ledger_rows(db_session, caller.tenant_id)
    assert [(row.kind, row.tokens, row.note) for row in rows] == [
        (CreditLedgerKind.ADJUSTMENT, 100_000, "First top-up"),
        (CreditLedgerKind.ADJUSTMENT, -20_000, "Correct first top-up"),
    ]
    assert (rows[0].id, rows[0].tokens, rows[0].note) == first_row_before


@pytest.mark.parametrize("note", ["", "   ", "\n\t"])
async def test_a_blank_note_is_refused_and_nothing_is_written(
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    caller: Caller,
    note: str,
) -> None:
    with pytest.raises(BlankAdjustmentNoteError):
        await _adjust(session_factory, caller.tenant_id, 10, note)

    assert await _ledger_row_count(db_session) == 0


@pytest.mark.parametrize("credits", [0, 1.5, True])
async def test_a_zero_or_non_integer_amount_is_refused_and_nothing_is_written(
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    caller: Caller,
    credits: object,
) -> None:
    with pytest.raises(InvalidCreditAmountError):
        await _adjust(session_factory, caller.tenant_id, credits)  # type: ignore[arg-type]

    assert await _ledger_row_count(db_session) == 0


async def test_an_unknown_tenant_is_refused_and_nothing_is_written(
    db_session: AsyncSession, session_factory: async_sessionmaker
) -> None:
    with pytest.raises(TenantNotFound):
        await _adjust(session_factory, uuid.uuid4(), 10)

    assert await _ledger_row_count(db_session) == 0


async def test_a_deleted_tenant_is_refused_and_nothing_is_written(
    db_session: AsyncSession, session_factory: async_sessionmaker
) -> None:
    tenant_id = await make_tenant(db_session)
    await db_session.execute(
        update(Tenant).where(Tenant.id == tenant_id).values(deleted_at=func.now())
    )
    await db_session.commit()

    with pytest.raises(TenantNotFound):
        await _adjust(session_factory, tenant_id, 10)

    assert await _ledger_row_count(db_session) == 0


def test_the_script_alone_knows_every_table_the_ledger_points_to() -> None:
    # A fresh interpreter: the test process has already imported the whole
    # app, which registers every table and would hide a missing one.
    check = (
        "import scripts.adjust_credits\n"
        "from credits.models import CreditLedgerEntry\n"
        "for fk in CreditLedgerEntry.__table__.foreign_keys:\n"
        "    fk.column\n"
    )
    app_dir = Path(__file__).resolve().parents[2] / "app"

    result = subprocess.run(
        [sys.executable, "-c", check],
        env={**os.environ, "PYTHONPATH": str(app_dir)},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
