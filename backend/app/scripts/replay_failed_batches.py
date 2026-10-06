"""Replays failed indexing and embedding batches. Run with `make search-replay`;
see `docs/search-quickstart.md`."""

import argparse
import asyncio
import uuid

from core.container import container
from documents.dead_letter_replay import replay_failed_batches
from documents.models import IngestionStage


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay failed indexing and embedding batches"
    )
    parser.add_argument(
        "--stage",
        type=IngestionStage,
        choices=[IngestionStage.INDEXING, IngestionStage.EMBEDDING],
        help="only this stage's rows (default: indexing, then embedding)",
    )
    parser.add_argument("--document-id", type=uuid.UUID, help="only this Document")
    parser.add_argument("--limit", type=int, help="at most this many rows")
    args = parser.parse_args()

    container.logging_configured()
    search_index = container.search_index()
    job_queue = container.job_queue()
    try:
        result = await replay_failed_batches(
            container.db_session_factory(),
            search_index,
            # Indexing alone must not need the Voyage key.
            None
            if args.stage == IngestionStage.INDEXING
            else container.embedding_provider(),
            container.retry_handler(),
            job_queue,
            stage=args.stage,
            document_id=args.document_id,
            limit=args.limit,
        )
    finally:
        await search_index.close()
        await job_queue.close()
        await container.db_engine().dispose()
    print(f"Replay: {result.resolved} resolved, {result.failed} still open")


if __name__ == "__main__":
    asyncio.run(main())
