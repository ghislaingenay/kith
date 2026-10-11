"""FastAPI dependency wiring for the credits domain."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.container import container
from core.database import get_session
from credits.config import CreditSettings
from credits.repository import CreditsRepository
from credits.service import CreditsService


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async for session in get_session(container.db_session_factory()):
        yield session


def get_credit_settings() -> CreditSettings:
    return container.credit_settings()


def get_credits_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[CreditSettings, Depends(get_credit_settings)],
) -> CreditsService:
    return CreditsService(CreditsRepository(session), settings)
