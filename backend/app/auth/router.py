"""Authentication HTTP router."""

from typing import Annotated

from fastapi import APIRouter, Depends

from auth.dependencies import get_magic_link_service
from auth.schemas import MagicLinkRequest, MagicLinkRequestResponse
from auth.service import MagicLinkService

router = APIRouter(prefix="/auth", tags=["auth"])

_MAGIC_LINK_RESPONSE = MagicLinkRequestResponse(
    message="If that email has an account, a magic link is on its way."
)


@router.post("/magic-link", response_model=MagicLinkRequestResponse)
async def request_magic_link(
    data: MagicLinkRequest,
    service: Annotated[MagicLinkService, Depends(get_magic_link_service)],
) -> MagicLinkRequestResponse:
    """Always returns the same response regardless of whether `data.email`
    has an account (ADR-0006's enumeration guard) — the per-email rate
    limit is the only thing that can produce a different status (429)."""
    await service.request_magic_link(data.email)
    return _MAGIC_LINK_RESPONSE
