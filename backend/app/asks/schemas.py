"""Pydantic API schemas for the asks domain: the request, and the data of
each event the Ask's stream sends."""

import uuid

from pydantic import BaseModel, Field

from asks.models import AskStatus


class AskRequest(BaseModel):
    query: str = Field(max_length=1000)


class CitedPassage(BaseModel):
    """A passage the Answer may cite as `[n]`."""

    n: int
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    page_number: int
    text: str


class CitationsEvent(BaseModel):
    """Sent first, before any of the Answer."""

    passages: list[CitedPassage]


class AnswerDeltaEvent(BaseModel):
    text: str


class AskDoneEvent(BaseModel):
    """Sent last. `credits_charged` is rounded up; `balance_credits` is the
    new Credit Balance, rounded down like everywhere else."""

    ask_id: uuid.UUID
    status: AskStatus
    credits_charged: int
    balance_credits: int
    reranked: bool
    degraded: bool


AskEvent = CitationsEvent | AnswerDeltaEvent | AskDoneEvent
