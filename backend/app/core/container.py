"""Composition root: wires infrastructure singletons via dependency-injector."""

from dependency_injector import containers, providers

from core.circuit_breaker.breaker import CircuitBreaker
from core.circuit_breaker.config import CircuitBreakerSettings
from core.cache.config import CacheSettings
from core.cache.factory import CacheProviderFactory
from core.cors import CorsSettings
from core.database import DatabaseSettings, create_engine, create_session_factory
from core.embedding.config import EmbeddingSettings
from core.embedding.factory import EmbeddingProviderFactory
from core.jobs.factory import JobQueueFactory
from core.logging.config import LoggingSettings, configure_logging
from core.mail.config import MailSettings
from core.mail.factory import MailerFactory
from core.ratelimit.factory import RateLimiterFactory
from core.retry.config import RetrySettings
from core.retry.handler import RetryHandler
from core.search.config import SearchSettings
from core.search.exceptions import SearchUnavailableError
from core.search.factory import SearchIndexFactory
from core.storage.config import StorageSettings
from core.storage.factory import StorageProviderFactory
from documents.config import IngestionSettings, UploadSettings


def _configure_logging_once(settings: LoggingSettings) -> bool:
    # `providers.Singleton` only caches a truthy factory return value —
    # `configure_logging` itself returns `None`, which `dependency_injector`
    # treats as "not yet computed" and would re-invoke on every access
    # instead of once. This wrapper's `bool` return is what makes the
    # Singleton caching actually stick.
    configure_logging(settings)
    return True


class Container(containers.DeclarativeContainer):
    logging_settings = providers.Singleton(LoggingSettings)

    # `providers.Singleton` is lazy — it only runs on first access. The app's
    # startup/lifespan must call `container.logging_configured()` eagerly,
    # and before any other singleton, so structlog is configured before
    # anything else has a chance to log.
    logging_configured = providers.Singleton(
        _configure_logging_once, settings=logging_settings
    )

    storage_settings = providers.Singleton(StorageSettings)

    # `providers.Singleton` is lazy — it only runs on first access. The app's
    # startup/lifespan must call `container.storage_provider()` eagerly so
    # config errors surface early.
    storage_provider = providers.Singleton(
        StorageProviderFactory.create,
        settings=storage_settings,
    )

    cache_settings = providers.Singleton(CacheSettings)

    # Same eager-init note as storage_provider: call `container.cache_provider()`
    # during startup/lifespan so a bad REDIS_URL fails fast instead of on first request.
    cache_provider = providers.Singleton(
        CacheProviderFactory.create,
        settings=cache_settings,
    )

    # Same eager-init note as storage_provider/cache_provider: call
    # `container.rate_limiter()` during startup/lifespan so a bad REDIS_URL
    # fails fast instead of on first request.
    rate_limiter = providers.Singleton(
        RateLimiterFactory.create,
        settings=cache_settings,
    )

    # Same eager-init note as storage_provider/cache_provider: call
    # `container.job_queue()` during startup/lifespan. The Redis pool itself
    # opens on the first enqueue.
    job_queue = providers.Singleton(JobQueueFactory.create, settings=cache_settings)

    circuit_breaker_settings = providers.Singleton(CircuitBreakerSettings)

    # One breaker for the whole process, so every job and batch sees the same
    # state of the search store (ADR-0011).
    search_circuit_breaker = providers.Singleton(
        CircuitBreaker,
        name="search",
        failure_threshold=circuit_breaker_settings.provided.failure_threshold,
        reset_timeout_seconds=circuit_breaker_settings.provided.reset_timeout_seconds,
        failure_types=(SearchUnavailableError,),
    )

    search_settings = providers.Singleton(SearchSettings)

    # Same eager-init note as storage_provider: call `container.search_index()`
    # during startup/lifespan so a bad SEARCH_URL fails fast. The client
    # connects on first use.
    search_index = providers.Singleton(
        SearchIndexFactory.create,
        settings=search_settings,
        breaker=search_circuit_breaker,
    )

    embedding_settings = providers.Singleton(EmbeddingSettings)

    # Same eager-init note as storage_provider: call
    # `container.embedding_provider()` during the ingest worker's startup so a
    # missing VOYAGE_API_KEY fails fast instead of on the first embed job.
    embedding_provider = providers.Singleton(
        EmbeddingProviderFactory.create, settings=embedding_settings
    )

    upload_settings = providers.Singleton(UploadSettings)

    ingestion_settings = providers.Singleton(IngestionSettings)

    database_settings = providers.Singleton(DatabaseSettings)

    # Same eager-init note as storage_provider: call `container.db_engine()` during
    # startup/lifespan so a bad DATABASE_URL fails fast instead of on first request.
    db_engine = providers.Singleton(create_engine, settings=database_settings)

    db_session_factory = providers.Singleton(create_session_factory, engine=db_engine)

    retry_settings = providers.Singleton(RetrySettings)

    retry_handler = providers.Singleton(RetryHandler, settings=retry_settings)

    cors_settings = providers.Singleton(CorsSettings)

    mail_settings = providers.Singleton(MailSettings)

    # Same eager-init note as storage_provider/cache_provider: call
    # `container.mailer()` during startup/lifespan so missing SMTP config
    # fails fast instead of on first magic-link request.
    mailer = providers.Singleton(MailerFactory.create, settings=mail_settings)

container = Container()
