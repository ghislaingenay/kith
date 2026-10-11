"""HTTP layer for the asks domain."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from asks.dependencies import get_ask_service
from asks.schemas import (
    AnswerDeltaEvent,
    AskDoneEvent,
    AskEvent,
    AskRequest,
    CitationsEvent,
)
from asks.service import AskService
from auth.dependencies import get_current_tenant, get_current_user
from auth.schemas import AuthenticatedUser, TenantContext
from core.ratelimit.dependencies import RateLimitDependency
from core.security.dependencies import require_allowed_origin
from tenants.dependencies import require_permission
from tenants.permissions import Action

_ASKS_PER_MINUTE = 10
# The minute budget already caps an hour at this.
_ASKS_PER_HOUR = 10 * 60

_EVENT_NAMES: dict[type[AskEvent], str] = {
    CitationsEvent: "citations",
    AnswerDeltaEvent: "answer_delta",
    AskDoneEvent: "done",
}

router = APIRouter(
    prefix="/asks",
    tags=["asks"],
    dependencies=[
        Depends(require_allowed_origin),
        Depends(require_permission(Action.ASK)),
        Depends(
            RateLimitDependency(per_minute=_ASKS_PER_MINUTE, per_hour=_ASKS_PER_HOUR)
        ),
    ],
)


async def _server_sent_events(events: AsyncIterator[AskEvent]) -> AsyncIterator[str]:
    async for event in events:
        yield f"event: {_EVENT_NAMES[type(event)]}\ndata: {event.model_dump_json()}\n\n"


@router.post(
    "",
    response_class=StreamingResponse,
    summary="Answer a Query from the Tenant's Documents",
    description=(
        "Streams `text/event-stream`: `citations` (the numbered passages), "
        "`answer_delta` events, then `done` with the Credits charged. A "
        "refusal comes before the stream, as a problem response."
    ),
)
async def ask(
    data: AskRequest,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    tenant: Annotated[TenantContext, Depends(get_current_tenant)],
    service: Annotated[AskService, Depends(get_ask_service)],
) -> StreamingResponse:
    events = await service.ask(
        tenant_id=tenant.tenant_id, user_id=user.id, query=data.query
    )
    return StreamingResponse(
        _server_sent_events(events),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store"},
    )
