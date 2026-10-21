"""Refills the search index from Postgres after it is lost (ADR-0019): creates
the index again, re-indexes every Document's Chunks and queues their
embedding. Run with `make rebuild-index`; see `docs/search-quickstart.md`."""

import argparse
import asyncio
import sys

from core.container import container
from documents.exceptions import IngestionInProgressError
from documents.rebuild_index import rebuild_index


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recreate the search index and refill it from Postgres"
    )
    parser.add_argument(
        "--yes", action="store_true", help="do not ask for confirmation"
    )
    args = parser.parse_args()
    if (
        not args.yes
        and input(
            "Delete the search index and rebuild it from Postgres? Search stays "
            "incomplete until it finishes. Type 'yes': "
        )
        != "yes"
    ):
        print("Nothing was changed")
        return

    container.logging_configured()
    search_index = container.search_index()
    job_queue = container.job_queue()
    try:
        result = await rebuild_index(
            container.db_session_factory(),
            search_index,
            job_queue,
            container.retry_handler(),
            container.ingestion_settings(),
        )
    except IngestionInProgressError as exc:
        sys.exit(f"Refused, nothing changed: {exc}")
    finally:
        await search_index.close()
        await job_queue.close()
        await container.db_engine().dispose()
    print(
        f"Re-indexed {result.documents_reindexed} Document(s), queued embedding "
        f"for {result.documents_queued_for_embedding}, "
        f"{result.chunks_dead_lettered} Chunk(s) dead-lettered"
    )


if __name__ == "__main__":
    asyncio.run(main())
