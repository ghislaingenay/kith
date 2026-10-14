"""Builds the configured `AnswerProvider`, if any."""

from core.answer.circuit_breaker_answer_provider import CircuitBreakerAnswerProvider
from core.answer.config import AnswerSettings
from core.answer.openai_provider import OpenAIAnswerProvider
from core.answer.provider import AnswerProvider
from core.answer.time_limited_answer_provider import (
    ANSWER_TIMEOUT_SECONDS,
    TimeLimitedAnswerProvider,
)
from core.circuit_breaker.breaker import CircuitBreaker


def create_answer_provider(
    settings: AnswerSettings, breaker: CircuitBreaker
) -> AnswerProvider | None:
    """`None` when there is no OpenAI key; every Ask then answers 503, and
    Search is unaffected (ADR-0016). The time limit sits inside the breaker,
    so a slow model counts as a down one."""
    if not settings.openai_api_key:
        return None
    return CircuitBreakerAnswerProvider(
        TimeLimitedAnswerProvider(
            OpenAIAnswerProvider(settings), ANSWER_TIMEOUT_SECONDS
        ),
        breaker,
    )
