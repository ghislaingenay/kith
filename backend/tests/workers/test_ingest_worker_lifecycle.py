"""`workers/ingest.py`'s startup and shutdown, which arq runs as a pair: it
calls shutdown even when startup raised part-way."""

import importlib
from types import ModuleType

import pytest
from pydantic import ValidationError


@pytest.fixture
def ingest_worker(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    # Importing the module reads REDIS_URL for arq's connection settings;
    # nothing connects to it here.
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("VOYAGE_API_KEY", "")
    return importlib.import_module("workers.ingest")


async def test_shutdown_after_a_startup_refused_for_a_missing_voyage_key_raises_nothing(
    ingest_worker: ModuleType,
) -> None:
    ctx: dict = {}
    with pytest.raises(ValidationError, match="VOYAGE_API_KEY"):
        await ingest_worker.startup(ctx)

    await ingest_worker.shutdown(ctx)
