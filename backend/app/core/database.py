"""Async SQLAlchemy engine/session setup and the shared declarative base."""

from collections.abc import AsyncIterator

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class DatabaseSettings(BaseSettings):
    """Env-driven database config."""

    model_config = SettingsConfigDict(case_sensitive=False)

    database_url: str = Field(validation_alias="DATABASE_URL")


class Base(DeclarativeBase):
    """Shared declarative base for all domain ORM models."""


def create_engine(settings: DatabaseSettings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url, pool_size=20, max_overflow=10, pool_timeout=30
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


async def get_db_session() -> AsyncIterator[AsyncSession]:
    from core.container import container  # local import avoids a circular import

    async for session in get_session(container.db_session_factory()):
        yield session
