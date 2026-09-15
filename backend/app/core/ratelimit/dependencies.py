"""FastAPI dependencies for rate limiting."""

import hashlib
from datetime import timedelta
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request

from auth.dependencies import get_current_tenant, get_current_user
from auth.schemas import AuthenticatedUser, TenantContext
from core.container import container
from core.ratelimit.exceptions import RateLimitExceededError, RateLimitUnavailableError
from core.ratelimit.limiter import Decision, MultiWindowLimiter


def get_rate_limiter() -> MultiWindowLimiter:
    """Provides the rate limiter instance from the container."""
    return container.rate_limiter()


async def _check_both(
    limiter: MultiWindowLimiter,
    tenant_id: UUID,
    user_id: UUID,
    per_minute: int,
    per_hour: int,
    fail_open: bool,
) -> None:
    """Shared check/raise logic for both dependency flavors below.

    Raises `RateLimitExceededError` (mapped to 429) when a window is over
    budget, or `RateLimitUnavailableError` (mapped to 503) when the backend
    is unreachable and `fail_open` is False. Both exceptions are handled by
    `register_ratelimit_exception_handlers` — this dependency never raises
    `HTTPException` directly, matching how `auth`/`tenants` dependencies
    raise domain exceptions instead of building HTTP responses inline.
    """
    try:
        minute_decision, hour_decision = await limiter.allow_both(
            tenant_id, user_id, per_minute, per_hour
        )
    except RateLimitUnavailableError:
        if not fail_open:
            raise
        return

    denied = [d for d in (minute_decision, hour_decision) if not d.allowed]
    if denied:
        binding: Decision = max(denied, key=lambda d: d.retry_after or timedelta(0))
        raise RateLimitExceededError(
            limit=binding.limit,
            remaining=binding.remaining,
            retry_after=binding.retry_after or timedelta(0),
        )


class RateLimitDependency:
    """Dependency for per-tenant/per-user rate limiting.

    Usage:
        @router.get("/expensive-operation")
        async def handler(
            _rate_limit: Annotated[None, Depends(RateLimitDependency(per_minute=5, per_hour=50))]
        ):
            ...
    """

    def __init__(self, per_minute: int, per_hour: int, fail_open: bool = True) -> None:
        """
        Args:
            per_minute: Maximum requests per minute.
            per_hour: Maximum requests per hour.
            fail_open: If True, allows requests when Redis is unavailable (default: True).
        """
        self.per_minute = per_minute
        self.per_hour = per_hour
        self.fail_open = fail_open

    async def __call__(
        self,
        user: Annotated[AuthenticatedUser, Depends(get_current_user)],
        tenant_context: Annotated[TenantContext, Depends(get_current_tenant)],
        limiter: Annotated[MultiWindowLimiter, Depends(get_rate_limiter)],
    ) -> None:
        await _check_both(
            limiter,
            tenant_context.tenant_id,
            user.id,
            self.per_minute,
            self.per_hour,
            self.fail_open,
        )


class IPRateLimitDependency:
    """Dependency for per-IP rate limiting (no authentication required).

    Useful for public endpoints or as an additional layer on authenticated
    routes.

    Usage:
        @router.post("/public-api")
        async def handler(
            _rate_limit: Annotated[None, Depends(IPRateLimitDependency(per_minute=10, per_hour=100))]
        ):
            ...
    """

    def __init__(self, per_minute: int, per_hour: int, fail_open: bool = True) -> None:
        """
        Args:
            per_minute: Maximum requests per minute per IP.
            per_hour: Maximum requests per hour per IP.
            fail_open: If True, allows requests when Redis is unavailable (default: True).
        """
        self.per_minute = per_minute
        self.per_hour = per_hour
        self.fail_open = fail_open

    async def __call__(
        self,
        request: Request,
        limiter: Annotated[MultiWindowLimiter, Depends(get_rate_limiter)],
    ) -> None:
        # Reuses the tenant+user-keyed limiter with the client IP standing in
        # for both — there's no tenant/user identity on an unauthenticated
        # request.
        ip_uuid = self._ip_to_uuid(self._get_client_ip(request))
        await _check_both(
            limiter, ip_uuid, ip_uuid, self.per_minute, self.per_hour, self.fail_open
        )

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request, checking X-Forwarded-For first."""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # X-Forwarded-For can contain multiple IPs; take the first (client).
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

        if request.client:
            return request.client.host

        return "unknown"

    def _ip_to_uuid(self, ip: str) -> UUID:
        """Converts an IP address to a deterministic UUID for use as a key."""
        hash_bytes = hashlib.md5(f"ip:{ip}".encode()).digest()
        return UUID(bytes=hash_bytes)
