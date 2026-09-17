"""Auth dependencies used by routers."""

from typing import Annotated

from fastapi import Depends, Header

from auth.config import MagicLinkSettings
from auth.exceptions import AuthenticationError
from auth.schemas import AuthenticatedUser, TenantContext
from auth.service import MagicLinkService
from core.cache.provider import CacheProvider
from core.container import container
from core.mail.dependencies import get_mailer
from core.mail.provider import Mailer
from core.ratelimit.counter_limiter import CounterLimiter


async def get_current_user() -> AuthenticatedUser:
    raise AuthenticationError("unauthorized")


async def get_current_tenant(
    x_tenant_id: str | None = Header(default=None),
) -> TenantContext:
    if not x_tenant_id:
        raise AuthenticationError("missing tenant context")
    raise AuthenticationError("unauthorized")


def get_cache_provider() -> CacheProvider:
    return container.cache_provider()


def get_magic_link_service(
    cache: Annotated[CacheProvider, Depends(get_cache_provider)],
    mailer: Annotated[Mailer, Depends(get_mailer)],
) -> MagicLinkService:
    # CounterLimiter is constructed directly (not via
    # core.ratelimit.dependencies) because that module imports
    # get_current_tenant/get_current_user from this one — importing it back
    # here would be circular. See the same note in tenants/router.py.
    #
    # `MagicLinkSettings` is instantiated here rather than module-level so
    # importing this module (done by unrelated domains for get_current_user)
    # doesn't require `MAGIC_LINK_VERIFY_URL` to be set.
    settings = MagicLinkSettings()
    return MagicLinkService(
        cache=cache,
        mailer=mailer,
        limiter=CounterLimiter(cache),
        verify_url=settings.verify_url,
    )
