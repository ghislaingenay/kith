"""Creates the search index and alias if they do not exist.

Run with `make search-index-create`; safe to run again."""

import asyncio

from core.container import container


async def main() -> None:
    search_index = container.search_index()
    try:
        await search_index.ensure_index()
    finally:
        await search_index.close()
    print(f"Search index ready behind alias {search_index.alias!r}")


if __name__ == "__main__":
    asyncio.run(main())
