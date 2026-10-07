"""Adds the fields the current mapping has to the existing search index, keeping
its Chunks. For development, after a field was added without a new mapping
version (`make refresh-index`); safe to run again."""

import asyncio

from core.container import container


async def main() -> None:
    search_index = container.search_index()
    try:
        await search_index.update_mapping()
    finally:
        await search_index.close()
    print(f"Mapping of {search_index.alias!r} is up to date")


if __name__ == "__main__":
    asyncio.run(main())
