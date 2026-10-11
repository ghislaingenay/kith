"""Persistence access for the asks domain."""

from sqlalchemy.ext.asyncio import AsyncSession

from asks.models import Ask


class AsksRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, ask: Ask) -> None:
        """Flushes without committing; the caller calls `commit`."""
        self.session.add(ask)
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()
