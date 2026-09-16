"""A fake `AsyncSession`/`Result` double for unit-testing repositories
without a real database.

This is deliberately a *stub*, not a SQL engine: each test scripts the
`Result` a given `execute()` call should return, then asserts on the
repository's return value and on what the fake session recorded (statements
executed, objects added, whether commit/refresh happened). It supports
`async with session_factory() as session:` the same way
`async_sessionmaker` does, so it also works as a scripted `session_factory`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


class FakeScalars:
    """Stands in for the object returned by `Result.scalars()`."""

    def __init__(self, items: Sequence[Any]) -> None:
        self._items = list(items)

    def all(self) -> list[Any]:
        return list(self._items)

    def first(self) -> Any | None:
        return self._items[0] if self._items else None


class FakeResult:
    """Stands in for the `Result` returned by `AsyncSession.execute()`."""

    def __init__(
        self,
        *,
        scalar: Any | None = None,
        scalars_list: Sequence[Any] | None = None,
        rows: Sequence[Any] | None = None,
    ) -> None:
        self._scalar = scalar
        self._scalars_list = scalars_list or []
        self._rows = rows or []

    def scalar_one_or_none(self) -> Any | None:
        return self._scalar

    def scalars(self) -> FakeScalars:
        return FakeScalars(self._scalars_list)

    def all(self) -> list[Any]:
        return list(self._rows)


class FakeAsyncSession:
    """A fake DB session: no SQL is ever run, `execute()` just returns the
    next scripted `FakeResult` (or an empty one if none were scripted).

    Usable both directly (`FakeAsyncSession(execute_results=[...])`) and via
    `async with`, so a zero-arg factory (`lambda: FakeAsyncSession()`) can
    stand in for `async_sessionmaker`.
    """

    def __init__(
        self,
        *,
        execute_results: Sequence[FakeResult] | None = None,
        commit_side_effects: Sequence[BaseException | None] | None = None,
    ) -> None:
        self._execute_results = list(execute_results or [])
        # Scripted per-call outcomes for `commit()`: `None` commits normally,
        # an exception instance is raised instead (e.g. a unique-constraint
        # race modeled as `IntegrityError(...)`).
        self._commit_side_effects = list(commit_side_effects or [])
        self.executed_statements: list[Any] = []
        self.added: list[Any] = []
        self.commit_count = 0
        self.rollback_count = 0
        self.refreshed: list[Any] = []
        self.flush_count = 0

    async def execute(self, statement: Any) -> FakeResult:
        self.executed_statements.append(statement)
        if self._execute_results:
            return self._execute_results.pop(0)
        return FakeResult()

    def add(self, instance: Any) -> None:
        self.added.append(instance)

    async def commit(self) -> None:
        self.commit_count += 1
        if self._commit_side_effects:
            effect = self._commit_side_effects.pop(0)
            if effect is not None:
                raise effect

    async def rollback(self) -> None:
        self.rollback_count += 1

    async def refresh(self, instance: Any) -> None:
        self.refreshed.append(instance)

    async def flush(self) -> None:
        self.flush_count += 1

    async def __aenter__(self) -> FakeAsyncSession:
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        return False
