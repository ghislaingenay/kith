"""FastAPI dependency wiring for the users domain."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.container import container
from core.database import get_session
from core.storage.dependencies import get_storage_provider
from core.storage.provider import StorageProvider
from users.repository import ProfileRepository, UserRepository
from users.service import ProfileService


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


def get_profile_service(
    profile_repository: Annotated[ProfileRepository, Depends(get_profile_repository)],
    storage: Annotated[StorageProvider, Depends(get_storage_provider)],
) -> ProfileService:
    return ProfileService(profile_repository, storage)
