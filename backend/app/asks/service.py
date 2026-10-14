"""Asks domain service: a Query answered from Ask's Retrieval and charged to
the Credit Balance (ADR-0016, ADR-0017)."""

import asyncio
import uuid
from collections.abc import AsyncGenerator
from contextlib import aclosing
from datetime import UTC, datetime
from functools import partial

import anyio
from asks.models import Ask, AskStatus
from asks.prompt import build_answer_request
from asks.repository import AsksRepository
from asks.schemas import (
    AnswerDeltaEvent,
    AskDoneEvent,
    AskEvent,
    CitationsEvent,
    CitedPassage,
)
from core.answer.config import AnswerSettings
from core.answer.exceptions import AnswerError, AnswerUnavailableError
from core.answer.provider import (
    AnswerDelta,
    AnswerEnd,
    AnswerEnding,
    AnswerProvider,
)
from core.logging import setup_logger
from credits.service import CreditsService
from documents.retrieval_service import AskRetrieval, RetrievalService

logger = setup_logger(__name__)


def _status(end: AnswerEnd) -> AskStatus:
    """An Answer that ended early after the provider reported usage is
    `cut_off` and charged; with nothing reported it is `failed` (ADR-0017)."""
    if end.ending == AnswerEnding.FAILED and end.usage is not None:
        return AskStatus.CUT_OFF
    return AskStatus(end.ending.value)


class AskService:
    def __init__(
        self,
        repository: AsksRepository,
        retrieval_service: RetrievalService,
        credits_service: CreditsService,
        answer_provider: AnswerProvider | None,
        answer_settings: AnswerSettings,
    ) -> None:
        self.repository = repository
        self.retrieval_service = retrieval_service
        self.credits_service = credits_service
        self.answer_provider = answer_provider
        self.answer_settings = answer_settings

    async def ask(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, query: str
    ) -> AsyncGenerator[AskEvent]:
        """Refuses before anything is streamed: no answer model, no Credits
        left, a blank Query or the search store down. Otherwise runs Ask's
        Retrieval and returns the stream: the citations, the Answer's deltas,
        then `done` once the Ask and its Ask Charge are saved together."""
        if self.answer_provider is None:
            raise AnswerUnavailableError("Answers are not available right now.")
        await self.credits_service.require_credits_left(tenant_id)
        started_at = datetime.now(UTC)
        retrieval = await self.retrieval_service.retrieve_for_ask(
            tenant_id=tenant_id, user_id=user_id, query=query
        )
        return self._answer(
            self.answer_provider,
            tenant_id=tenant_id,
            user_id=user_id,
            query=query,
            retrieval=retrieval,
            started_at=started_at,
        )

    async def _answer(
        self,
        answer_provider: AnswerProvider,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        query: str,
        retrieval: AskRetrieval,
        started_at: datetime,
    ) -> AsyncGenerator[AskEvent]:
        passages = [chunk.result for chunk in retrieval.chunks]
        yield CitationsEvent(
            passages=[
                CitedPassage(
                    n=n,
                    chunk_id=passage.chunk_id,
                    document_id=passage.document_id,
                    document_name=passage.document_name,
                    page_number=passage.page_number,
                    text=passage.text,
                )
                for n, passage in enumerate(passages, start=1)
            ]
        )
        answer_parts: list[str] = []
        record = partial(
            self._record,
            tenant_id=tenant_id,
            user_id=user_id,
            query=query,
            retrieval=retrieval,
            started_at=started_at,
        )
        if not passages:
            # Nothing to answer from: the model is not called (ADR-0017).
            yield await record(answer="", end=None)
            return

        request = build_answer_request(query, [passage.text for passage in passages])
        end: AnswerEnd | None = None
        try:
            async with aclosing(answer_provider.stream_answer(request)) as parts:
                async for part in parts:
                    if isinstance(part, AnswerDelta):
                        answer_parts.append(part.text)
                        yield AnswerDeltaEvent(text=part.text)
                    else:
                        end = part
        except AnswerError as error:
            # The stream has started, so the failure is told in `done`.
            logger.warning("answer_failed", tenant_id=str(tenant_id), error=str(error))
            end = AnswerEnd(AnswerEnding.FAILED, None)
        except (asyncio.CancelledError, GeneratorExit):
            # The client left: `aclosing` stopped the model; record it anyway.
            await record(
                answer="".join(answer_parts),
                end=end or AnswerEnd(AnswerEnding.FAILED, None),
            )
            raise
        if end is None:
            raise RuntimeError("The answer provider's stream ended without an end")
        yield await record(answer="".join(answer_parts), end=end)

    async def _record(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        query: str,
        retrieval: AskRetrieval,
        started_at: datetime,
        answer: str,
        end: AnswerEnd | None,
    ) -> AskDoneEvent:
        """Saves the Ask and its Ask Charge together. `end` is `None` when the
        model was never called. Shielded, so a client that goes away part-way
        cannot leave the Ask unrecorded."""
        status = _status(end) if end else AskStatus.NO_CHUNKS
        usage = end.usage if end else None
        ask = Ask(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            query=query,
            answer=answer,
            status=status,
            cited_chunks=[
                {
                    "chunk_id": str(chunk.result.chunk_id),
                    "document_id": str(chunk.result.document_id),
                    "page_number": chunk.result.page_number,
                    "rerank_score": chunk.rerank_score,
                }
                for chunk in retrieval.chunks
            ],
            is_reranked=retrieval.is_reranked,
            is_degraded=retrieval.degraded,
            model=self.answer_settings.model,
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
            reasoning_tokens=usage.reasoning_tokens if usage else None,
            created_at=started_at,
            finished_at=datetime.now(UTC),
        )
        with anyio.CancelScope(shield=True):
            await self.repository.add(ask)
            credits_charged = await self.credits_service.charge_ask(
                tenant_id=tenant_id,
                ask_id=ask.id,
                user_id=user_id,
                tokens=usage.input_tokens + usage.output_tokens if usage else 0,
            )
            await self.repository.commit()
            balance = await self.credits_service.get_balance(tenant_id)
        logger.info(
            "ask_completed",
            tenant_id=str(tenant_id),
            user_id=str(user_id),
            ask_id=str(ask.id),
            status=ask.status,
            model=ask.model,
            input_tokens=ask.input_tokens,
            output_tokens=ask.output_tokens,
            reasoning_tokens=ask.reasoning_tokens,
            credits_charged=credits_charged,
            reranked=ask.is_reranked,
            degraded=ask.is_degraded,
        )
        return AskDoneEvent(
            ask_id=ask.id,
            status=AskStatus(ask.status),
            credits_charged=credits_charged,
            balance_credits=balance.credits,
            reranked=ask.is_reranked,
            degraded=ask.is_degraded,
        )
