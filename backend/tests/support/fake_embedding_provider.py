"""An in-memory `EmbeddingProvider` stand-in. A text costs one token per
word, so a test sets how big a Chunk is by how many words it has. Records
every request it receives, and can be scripted to fail the way an embedding
model that is down or that rejects a text does."""

from collections.abc import Sequence

from core.embedding.exceptions import EmbeddingError, EmbeddingUnavailableError
from core.embedding.provider import (
    VECTOR_DIMENSION,
    EmbeddingInputType,
    EmbeddingProvider,
    EmbeddingResult,
)


def vector_for(text: str) -> list[float]:
    """The vector the fake gives a text, so a test can tell which text a
    stored vector came from."""
    return [float(len(text))] * VECTOR_DIMENSION


class FakeEmbeddingProvider(EmbeddingProvider):
    def __init__(self) -> None:
        self.requests: list[list[str]] = []
        self.input_types: list[EmbeddingInputType] = []
        self.embed_calls = 0
        self.embed_outcomes: list[bool] = []
        """What each `embed` call does, in order: `True` works, `False` raises
        `EmbeddingUnavailableError`. Once used up, `is_down` decides."""
        self.is_down = False
        self.rejected_texts: set[str] = set()
        """A request containing one of these texts raises `EmbeddingError`, as
        the model does for a text it refuses."""
        self.crash_with: Exception | None = None
        """Raised by `embed` instead of anything else, to stand for a failure
        that is not the model being unavailable or rejecting the request."""

    async def count_tokens(self, texts: Sequence[str]) -> list[int]:
        return [len(text.split()) for text in texts]

    async def embed(
        self, texts: Sequence[str], *, input_type: EmbeddingInputType
    ) -> EmbeddingResult:
        self.embed_calls += 1
        if self.crash_with is not None:
            raise self.crash_with
        if self.rejected_texts.intersection(texts):
            raise EmbeddingError("fake embedding model rejected the request")
        is_working = self.embed_outcomes.pop(0) if self.embed_outcomes else not self.is_down
        if not is_working:
            raise EmbeddingUnavailableError("fake embedding model is down")
        self.requests.append(list(texts))
        self.input_types.append(input_type)
        return EmbeddingResult(
            vectors=[vector_for(text) for text in texts],
            tokens_used=sum(await self.count_tokens(texts)),
        )
