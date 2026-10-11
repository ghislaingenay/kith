"""FastAPI dependency wiring for the answer core module."""

from core.answer.config import AnswerSettings
from core.answer.provider import AnswerProvider
from core.container import container


def get_answer_settings() -> AnswerSettings:
    return container.answer_settings()


def get_answer_provider() -> AnswerProvider | None:
    """`None` when no answer model is configured; Ask then answers 503."""
    return container.answer_provider()
