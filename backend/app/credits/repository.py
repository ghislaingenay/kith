"""Persistence access for the credits domain."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from credits.models import CreditLedgerEntry, CreditLedgerKind


class CreditsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def sum_tokens(self, tenant_id: uuid.UUID) -> int:
        total = await self.session.scalar(
            select(func.coalesce(func.sum(CreditLedgerEntry.tokens), 0)).where(
                CreditLedgerEntry.tenant_id == tenant_id
            )
        )
        return int(total)

    async def add_adjustment(
        self, *, tenant_id: uuid.UUID, tokens: int, note: str
    ) -> None:
        """Adds the row to the caller's transaction without committing, so it
        lands or fails together with whatever the caller is writing."""
        self.session.add(
            CreditLedgerEntry(
                tenant_id=tenant_id,
                kind=CreditLedgerKind.ADJUSTMENT,
                tokens=tokens,
                note=note,
            )
        )
        await self.session.flush()

    async def add_ask_charge(
        self,
        *,
        tenant_id: uuid.UUID,
        ask_id: uuid.UUID,
        user_id: uuid.UUID,
        tokens: int,
    ) -> None:
        """`tokens` is what the Ask spent, written as a negative row. Flushes
        without committing, like `add_adjustment`."""
        self.session.add(
            CreditLedgerEntry(
                tenant_id=tenant_id,
                kind=CreditLedgerKind.ASK_CHARGE,
                tokens=-tokens,
                ask_id=ask_id,
                user_id=user_id,
            )
        )
        await self.session.flush()
