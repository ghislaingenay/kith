from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from auth.router import me_router
from auth.router import router as auth_router
from core.container import container
from core.exceptions import register_exception_handlers
from core.migrations import warn_if_schema_out_of_date
from core.logging import setup_logger
from core.search.startup import require_search_index
from credits.router import router as credits_router
from documents.router import library_router
from documents.router import router as uploads_router
from documents.router import search_router
from tenants.router import router as tenants_router
from users.router import router as users_router


logger = setup_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Order matters: logging must be configured before anything else has a
    # chance to log. `db_engine`/`cache_provider`/`rate_limiter` are called
    # eagerly so a bad DATABASE_URL/REDIS_URL fails fast at startup instead
    # of on first request (see notes in core/container.py).
    container.logging_configured()
    await warn_if_schema_out_of_date(container.db_engine())
    container.cache_provider()
    container.rate_limiter()
    container.mailer()
    container.job_queue()
    await require_search_index(container.search_index())
    if container.query_embedding_provider() is None:
        logger.warning(
            "voyage_api_key_missing",
            detail="VOYAGE_API_KEY is not set; every Search runs keyword only",
        )
    if container.rerank_settings().enabled and container.reranker() is None:
        logger.warning(
            "rerank_voyage_api_key_missing",
            detail="VOYAGE_API_KEY is not set; Ask's Retrieval is not reranked",
        )
    yield
    # Graceful shutdown: release the DB pool's and both Redis clients'
    # connections rather than letting the process drop them.
    await container.db_engine().dispose()
    await container.cache_provider().close()
    await container.rate_limiter().close()
    await container.job_queue().close()
    await container.search_index().close()


def set_api_version(version: str = "v1") -> str:
    return f"/api/{version}"


app = FastAPI(title="Kith", lifespan=lifespan)
register_exception_handlers(app)


app.add_middleware(
    CORSMiddleware,
    allow_origins=container.cors_settings().allowed_origins,
    allow_credentials=True,  # session cookie (ADR-0006)
    allow_methods=["*"],
    allow_headers=["*"],  # must cover X-Tenant-ID + Content-Type
)
app.include_router(auth_router, prefix=set_api_version())
app.include_router(me_router, prefix=set_api_version())
app.include_router(tenants_router, prefix=set_api_version())
app.include_router(users_router, prefix=set_api_version())
app.include_router(uploads_router, prefix=set_api_version())
app.include_router(library_router, prefix=set_api_version())
app.include_router(search_router, prefix=set_api_version())
app.include_router(credits_router, prefix=set_api_version())


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
