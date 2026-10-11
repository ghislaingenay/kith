"""Auth dependencies used by routers."""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from auth.config import SESSION_COOKIE_NAME, MagicLinkSettings
from auth.exceptions import AuthenticationError
from auth.schemas import AuthenticatedUser, TenantContext
from auth.service import MagicLinkService, MagicLinkVerificationService
from auth.session import SessionService
from core.cache.provider import CacheProvider
from core.container import container
from core.database import get_session
from core.mail.dependencies import get_mailer
from core.mail.provider import Mailer
from core.ratelimit.counter_limiter import CounterLimiter
from fastapi import Cookie, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession
from credits.config import CreditSettings
from credits.dependencies import get_credit_settings
from credits.repository import CreditsRepository
from credits.service import CreditsService
from tenants.permissions import Role
from tenants.repository import TenantsRepository
from tenants.service import TenantsService
from users.dependencies import get_user_repository
from users.repository import UserRepository


async def get_db_session() -> AsyncIterator[AsyncSession]:
    # Duplicated in every domain's dependencies.py rather than imported —
    # `tenants.dependencies` imports `get_current_tenant` from this module,
    # so importing `tenants.dependencies.get_tenant_repository` back here
    # would be circular. See the same note next to `CounterLimiter` below.
    async for session in get_session(container.db_session_factory()):
        yield session


def get_cache_provider() -> CacheProvider:
    return container.cache_provider()


def get_session_service(
    cache: Annotated[CacheProvider, Depends(get_cache_provider)],
) -> SessionService:
    return SessionService(cache)


async def get_current_user(
    session_service: Annotated[SessionService, Depends(get_session_service)],
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> AuthenticatedUser:
    if not session_cookie:
        raise AuthenticationError("missing session")

    user_id = await session_service.resolve_user_id(session_cookie)
    if user_id is None:
        raise AuthenticationError("invalid or expired session")

    user = await user_repository.get_by_user_id(str(user_id))
    if user is None or not user.is_active:
        raise AuthenticationError("invalid or expired session")

    return AuthenticatedUser(
        id=user.id,
        email=user.email,
        email_verified=user.email_verified,
        is_active=user.is_active,
    )


async def get_current_tenant(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: AsyncSession = Depends(get_db_session),
    x_tenant_id: str | None = Header(default=None),
) -> TenantContext:
    if not x_tenant_id:
        raise AuthenticationError("missing tenant context")
    try:
        tenant_id = uuid.UUID(x_tenant_id)
    except ValueError as exc:
        raise AuthenticationError("invalid tenant context") from exc

    # Constructed directly rather than via tenants.dependencies.get_tenant_repository
    # for the same circular-import reason noted on get_db_session above:
    # tenants.dependencies imports get_current_tenant from this module.
    membership = await TenantsRepository(session).get_active_membership(
        user_id=user.id, tenant_id=tenant_id
    )
    if membership is None:
        raise AuthenticationError("not a member of this tenant")

    return TenantContext(tenant_id=tenant_id, role=Role(membership.role))


def get_magic_link_service(
    cache: Annotated[CacheProvider, Depends(get_cache_provider)],
    mailer: Annotated[Mailer, Depends(get_mailer)],
) -> MagicLinkService:
    settings = MagicLinkSettings()
    return MagicLinkService(
        cache=cache,
        mailer=mailer,
        limiter=CounterLimiter(cache),
        verify_url=settings.verify_url,
    )


def get_magic_link_verification_service(
    cache: Annotated[CacheProvider, Depends(get_cache_provider)],
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    credit_settings: Annotated[CreditSettings, Depends(get_credit_settings)],
    session: AsyncSession = Depends(get_db_session),
) -> MagicLinkVerificationService:
    return MagicLinkVerificationService(
        cache=cache,
        user_repository=user_repository,
        session_service=session_service,
        tenants_service=TenantsService(
            TenantsRepository(session),
            CreditsService(CreditsRepository(session), credit_settings),
        ),
    )
