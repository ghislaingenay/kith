"""Credits domain service: the Credit Balance and the starting grant
(ADR-0017)."""

import uuid

from credits.config import CreditSettings
from credits.exceptions import CreditBalanceExhaustedError
from credits.repository import CreditsRepository
from credits.schemas import CreditBalance

TOKENS_PER_CREDIT = 1_000
_STARTING_GRANT_NOTE = "Starting grant"


class CreditsService:
    def __init__(self, repository: CreditsRepository, settings: CreditSettings) -> None:
        self.repository = repository
        self.settings = settings

    async def get_balance(self, tenant_id: uuid.UUID) -> CreditBalance:
        tokens = await self.repository.sum_tokens(tenant_id)
        return CreditBalance(
            credits=tokens // TOKENS_PER_CREDIT,
            tokens=tokens,
            is_low=tokens < self.settings.low_threshold_credits * TOKENS_PER_CREDIT,
            is_exhausted=tokens <= 0,
        )

    async def require_credits_left(self, tenant_id: uuid.UUID) -> None:
        """An Ask may start only while the balance is above 0 (ADR-0017)."""
        if await self.repository.sum_tokens(tenant_id) <= 0:
            raise CreditBalanceExhaustedError(
                "The Credit Balance is used up. Ask an Admin to get more Credits."
            )

    async def charge_ask(
        self,
        *,
        tenant_id: uuid.UUID,
        ask_id: uuid.UUID,
        user_id: uuid.UUID,
        tokens: int,
    ) -> int:
        """Writes the Ask Charge into the caller's open transaction and returns
        the Credits charged, rounded up. Nothing spent writes no row."""
        if tokens == 0:
            return 0
        await self.repository.add_ask_charge(
            tenant_id=tenant_id, ask_id=ask_id, user_id=user_id, tokens=tokens
        )
        return -(-tokens // TOKENS_PER_CREDIT)

    async def grant_starting_credits(self, tenant_id: uuid.UUID) -> None:
        """Writes the grant into the caller's open transaction; the caller
        commits it together with the new Tenant."""
        await self.repository.add_adjustment(
            tenant_id=tenant_id,
            tokens=self.settings.starting_grant_credits * TOKENS_PER_CREDIT,
            note=_STARTING_GRANT_NOTE,
        )
