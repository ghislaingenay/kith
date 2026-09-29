from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from structlog.testing import capture_logs

from core import migrations
from core.migrations import warn_if_schema_out_of_date


class _FakeConnection:
    def __init__(self, current_revisions: list[str]) -> None:
        self._current_revisions = current_revisions

    async def run_sync(self, _fn) -> list[str]:
        return self._current_revisions


class _FakeEngine:
    def __init__(self, current_revisions: list[str]) -> None:
        self._connection = _FakeConnection(current_revisions)

    @asynccontextmanager
    async def connect(self):
        yield self._connection


@pytest.fixture
def head_revisions(monkeypatch) -> list[str]:
    heads = ["009"]
    monkeypatch.setattr(
        migrations.ScriptDirectory,
        "from_config",
        lambda _config: SimpleNamespace(get_heads=lambda: heads),
    )
    return heads


async def test_no_warning_when_database_is_at_head(head_revisions) -> None:
    with capture_logs() as logs:
        await warn_if_schema_out_of_date(_FakeEngine(["009"]))

    assert logs == []


async def test_warns_with_both_revisions_when_database_is_behind(
    head_revisions,
) -> None:
    with capture_logs() as logs:
        await warn_if_schema_out_of_date(_FakeEngine(["008"]))

    assert len(logs) == 1
    assert logs[0]["event"] == "db_schema_out_of_date"
    assert logs[0]["log_level"] == "warning"
    assert logs[0]["current_revisions"] == ["008"]
    assert logs[0]["head_revisions"] == ["009"]


async def test_warns_when_database_has_no_migrations_applied(head_revisions) -> None:
    with capture_logs() as logs:
        await warn_if_schema_out_of_date(_FakeEngine([]))

    assert logs[0]["event"] == "db_schema_out_of_date"
    assert logs[0]["current_revisions"] == []


async def test_a_failing_check_is_logged_and_never_raised(head_revisions) -> None:
    class _BrokenEngine:
        def connect(self):
            raise ConnectionError("database unreachable")

    with capture_logs() as logs:
        await warn_if_schema_out_of_date(_BrokenEngine())

    assert [log["event"] for log in logs] == ["db_schema_check_failed"]
