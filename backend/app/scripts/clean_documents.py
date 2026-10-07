"""Removes every Document, Chunk and Upload in every Tenant, their files in
storage (not the bucket) and the search index, then creates the index again.
Run with `make clean-documents`; see `docs/search-quickstart.md`. For
development only: it cannot be undone."""

import argparse
import asyncio

from core.container import container
from documents.clean_documents import clean_documents


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Delete every Document, its files and the search index"
    )
    parser.add_argument(
        "--yes", action="store_true", help="do not ask for confirmation"
    )
    args = parser.parse_args()
    if (
        not args.yes
        and input("Delete ALL Documents, files and the search index? Type 'yes': ")
        != "yes"
    ):
        print("Nothing was deleted")
        return

    container.logging_configured()
    search_index = container.search_index()
    try:
        result = await clean_documents(
            container.db_session_factory(), container.storage_provider(), search_index
        )
    finally:
        await search_index.close()
        await container.db_engine().dispose()
    print(f"Deleted {result.documents} Document(s) and {result.uploads} Upload(s)")


if __name__ == "__main__":
    asyncio.run(main())
