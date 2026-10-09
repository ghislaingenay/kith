"""Builds the configured `Reranker`, if any."""

from core.circuit_breaker.breaker import CircuitBreaker
from core.embedding.config import EmbeddingSettings
from core.rerank.circuit_breaker_reranker import CircuitBreakerReranker
from core.rerank.config import RerankSettings
from core.rerank.provider import Reranker
from core.rerank.time_limited_reranker import (
    RERANK_TIMEOUT_SECONDS,
    TimeLimitedReranker,
)
from core.rerank.voyage_reranker import VoyageReranker
from pydantic import ValidationError


def create_reranker(
    settings: RerankSettings, breaker: CircuitBreaker
) -> Reranker | None:
    """`None` when Rerank is switched off or there is no Voyage API key; Ask's
    Retrieval then keeps Retrieval's order. The time limit sits inside the
    breaker, so a slow reranker counts as a down one."""
    if not settings.enabled:
        return None
    try:
        api_key = EmbeddingSettings().voyage_api_key
    except ValidationError:
        return None
    return CircuitBreakerReranker(
        TimeLimitedReranker(VoyageReranker(settings, api_key), RERANK_TIMEOUT_SECONDS),
        breaker,
    )
