"""Abstract interface the reranker implements (ADR-0004)."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class RankedText:
    index: int
    """Position of the text in the request."""
    relevance_score: float


@dataclass(frozen=True)
class RerankResult:
    ranking: Sequence[RankedText]
    """Best first; may hold fewer texts than were sent."""
    tokens_used: int
    """What the model reported for the request."""


class Reranker(ABC):
    @abstractmethod
    async def rerank(self, query: str, texts: Sequence[str]) -> RerankResult:
        """Scores each text against the Query in one request. Never truncates
        a text."""
