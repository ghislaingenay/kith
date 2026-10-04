"""Replays failed indexing batches. Run with `make search-replay`; see
`docs/search-quickstart.md`."""

import argparse
import asyncio
import uuid

from core.container import container
from documents.dead_letter_replay import replay_failed_batches


async def main() -> None:
    parser = argparse.ArgumentParser(description="Replay failed indexing batches")
    parser.add_argument("--document-id", type=uuid.UUID, help="only this Document")
    parser.add_argument("--limit", type=int, help="at most this many rows")
    args = parser.parse_args()

    container.logging_configured()
    search_index = container.search_index()
    try:
        result = await replay_failed_batches(
            container.db_session_factory(),
            search_index,
            container.retry_handler(),
            document_id=args.document_id,
            limit=args.limit,
        )
    finally:
        await search_index.close()
        await container.db_engine().dispose()
    print(f"Replay: {result.resolved} resolved, {result.failed} still open")


if __name__ == "__main__":
    asyncio.run(main())
