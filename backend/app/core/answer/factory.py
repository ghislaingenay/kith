"""Builds the configured `AnswerProvider`, if any."""

from core.answer.config import AnswerSettings
from core.answer.provider import AnswerProvider


def create_answer_provider(settings: AnswerSettings) -> AnswerProvider | None:
    """`None` until the OpenAI adapter exists (ADR-0016); every Ask then
    answers 503, and Search is unaffected."""
    return None
