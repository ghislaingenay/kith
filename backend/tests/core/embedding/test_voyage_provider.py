"""How `VoyageEmbeddingProvider` talks to Voyage, against a stub client: the
real API is never called by automated tests."""

import pytest
from core.embedding.config import EmbeddingSettings
from core.embedding.exceptions import EmbeddingError, EmbeddingUnavailableError
from core.embedding.provider import EmbeddingInputType
from core.embedding.voyage_provider import VoyageEmbeddingProvider
from voyageai import error as voyage_error
from voyageai.object import EmbeddingsObject


class _StubClient:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.embed_calls: list[dict] = []
        self.tokenize_calls: list[tuple[list[str], str]] = []

    async def embed(self, texts: list[str], **options: object) -> EmbeddingsObject:
        self.embed_calls.append({"texts": texts, **options})
        if self.error is not None:
            raise self.error
        response = EmbeddingsObject()
        response.embeddings = [[0.25] * 1024 for _ in texts]
        response.total_tokens = 7
        return response

    def tokenize(self, texts: list[str], model: str) -> list[list[int]]:
        self.tokenize_calls.append((texts, model))
        return [list(range(len(text.split()))) for text in texts]


def _provider(client: _StubClient) -> VoyageEmbeddingProvider:
    return VoyageEmbeddingProvider(EmbeddingSettings(voyage_api_key="key"), client)


async def test_texts_are_embedded_with_the_documented_options() -> None:
    client = _StubClient()

    result = await _provider(client).embed(
        ["first", "second"], input_type=EmbeddingInputType.DOCUMENT
    )

    assert client.embed_calls == [
        {
            "texts": ["first", "second"],
            "model": "voyage-4-large",
            "input_type": "document",
            "truncation": False,
            "output_dimension": 1024,
        }
    ]
    assert result.vectors == [[0.25] * 1024] * 2
    assert result.tokens_used == 7


async def test_tokens_are_counted_per_text_with_the_models_tokenizer() -> None:
    client = _StubClient()

    counts = await _provider(client).count_tokens(["one two three", "four"])

    assert counts == [3, 1]
    assert client.tokenize_calls == [(["one two three", "four"], "voyage-4-large")]


@pytest.mark.parametrize(
    "error",
    [
        voyage_error.Timeout("timed out"),
        voyage_error.APIConnectionError("connection reset"),
        voyage_error.RateLimitError("slow down", http_status=429),
        voyage_error.ServerError("boom", http_status=500),
        voyage_error.ServiceUnavailableError("overloaded", http_status=503),
        voyage_error.APIError("bad gateway page", http_status=520),
    ],
)
async def test_a_model_that_is_down_or_busy_is_reported_as_unavailable(
    error: Exception,
) -> None:
    with pytest.raises(EmbeddingUnavailableError):
        await _provider(_StubClient(error=error)).embed(
            ["text"], input_type=EmbeddingInputType.DOCUMENT
        )


@pytest.mark.parametrize(
    "error",
    [
        voyage_error.InvalidRequestError("text too long", http_status=400),
        voyage_error.AuthenticationError("bad key", http_status=401),
        voyage_error.MalformedRequestError("malformed", http_status=422),
        voyage_error.APIError("unexpected", http_status=418),
    ],
)
async def test_a_request_the_model_rejects_is_not_reported_as_unavailable(
    error: Exception,
) -> None:
    with pytest.raises(EmbeddingError) as raised:
        await _provider(_StubClient(error=error)).embed(
            ["text"], input_type=EmbeddingInputType.DOCUMENT
        )

    assert not isinstance(raised.value, EmbeddingUnavailableError)
