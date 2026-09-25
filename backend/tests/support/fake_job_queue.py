"""A `JobQueue` stand-in that records what was enqueued."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EnqueuedJob:
    queue: str
    function: str
    payload: dict[str, str]
    job_id: str


class FakeJobQueue:
    def __init__(self) -> None:
        self.jobs: list[EnqueuedJob] = []

    async def enqueue(
        self, queue: str, function: str, payload: dict[str, str], *, job_id: str
    ) -> None:
        self.jobs.append(EnqueuedJob(queue, function, payload, job_id))

    async def close(self) -> None:
        return None
