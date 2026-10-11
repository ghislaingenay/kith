"""Credits domain service: the Credit Balance and the starting grant
(ADR-0017)."""

import uuid

from credits.config import CreditSettings
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

    async def grant_starting_credits(self, tenant_id: uuid.UUID) -> None:
        """Writes the grant into the caller's open transaction; the caller
        commits it together with the new Tenant."""
        await self.repository.add_adjustment(
            tenant_id=tenant_id,
            tokens=self.settings.starting_grant_credits * TOKENS_PER_CREDIT,
            note=_STARTING_GRANT_NOTE,
        )
