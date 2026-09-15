"""FastAPI dependency wiring for the users domain."""

from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.container import container
from core.database import get_session
from users.repository import ProfileRepository, UserRepository


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async for session in get_session(container.db_session_factory()):
        yield session


def get_user_repository(
    session: AsyncSession = Depends(get_db_session),
) -> UserRepository:
    return UserRepository(session)


def get_profile_repository(
    session: AsyncSession = Depends(get_db_session),
) -> ProfileRepository:
    return ProfileRepository(session)
