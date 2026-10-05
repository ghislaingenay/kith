"""Tests for #65: `embed_document` turns a Document's indexed Chunks into
vectors. Called directly as a job function, against real Postgres, a
`FakeSearchIndex` and a `FakeEmbeddingProvider`; the provider is never the
real Voyage API."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from core.database import DatabaseSettings, create_engine, create_session_factory
from core.embedding.provider import EmbeddingInputType
from documents.config import IngestionSettings
from documents.embed import embed_document
from documents.models import (
    ChunkDeadLetter,
    ChunkStatus,
    IngestionStage,
    IngestionStatus,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from structlog.testing import capture_logs

from tests.documents.conftest import Caller, fast_retry_handler
from tests.documents.embedding_support import (
    document_waiting_at_embedding,
    load_chunks,
    load_document,
)
from tests.support.fake_embedding_provider import FakeEmbeddingProvider, vector_for
from tests.support.fake_search_index import FakeSearchIndex


@pytest.fixture
async def session_factory(_database_url: str) -> AsyncIterator[async_sessionmaker]:
    engine = create_engine(DatabaseSettings(database_url=_database_url))
    yield create_session_factory(engine)
    await engine.dispose()


@pytest.fixture
def search_index() -> FakeSearchIndex:
    return FakeSearchIndex()


@pytest.fixture
def embedding_provider() -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider()


@pytest.fixture
def embed_ctx(
    session_factory: async_sessionmaker,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
) -> dict:
    return {
        "db_session_factory": session_factory,
        "ingestion_settings": IngestionSettings(),
        "search_index": search_index,
        "embedding_provider": embedding_provider,
        "retry_handler": fast_retry_handler(),
    }


async def _embed(ctx: dict, caller: Caller, document_id: uuid.UUID) -> None:
    await embed_document(
        ctx, document_id=str(document_id), tenant_id=str(caller.tenant_id)
    )


async def test_embedding_a_document_waiting_at_embedding_makes_it_ready(
    caller: Caller,
    db_session: AsyncSession,
    search_index: FakeSearchIndex,
    embed_ctx: dict,
) -> None:
    texts = ["first chunk text", "second chunk text"]
    document_id = await document_waiting_at_embedding(
        db_session, search_index, caller, texts
    )

    await _embed(embed_ctx, caller, document_id)

    chunks = await load_chunks(db_session, document_id)
    assert [chunk.embedding_status for chunk in chunks] == [ChunkStatus.DONE] * 2
    assert [search_index.embeddings[chunk.id] for chunk in chunks] == [
        vector_for(text) for text in texts
    ]
    document = await load_document(db_session, document_id)
    assert document.ingestion_status == IngestionStatus.READY
    assert document.ingestion_stage == IngestionStage.EMBEDDING
    assert document.ingestion_error is None


async def test_chunks_are_embedded_as_documents(
    caller: Caller,
    db_session: AsyncSession,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
    embed_ctx: dict,
) -> None:
    document_id = await document_waiting_at_embedding(
        db_session, search_index, caller, ["some text"]
    )

    await _embed(embed_ctx, caller, document_id)

    assert embedding_provider.input_types == [EmbeddingInputType.DOCUMENT]


async def test_a_second_run_sends_nothing_to_the_provider(
    caller: Caller,
    db_session: AsyncSession,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
    embed_ctx: dict,
) -> None:
    document_id = await document_waiting_at_embedding(
        db_session, search_index, caller, ["first text", "second text"]
    )
    await _embed(embed_ctx, caller, document_id)
    requests_after_first_run = len(embedding_provider.requests)

    await _embed(embed_ctx, caller, document_id)

    assert requests_after_first_run == 1
    assert len(embedding_provider.requests) == 1


async def test_only_chunks_that_are_indexed_and_pending_embedding_are_sent(
    caller: Caller,
    db_session: AsyncSession,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
    embed_ctx: dict,
) -> None:
    document_id = await document_waiting_at_embedding(
        db_session,
        search_index,
        caller,
        ["already embedded", "pending text", "never indexed"],
    )
    already_embedded, _, never_indexed = await load_chunks(db_session, document_id)
    already_embedded.embedding_status = ChunkStatus.DONE
    never_indexed.indexing_status = ChunkStatus.FAILED
    await db_session.commit()

    await _embed(embed_ctx, caller, document_id)

    assert embedding_provider.requests == [["pending text"]]


async def test_a_document_with_chunks_that_failed_indexing_ends_partial(
    caller: Caller,
    db_session: AsyncSession,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
    embed_ctx: dict,
) -> None:
    document_id = await document_waiting_at_embedding(
        db_session, search_index, caller, ["indexed text", "failed text"]
    )
    document = await load_document(db_session, document_id)
    _, failed_chunk = await load_chunks(db_session, document_id)
    failed_chunk.indexing_status = ChunkStatus.FAILED
    document.ingestion_status = IngestionStatus.PARTIAL
    await db_session.commit()

    await _embed(embed_ctx, caller, document_id)

    assert embedding_provider.requests == [["indexed text"]]
    assert (await load_document(db_session, document_id)).ingestion_status == (
        IngestionStatus.PARTIAL
    )


async def test_chunks_over_the_token_cap_are_split_across_several_requests(
    caller: Caller,
    db_session: AsyncSession,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
    embed_ctx: dict,
) -> None:
    embed_ctx["ingestion_settings"] = IngestionSettings.model_validate(
        {"INGESTION_EMBED_BATCH_TOKEN_CAP": 10}
    )
    document_id = await document_waiting_at_embedding(
        db_session,
        search_index,
        caller,
        [
            "one two three four",
            "five six seven",
            "eight nine ten eleven",
            "twelve",
        ],
    )

    await _embed(embed_ctx, caller, document_id)

    assert [len(request) for request in embedding_provider.requests] == [2, 2]
    assert (await load_document(db_session, document_id)).ingestion_status == (
        IngestionStatus.READY
    )
    assert all(
        chunk.embedding_status == ChunkStatus.DONE
        for chunk in await load_chunks(db_session, document_id)
    )


async def test_a_chunk_over_the_cap_on_its_own_is_sent_alone(
    caller: Caller,
    db_session: AsyncSession,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
    embed_ctx: dict,
) -> None:
    embed_ctx["ingestion_settings"] = IngestionSettings.model_validate(
        {"INGESTION_EMBED_BATCH_TOKEN_CAP": 3}
    )
    document_id = await document_waiting_at_embedding(
        db_session, search_index, caller, ["a", "b c d e f", "g"]
    )

    await _embed(embed_ctx, caller, document_id)

    assert embedding_provider.requests == [["a"], ["b c d e f"], ["g"]]


async def test_a_request_never_holds_more_chunks_than_the_limit(
    caller: Caller,
    db_session: AsyncSession,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
    embed_ctx: dict,
) -> None:
    embed_ctx["ingestion_settings"] = IngestionSettings.model_validate(
        {"INGESTION_EMBED_BATCH_MAX_CHUNKS": 2}
    )
    document_id = await document_waiting_at_embedding(
        db_session, search_index, caller, ["a", "b", "c"]
    )

    await _embed(embed_ctx, caller, document_id)

    assert embedding_provider.requests == [["a", "b"], ["c"]]


async def test_the_tokens_used_are_logged_for_the_document(
    caller: Caller,
    db_session: AsyncSession,
    search_index: FakeSearchIndex,
    embed_ctx: dict,
) -> None:
    document_id = await document_waiting_at_embedding(
        db_session, search_index, caller, ["one two three", "four five"]
    )

    with capture_logs() as logs:
        await _embed(embed_ctx, caller, document_id)

    [embedded] = [log for log in logs if log["event"] == "embed_document_embedded"]
    assert embedded["document_id"] == str(document_id)
    assert embedded["tokens_used"] == 5


async def test_a_chunk_missing_from_the_index_is_not_marked_embedded(
    caller: Caller,
    db_session: AsyncSession,
    search_index: FakeSearchIndex,
    embed_ctx: dict,
) -> None:
    document_id = await document_waiting_at_embedding(
        db_session, search_index, caller, ["still indexed", "gone"]
    )
    search_index.indexed = search_index.indexed[:1]

    await _embed(embed_ctx, caller, document_id)

    still_indexed, gone = await load_chunks(db_session, document_id)
    assert still_indexed.embedding_status == ChunkStatus.DONE
    assert gone.embedding_status == ChunkStatus.PENDING
    assert (await load_document(db_session, document_id)).ingestion_status == (
        IngestionStatus.PROCESSING
    )


async def test_a_document_deleted_while_embedding_is_logged_and_skipped_not_failed(
    caller: Caller,
    db_session: AsyncSession,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
    embed_ctx: dict,
) -> None:
    document_id = await document_waiting_at_embedding(
        db_session, search_index, caller, ["first chunk", "second chunk"]
    )

    async def delete_document_while_the_model_works() -> None:
        # What the delete and its purge leave behind: the Document marked
        # deleted and its Chunks gone from the index.
        document = await load_document(db_session, document_id)
        document.ingestion_status = IngestionStatus.DELETED
        document.deleted_at = datetime.now(UTC)
        await db_session.commit()
        search_index.indexed.clear()

    embedding_provider.after_embed = delete_document_while_the_model_works

    with capture_logs() as logs:
        await _embed(embed_ctx, caller, document_id)

    [warning] = [
        log for log in logs if log["event"] == "embed_document_chunks_not_in_index"
    ]
    assert warning["log_level"] == "warning"
    assert warning["document_id"] == str(document_id)
    assert warning["chunks"] == 2
    chunks = await load_chunks(db_session, document_id)
    assert [chunk.embedding_status for chunk in chunks] == [ChunkStatus.PENDING] * 2
    assert (
        await db_session.execute(
            select(ChunkDeadLetter).where(ChunkDeadLetter.document_id == document_id)
        )
    ).first() is None
    assert (await load_document(db_session, document_id)).ingestion_status == (
        IngestionStatus.DELETED
    )


async def test_a_document_deleted_after_its_last_vector_is_written_stays_deleted(
    caller: Caller,
    db_session: AsyncSession,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
    embed_ctx: dict,
) -> None:
    document_id = await document_waiting_at_embedding(
        db_session, search_index, caller, ["only chunk"]
    )

    async def delete_document() -> None:
        document = await load_document(db_session, document_id)
        document.ingestion_status = IngestionStatus.DELETED
        document.deleted_at = datetime.now(UTC)
        await db_session.commit()

    embedding_provider.after_embed = delete_document

    await _embed(embed_ctx, caller, document_id)

    assert (await load_document(db_session, document_id)).ingestion_status == (
        IngestionStatus.DELETED
    )


@pytest.mark.parametrize(
    ("status", "stage"),
    [
        (IngestionStatus.UPLOADED, None),
        (IngestionStatus.PROCESSING, IngestionStage.INDEXING),
        (IngestionStatus.DELETED, None),
    ],
)
async def test_a_document_that_is_not_waiting_for_vectors_is_left_alone(
    caller: Caller,
    db_session: AsyncSession,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
    embed_ctx: dict,
    status: IngestionStatus,
    stage: IngestionStage | None,
) -> None:
    document_id = await document_waiting_at_embedding(
        db_session, search_index, caller, ["some text"]
    )
    document = await load_document(db_session, document_id)
    document.ingestion_status = status
    document.ingestion_stage = stage
    if status == IngestionStatus.DELETED:
        document.deleted_at = datetime.now(UTC)
    await db_session.commit()

    await _embed(embed_ctx, caller, document_id)

    assert embedding_provider.requests == []
    assert (await load_document(db_session, document_id)).ingestion_status == status


async def test_a_job_for_another_tenants_document_does_nothing(
    caller: Caller,
    db_session: AsyncSession,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
    embed_ctx: dict,
) -> None:
    document_id = await document_waiting_at_embedding(
        db_session, search_index, caller, ["some text"]
    )

    await embed_document(
        embed_ctx, document_id=str(document_id), tenant_id=str(uuid.uuid4())
    )

    assert embedding_provider.requests == []


async def test_a_job_for_a_missing_document_does_nothing(
    caller: Caller,
    embedding_provider: FakeEmbeddingProvider,
    embed_ctx: dict,
) -> None:
    await _embed(embed_ctx, caller, uuid.uuid4())

    assert embedding_provider.requests == []
