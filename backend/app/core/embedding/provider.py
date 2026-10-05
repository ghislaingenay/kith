"""Abstract interface the embedding model implements (ADR-0004)."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum


class EmbeddingInputType(StrEnum):
    """Whether a text is stored for search or is a search Query; the model
    embeds the two differently."""

    DOCUMENT = "document"
    QUERY = "query"


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: Sequence[Sequence[float]]
    """One vector per input text, in the same order."""
    tokens_used: int
    """What the model reported for the request."""


class EmbeddingProvider(ABC):
    @abstractmethod
    async def count_tokens(self, texts: Sequence[str]) -> list[int]:
        """How many tokens each text is to the model, in the same order, so
        a caller can keep a request under the model's per-request cap."""

    @abstractmethod
    async def embed(
        self, texts: Sequence[str], *, input_type: EmbeddingInputType
    ) -> EmbeddingResult:
        """Embeds the texts in one request. Never truncates a text. Raises
        `EmbeddingUnavailableError` when the model cannot be reached or is
        overloaded, and `EmbeddingError` when it rejects the request."""
