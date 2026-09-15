"""Composition root: wires infrastructure singletons via dependency-injector."""

from dependency_injector import containers, providers

from core.cache.config import CacheSettings
from core.cors import CorsSettings
from core.cache.factory import CacheProviderFactory
from core.database import DatabaseSettings, create_engine, create_session_factory
from core.logging.config import LoggingSettings, configure_logging
from core.ratelimit.factory import RateLimiterFactory
from core.retry.config import RetrySettings
from core.retry.handler import RetryHandler
from core.storage.config import StorageSettings
from core.storage.factory import StorageProviderFactory
from rbac.service import RolePermissionCacheService


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

    database_settings = providers.Singleton(DatabaseSettings)

    # Same eager-init note as storage_provider: call `container.db_engine()` during
    # startup/lifespan so a bad DATABASE_URL fails fast instead of on first request.
    db_engine = providers.Singleton(create_engine, settings=database_settings)

    db_session_factory = providers.Singleton(create_session_factory, engine=db_engine)

    retry_settings = providers.Singleton(RetrySettings)

    retry_handler = providers.Singleton(RetryHandler, settings=retry_settings)

    # Holds process-wide in-memory state (cached roles/permissions, a lock)
    # refreshed on an interval — a singleton like the providers above, not a
    # per-request object. The app's startup/lifespan should call
    # `await container.role_permission_cache_service().refresh()` eagerly so
    # the cache is populated before the first request needs it.
    role_permission_cache_service = providers.Singleton(
        RolePermissionCacheService,
        session_factory=db_session_factory,
        cache_provider=cache_provider,
    )

    cors_settings = providers.Singleton(CorsSettings)


container = Container()
