"""Authentication HTTP router. `router` holds the `/auth`-prefixed
endpoints; `me_router` holds `GET /me`, which is deliberately not under
`/auth` (see auth/schemas.py:MeResponse)."""

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response
from pydantic import EmailStr

from auth.config import SESSION_COOKIE_NAME, SESSION_TTL_SECONDS, SessionCookieSettings
from auth.dependencies import (
    get_current_user,
    get_magic_link_service,
    get_magic_link_verification_service,
    get_session_service,
)
from auth.schemas import (
    AuthenticatedUser,
    LogoutResponse,
    MagicLinkRequest,
    MagicLinkRequestResponse,
    MeResponse,
    VerifyMagicLinkResponse,
)
from auth.service import MagicLinkService, MagicLinkVerificationService
from auth.session import SessionService
from core.security.dependencies import require_allowed_origin
from tenants.dependencies import get_tenants_service
from tenants.service import TenantsService

router = APIRouter(prefix="/auth", tags=["auth"])
me_router = APIRouter(tags=["me"])

_MAGIC_LINK_RESPONSE = MagicLinkRequestResponse(
    message="If that email has an account, a magic link is on its way."
)

# Every field has a default (unlike MagicLinkSettings.verify_url), so this
# can be a module-level singleton instead of the per-request instantiation
# `MagicLinkSettings` needs to keep unrelated importers of `auth.dependencies`
# from being forced to set an env var they don't need.
_cookie_settings = SessionCookieSettings()


def _set_session_cookie(response: Response, raw_session_id: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_session_id,
        max_age=SESSION_TTL_SECONDS,
        path="/",
        httponly=True,
        samesite="lax",
        secure=_cookie_settings.cookie_secure,
        domain=_cookie_settings.cookie_domain,
    )


@router.post(
    "/magic-link",
    response_model=MagicLinkRequestResponse,
    dependencies=[Depends(require_allowed_origin)],
)
async def request_magic_link(
    data: MagicLinkRequest,
    service: Annotated[MagicLinkService, Depends(get_magic_link_service)],
) -> MagicLinkRequestResponse:
    """Always returns the same response regardless of whether `data.email`
    has an account (ADR-0006's enumeration guard) — the per-email rate
    limit is the only thing that can produce a different status (429)."""
    await service.request_magic_link(data.email)
    return _MAGIC_LINK_RESPONSE


@router.get("/magic-link/verify", response_model=VerifyMagicLinkResponse)
async def verify_magic_link(
    token: str,
    email: EmailStr,
    response: Response,
    service: Annotated[
        MagicLinkVerificationService, Depends(get_magic_link_verification_service)
    ],
) -> VerifyMagicLinkResponse:
    """No Origin-header check here (unlike the other state-changing `/auth`
    routes): this is called server-to-server by the frontend's verify
    route, forwarding no browser `Origin` at all — see
    core/security/dependencies.py's docstring on why an absent Origin is
    let through."""
    _, raw_session_id = await service.verify(email=email, token=token)
    _set_session_cookie(response, raw_session_id)
    return VerifyMagicLinkResponse(message="Signed in.")


@router.post(
    "/logout",
    response_model=LogoutResponse,
    dependencies=[Depends(require_allowed_origin)],
)
async def logout(
    response: Response,
    session_service: Annotated[SessionService, Depends(get_session_service)],
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> LogoutResponse:
    """Idempotent: clears the cookie and, if a session was still live,
    deletes it — succeeds even against an already-expired or already-cleared
    session, since a caller trying to sign out shouldn't be told "you're
    not signed in"."""
    if session_cookie:
        await session_service.delete_session(session_cookie)
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        domain=_cookie_settings.cookie_domain,
    )
    return LogoutResponse(message="Signed out.")


@me_router.get("/me", response_model=MeResponse)
async def get_me(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    service: Annotated[TenantsService, Depends(get_tenants_service)],
) -> MeResponse:
    """No `X-Tenant-ID` required — the frontend calls this right after
    verifying a Magic Link, before it has a tenant to pick (its membership
    count decides where to redirect)."""
    memberships = await service.list_my_memberships(user.id)
    return MeResponse(user=user, memberships=memberships)
