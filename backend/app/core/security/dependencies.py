"""FastAPI dependency for the Origin-header check."""

from fastapi import Header

from core.container import container
from core.security.exceptions import OriginNotAllowedError


async def require_allowed_origin(origin: str | None = Header(default=None)) -> None:
    """Reject a state-changing request whose `Origin` header isn't in the
    same allow-list already used for CORS (`CorsSettings.allowed_origins`)
    — a browser request that would fail CORS couldn't complete anyway, so
    reusing that list adds no new config surface.

    A request with no `Origin` header at all is let through: browsers
    always send it on state-changing methods, so its absence means this
    request wasn't made by a browser (e.g. a server-to-server call) —
    outside what this check, layered on top of the `SameSite=Lax` cookie,
    is defending against.
    """
    if origin is None:
        return
    if origin not in container.cors_settings().allowed_origins:
        raise OriginNotAllowedError(origin)
