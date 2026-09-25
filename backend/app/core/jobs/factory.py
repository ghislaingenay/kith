"""Factory for instantiating the job queue from configuration."""

from arq.connections import RedisSettings

from core.cache.config import CacheSettings
from core.jobs.arq_queue import ArqJobQueue
from core.jobs.provider import JobQueue


class JobQueueFactory:
    """Builds the arq job queue on the same Redis as `cache_provider`
    (`CacheSettings.redis_url`) rather than adding a second env var."""

    @staticmethod
    def create(settings: CacheSettings) -> JobQueue:
        return ArqJobQueue(RedisSettings.from_dsn(settings.redis_url))
