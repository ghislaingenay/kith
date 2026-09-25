"""arq-backed `JobQueue`."""

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from core.jobs.provider import JobQueue


class ArqJobQueue(JobQueue):
    """Opens its Redis pool on first use, so building the queue at startup
    needs no network and an unreachable Redis fails the enqueue, not boot."""

    def __init__(self, redis_settings: RedisSettings) -> None:
        self._redis_settings = redis_settings
        self._pool: ArqRedis | None = None

    async def enqueue(
        self,
        queue: str,
        function: str,
        payload: dict[str, str],
        *,
        job_id: str,
    ) -> None:
        if self._pool is None:
            self._pool = await create_pool(self._redis_settings)
        await self._pool.enqueue_job(
            function, _job_id=job_id, _queue_name=queue, **payload
        )

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.aclose()
