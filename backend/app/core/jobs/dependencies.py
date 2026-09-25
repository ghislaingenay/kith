"""FastAPI dependency wiring for the jobs core module."""

from core.container import container
from core.jobs.provider import JobQueue


def get_job_queue() -> JobQueue:
    return container.job_queue()
