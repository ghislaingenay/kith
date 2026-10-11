"""Operator Credit Adjustments (ADR-0017): a top-up, or a negative
Adjustment that takes back a mistaken one. The command that runs it is
`scripts/adjust_credits.py` (`make adjust-credits`)."""

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import async_sessionmaker

from credits.config import CreditSettings
from credits.exceptions import BlankAdjustmentNoteError, InvalidCreditAmountError
from credits.repository import CreditsRepository
from credits.schemas import CreditBalance
from credits.service import TOKENS_PER_CREDIT, CreditsService
from tenants.exceptions import TenantNotFound
from tenants.repository import TenantsRepository


@dataclass(frozen=True)
class CreditAdjustmentResult:
    tenant_id: uuid.UUID
    tenant_name: str
    credits: int
    tokens: int
    balance: CreditBalance


async def adjust_credits(
    session_factory: async_sessionmaker,
    settings: CreditSettings,
    *,
    tenant_id: uuid.UUID,
    credits: int,
    note: str,
) -> CreditAdjustmentResult:
    """Writes one Credit Adjustment row of `credits` x 1,000 tokens to an
    undeleted Tenant and returns its new balance. A refusal writes nothing."""
    # bool is an int subclass; True must not pass as 1 Credit.
    if not isinstance(credits, int) or isinstance(credits, bool) or credits == 0:
        raise InvalidCreditAmountError(
            f"Credits must be a non-zero whole number, got {credits!r}."
        )
    if not note.strip():
        raise BlankAdjustmentNoteError("A Credit Adjustment needs a note saying why.")

    tokens = credits * TOKENS_PER_CREDIT
    async with session_factory() as session:
        tenant_name = await TenantsRepository(session).get_undeleted_tenant_name(
            tenant_id
        )
        if tenant_name is None:
            raise TenantNotFound(str(tenant_id))
        repository = CreditsRepository(session)
        await repository.add_adjustment(
            tenant_id=tenant_id, tokens=tokens, note=note.strip()
        )
        await session.commit()
        balance = await CreditsService(repository, settings).get_balance(tenant_id)
    return CreditAdjustmentResult(
        tenant_id=tenant_id,
        tenant_name=tenant_name,
        credits=credits,
        tokens=tokens,
        balance=balance,
    )
