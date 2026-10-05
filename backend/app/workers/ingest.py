"""Entry point for the `worker-ingest` service (ADR-0005): an arq worker
consuming the `ingest` queue, run with `arq workers.ingest.WorkerSettings`.

Builds its own DI-wired dependencies independently of the FastAPI `app`
process — its own database engine/session and storage provider — matching
the container/lifespan composition pattern `main.py` establishes for `app`.
Low `max_jobs`, matching ADR-0005's "low max_jobs" for `worker-ingest`
versus `worker-tasks`. The `ProcessPoolExecutor` ADR-0005 also calls for is
deliberately deferred: there's no CPU-bound work to offload until #40 lands
real extraction."""

from collections.abc import Awaitable, Callable
from typing import ClassVar

from arq.connections import RedisSettings
from core.container import container
from core.logging import setup_logger
from core.migrations import warn_if_schema_out_of_date
from documents.embed import embed_document
from documents.ingest import ingest_document

# Must run before any other singleton, including `redis_settings` below:
# arq reads that class attribute to open its pool before `on_startup` ever
# runs, so logging can't wait for startup to be configured first.
container.logging_configured()

logger = setup_logger(__name__)


async def startup(ctx: dict) -> None:
    # Same eager-init rationale as `main.py`'s lifespan: fail fast on bad
    # config rather than on the first job. Built first so a missing
    # VOYAGE_API_KEY stops the worker before it does anything else.
    ctx["embedding_provider"] = container.embedding_provider()
    await warn_if_schema_out_of_date(container.db_engine())
    ctx["db_session_factory"] =container.db_session_factory()
    ctx["storage_provider"] = container.storage_provider()
    ctx["ingestion_settings"] = container.ingestion_settings()
    ctx["search_index"] = container.search_index()
    ctx["retry_handler"] = container.retry_handler()
    ctx["job_queue"] = container.job_queue()
    logger.info("worker_ingest_started")


async def shutdown(ctx: dict) -> None:
    await ctx["search_index"].close()
    await ctx["job_queue"].close()
    await container.db_engine().dispose()
    logger.info("worker_ingest_stopped")


class WorkerSettings:
    functions: ClassVar[list[Callable[..., Awaitable[None]]]] = [
        ingest_document,
        embed_document,
    ]
    queue_name = "ingest"
    redis_settings = RedisSettings.from_dsn(container.cache_settings().redis_url)
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 5
