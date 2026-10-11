"""Builds the configured `AnswerProvider`, if any."""

from core.answer.config import AnswerSettings
from core.answer.openai_provider import OpenAIAnswerProvider
from core.answer.provider import AnswerProvider


def create_answer_provider(settings: AnswerSettings) -> AnswerProvider | None:
    """`None` when there is no OpenAI key; every Ask then answers 503, and
    Search is unaffected (ADR-0016)."""
    if not settings.openai_api_key:
        return None
    return OpenAIAnswerProvider(settings)
