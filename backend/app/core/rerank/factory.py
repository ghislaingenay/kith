"""Builds the configured `Reranker`, if any."""

from core.embedding.config import EmbeddingSettings
from core.rerank.config import RerankSettings
from core.rerank.provider import Reranker
from core.rerank.voyage_reranker import VoyageReranker
from pydantic import ValidationError


def create_reranker(settings: RerankSettings) -> Reranker | None:
    """`None` when Rerank is switched off or there is no Voyage API key; Ask's
    Retrieval then keeps Retrieval's order."""
    if not settings.enabled:
        return None
    try:
        api_key = EmbeddingSettings().voyage_api_key
    except ValidationError:
        return None
    return VoyageReranker(settings, api_key)
