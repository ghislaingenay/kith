"""Real-Postgres tests for the rules the database itself enforces on the
Credit Ledger (ADR-0017)."""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from credits.models import CreditLedgerEntry, CreditLedgerKind
from tests.documents.conftest import make_tenant


@pytest.mark.parametrize("note", [None, "", "   "])
async def test_the_database_refuses_an_adjustment_without_a_note(
    db_session: AsyncSession, note: str | None
) -> None:
    tenant_id = await make_tenant(db_session)
    db_session.add(
        CreditLedgerEntry(
            tenant_id=tenant_id,
            kind=CreditLedgerKind.ADJUSTMENT,
            tokens=1_000,
            note=note,
        )
    )

    with pytest.raises(IntegrityError, match="ck_credit_ledger_adjustment_note"):
        await db_session.commit()


async def test_an_ask_charge_needs_no_note(db_session: AsyncSession) -> None:
    tenant_id = await make_tenant(db_session)
    db_session.add(
        CreditLedgerEntry(
            tenant_id=tenant_id, kind=CreditLedgerKind.ASK_CHARGE, tokens=-3_200
        )
    )

    await db_session.commit()
