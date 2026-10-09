"""Runs Ask's Retrieval for a Query in one Tenant, with Rerank forced on or off,
and prints the Chunks Ask would cite. Run with `make retrieve`; see
`docs/search-quickstart.md`. Both modes start from the same `RERANK_FETCH_SIZE`
candidates, so their orders can be compared."""

import argparse
import asyncio
import sys

from core.container import container
from documents.exceptions import BlankQueryError
from documents.repository import DocumentsRepository
from documents.retrieval_service import AskRetrieval, RetrievalService
from tenants.repository import TenantsRepository

PREVIEW_LENGTH = 150


def _on_or_off(value: str) -> bool:
    if value not in ("true", "false"):
        raise argparse.ArgumentTypeError("must be true or false")
    return value == "true"


def _print(retrieval: AskRetrieval, *, rerank: bool) -> None:
    if not retrieval.chunks:
        print("No Chunks found")
    for rank, chunk in enumerate(retrieval.chunks, start=1):
        score = "" if chunk.rerank_score is None else f"{chunk.rerank_score:.4f}"
        preview = " ".join(chunk.result.text.split())[:PREVIEW_LENGTH]
        print(
            f"{rank:>2}  {score:>6}  {chunk.result.document_name}"
            f"  p.{chunk.result.page_number}\n    {preview}"
        )
    print(f"Rerank tokens used: {retrieval.rerank_tokens}")
    if retrieval.is_reranked:
        print(f"Reranked with {container.rerank_settings().model}")
    elif rerank and retrieval.chunks:
        print("Rerank fell back to Retrieval's order (see the warning above)")
    else:
        print("Not reranked: Retrieval's order")
    if retrieval.degraded:
        print("Keyword matches only: the Query could not be embedded")


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print the Chunks Ask's Retrieval returns for a Query"
    )
    parser.add_argument("query", help="the Query")
    parser.add_argument("--tenant", required=True, help="the Tenant's slug")
    parser.add_argument(
        "--rerank",
        type=_on_or_off,
        required=True,
        help="true or false, over RERANK_ENABLED",
    )
    args = parser.parse_args()

    container.logging_configured()
    search_index = container.search_index()
    try:
        async with container.db_session_factory()() as session:
            tenant_id = await TenantsRepository(session).get_tenant_id_by_slug(
                args.tenant
            )
            if tenant_id is None:
                sys.exit(f"No Tenant with the slug {args.tenant!r}")
            service = RetrievalService(
                DocumentsRepository(session),
                search_index,
                container.query_embedding_provider(),
                container.retrieval_settings(),
                container.reranker(),
                container.rerank_settings(),
            )
            try:
                retrieval = await service.retrieve_for_ask(
                    tenant_id=tenant_id,
                    user_id=None,
                    query=args.query,
                    rerank=args.rerank,
                )
            except BlankQueryError:
                sys.exit("The Query is blank")
    finally:
        await search_index.close()
        await container.db_engine().dispose()
    _print(retrieval, rerank=args.rerank)


if __name__ == "__main__":
    asyncio.run(main())
