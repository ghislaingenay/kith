"""Enqueues embedding for Documents waiting at `embedding`. Run with
`make embed-documents`; see `docs/search-quickstart.md`."""

import argparse
import asyncio
import uuid

from core.container import container
from documents.embed_backlog import enqueue_embedding_backlog


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enqueue embedding for Documents waiting at embedding"
    )
    parser.add_argument("--document-id", type=uuid.UUID, help="only this Document")
    args = parser.parse_args()

    container.logging_configured()
    job_queue = container.job_queue()
    try:
        count = await enqueue_embedding_backlog(
            container.db_session_factory(), job_queue, document_id=args.document_id
        )
    finally:
        await job_queue.close()
        await container.db_engine().dispose()
    print(f"Enqueued embedding for {count} Document(s)")


if __name__ == "__main__":
    asyncio.run(main())
