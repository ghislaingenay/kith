"""An in-memory `EmbeddingProvider` stand-in. A text costs one token per
word, so a test sets how big a Chunk is by how many words it has. Records
every request it receives."""

from collections.abc import Sequence

from core.embedding.provider import (
    EmbeddingInputType,
    EmbeddingProvider,
    EmbeddingResult,
)

VECTOR_DIMENSION = 1024


def vector_for(text: str) -> list[float]:
    """The vector the fake gives a text, so a test can tell which text a
    stored vector came from."""
    return [float(len(text))] * VECTOR_DIMENSION


class FakeEmbeddingProvider(EmbeddingProvider):
    def __init__(self) -> None:
        self.requests: list[list[str]] = []
        self.input_types: list[EmbeddingInputType] = []

    async def count_tokens(self, texts: Sequence[str]) -> list[int]:
        return [len(text.split()) for text in texts]

    async def embed(
        self, texts: Sequence[str], *, input_type: EmbeddingInputType
    ) -> EmbeddingResult:
        self.requests.append(list(texts))
        self.input_types.append(input_type)
        return EmbeddingResult(
            vectors=[vector_for(text) for text in texts],
            tokens_used=sum(await self.count_tokens(texts)),
        )
