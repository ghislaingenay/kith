"""FastAPI dependency wiring for the asks domain."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from asks.repository import AsksRepository
from asks.service import AskService
from core.answer.config import AnswerSettings
from core.answer.dependencies import get_answer_provider, get_answer_settings
from core.answer.provider import AnswerProvider
from credits.dependencies import get_credit_settings
from credits.config import CreditSettings
from credits.repository import CreditsRepository
from credits.service import CreditsService
from documents.dependencies import get_db_session, get_retrieval_service
from documents.retrieval_service import RetrievalService


def get_ask_service(
    # The session Retrieval uses, so one request holds one connection and the
    # Ask and its Ask Charge commit together.
    session: Annotated[AsyncSession, Depends(get_db_session)],
    retrieval_service: Annotated[RetrievalService, Depends(get_retrieval_service)],
    credit_settings: Annotated[CreditSettings, Depends(get_credit_settings)],
    answer_provider: Annotated[AnswerProvider | None, Depends(get_answer_provider)],
    answer_settings: Annotated[AnswerSettings, Depends(get_answer_settings)],
) -> AskService:
    return AskService(
        AsksRepository(session),
        retrieval_service,
        CreditsService(CreditsRepository(session), credit_settings),
        answer_provider,
        answer_settings,
    )
