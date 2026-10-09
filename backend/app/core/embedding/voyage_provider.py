"""`EmbeddingProvider` backed by Voyage `voyage-4-large` (ADR-0004)."""

import asyncio
from collections.abc import Sequence

from core.embedding.config import EmbeddingSettings
from core.embedding.exceptions import EmbeddingError, EmbeddingUnavailableError
from core.embedding.provider import (
    VECTOR_DIMENSION,
    EmbeddingInputType,
    EmbeddingProvider,
    EmbeddingResult,
)
from voyageai import error as voyage_error
from voyageai.client_async import AsyncClient

VOYAGE_MODEL = "voyage-4-large"

_UNAVAILABLE_ERRORS = (
    voyage_error.Timeout,
    voyage_error.APIConnectionError,
    voyage_error.RateLimitError,
    voyage_error.ServerError,
    voyage_error.ServiceUnavailableError,
)


def is_voyage_unavailable(error: voyage_error.VoyageError) -> bool:
    """Down, slow or overloaded, as opposed to a request Voyage rejects. Shared
    with the Voyage reranker."""
    if isinstance(error, _UNAVAILABLE_ERRORS):
        return True
    return isinstance(error, voyage_error.APIError) and (error.http_status or 0) >= 500


class VoyageEmbeddingProvider(EmbeddingProvider):
    def __init__(
        self,
        settings: EmbeddingSettings,
        client: AsyncClient | None = None,
    ) -> None:
        # One attempt: the application's retry handler does the retrying.
        self._client = client or AsyncClient(
            api_key=settings.voyage_api_key, max_retries=1
        )

    async def count_tokens(self, texts: Sequence[str]) -> list[int]:
        # Voyage's tokenizer is loaded from disk or downloaded on first use,
        # so it runs off the event loop.
        encodings = await asyncio.to_thread(
            self._client.tokenize, list(texts), VOYAGE_MODEL
        )
        return [len(encoding) for encoding in encodings]

    async def embed(
        self, texts: Sequence[str], *, input_type: EmbeddingInputType
    ) -> EmbeddingResult:
        try:
            response = await self._client.embed(
                list(texts),
                model=VOYAGE_MODEL,
                input_type=input_type.value,
                truncation=False,
                output_dimension=VECTOR_DIMENSION,
            )
        except voyage_error.VoyageError as error:
            if is_voyage_unavailable(error):
                raise EmbeddingUnavailableError(f"Embedding failed: {error}") from error
            raise EmbeddingError(f"Embedding was rejected: {error}") from error
        return EmbeddingResult(
            vectors=response.embeddings, tokens_used=response.total_tokens
        )
