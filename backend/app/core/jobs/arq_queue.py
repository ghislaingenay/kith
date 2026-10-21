"""arq-backed `JobQueue`."""

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from core.jobs.provider import JobQueue

KEEP_RESULT_SECONDS = 0
"""For the workers' `keep_result`. arq refuses a job whose id has a kept
result, so keeping none is what lets a job id be queued again once its job
finished, as `JobQueue.enqueue` promises."""


class ArqJobQueue(JobQueue):
    """Opens its Redis pool on first use, so building the queue at startup
    needs no network and an unreachable Redis fails the enqueue, not boot."""

    def __init__(self, redis_settings: RedisSettings) -> None:
        self._redis_settings = redis_settings
        self._pool: ArqRedis | None = None

    async def _get_pool(self) -> ArqRedis:
        if self._pool is None:
            self._pool = await create_pool(self._redis_settings)
        return self._pool

    async def enqueue(
        self,
        queue: str,
        function: str,
        payload: dict[str, str],
        *,
        job_id: str,
    ) -> None:
        pool = await self._get_pool()
        await pool.enqueue_job(function, _job_id=job_id, _queue_name=queue, **payload)

    async def count_jobs(self, queue: str) -> int:
        # arq keeps a job in the queue's sorted set until it finishes, so the
        # set holds the running and retrying jobs as well as the waiting ones.
        pool = await self._get_pool()
        return await pool.zcard(queue)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.aclose()
