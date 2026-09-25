"""Abstract interface for handing background work to a worker queue."""

from abc import ABC, abstractmethod


class JobQueue(ABC):
    """Enqueues jobs for the arq workers (ADR-0005)."""

    @abstractmethod
    async def enqueue(
        self,
        queue: str,
        function: str,
        payload: dict[str, str],
        *,
        job_id: str,
    ) -> None:
        """Enqueue `function` on the named `queue` with `payload` as its
        keyword arguments. A job whose `job_id` is already queued or
        running is not enqueued a second time."""

    @abstractmethod
    async def close(self) -> None:
        """Release any held connections. Called once during app shutdown."""
