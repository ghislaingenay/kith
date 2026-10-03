"""Every state transition of the in-house circuit breaker (ADR-0011), driven
by an injected clock so no test sleeps."""

import asyncio

import pytest
import structlog
from core.circuit_breaker.breaker import CircuitBreaker
from core.circuit_breaker.exceptions import CircuitOpenError


class _StoreDown(Exception):
    pass


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class _Store:
    """A search call that fails while `down` and counts how often it ran."""

    def __init__(self) -> None:
        self.down = False
        self.calls = 0

    async def call(self) -> str:
        self.calls += 1
        if self.down:
            raise _StoreDown
        return "ok"


@pytest.fixture
def clock() -> _Clock:
    return _Clock()


@pytest.fixture
def breaker(clock: _Clock) -> CircuitBreaker:
    return CircuitBreaker(
        name="test",
        failure_threshold=5,
        reset_timeout_seconds=30,
        failure_types=(_StoreDown,),
        clock=clock,
    )


@pytest.fixture
def store() -> _Store:
    return _Store()


async def _fail(breaker: CircuitBreaker, store: _Store, times: int) -> None:
    store.down = True
    for _ in range(times):
        with pytest.raises(_StoreDown):
            await breaker.call(store.call)


async def test_a_closed_breaker_passes_calls_through(
    breaker: CircuitBreaker, store: _Store
) -> None:
    assert await breaker.call(store.call) == "ok"
    assert store.calls == 1


async def test_four_failures_leave_it_closed(
    breaker: CircuitBreaker, store: _Store
) -> None:
    await _fail(breaker, store, 4)

    store.down = False
    assert await breaker.call(store.call) == "ok"


async def test_a_success_resets_the_failure_count(
    breaker: CircuitBreaker, store: _Store
) -> None:
    await _fail(breaker, store, 4)
    store.down = False
    await breaker.call(store.call)

    await _fail(breaker, store, 4)

    store.down = False
    assert await breaker.call(store.call) == "ok"


async def test_five_consecutive_failures_open_it_and_calls_fail_fast(
    breaker: CircuitBreaker, store: _Store
) -> None:
    await _fail(breaker, store, 5)
    calls_before = store.calls

    with pytest.raises(CircuitOpenError):
        await breaker.call(store.call)

    assert store.calls == calls_before


async def test_it_stays_open_until_the_timeout_has_passed(
    breaker: CircuitBreaker, store: _Store, clock: _Clock
) -> None:
    await _fail(breaker, store, 5)
    clock.now += 29.9

    with pytest.raises(CircuitOpenError):
        await breaker.call(store.call)


async def test_after_the_timeout_one_probe_goes_through_and_a_success_closes_it(
    breaker: CircuitBreaker, store: _Store, clock: _Clock
) -> None:
    await _fail(breaker, store, 5)
    clock.now += 30
    store.down = False

    assert await breaker.call(store.call) == "ok"
    assert await breaker.call(store.call) == "ok"


async def test_a_failed_probe_reopens_it_for_another_timeout(
    breaker: CircuitBreaker, store: _Store, clock: _Clock
) -> None:
    await _fail(breaker, store, 5)
    clock.now += 30
    await _fail(breaker, store, 1)
    calls_before = store.calls

    with pytest.raises(CircuitOpenError):
        await breaker.call(store.call)
    assert store.calls == calls_before

    clock.now += 30
    store.down = False
    assert await breaker.call(store.call) == "ok"


async def test_only_one_probe_is_allowed_while_it_is_in_flight(
    breaker: CircuitBreaker, store: _Store, clock: _Clock
) -> None:
    await _fail(breaker, store, 5)
    clock.now += 30

    async def probe_that_triggers_a_second_call() -> str:
        with pytest.raises(CircuitOpenError):
            await breaker.call(store.call)
        return "probe done"

    assert await breaker.call(probe_that_triggers_a_second_call) == "probe done"


async def test_a_failure_of_another_type_does_not_count(
    breaker: CircuitBreaker,
) -> None:
    async def bug() -> None:
        raise ValueError

    for _ in range(10):
        with pytest.raises(ValueError):
            await breaker.call(bug)

    async def fine() -> str:
        return "ok"

    assert await breaker.call(fine) == "ok"


async def test_a_probe_that_dies_of_another_error_leaves_it_open_not_wedged(
    breaker: CircuitBreaker, store: _Store, clock: _Clock
) -> None:
    await _fail(breaker, store, 5)
    clock.now += 30

    async def bug() -> None:
        raise ValueError

    with pytest.raises(ValueError):
        await breaker.call(bug)
    with pytest.raises(CircuitOpenError):
        await breaker.call(store.call)

    clock.now += 30
    store.down = False
    assert await breaker.call(store.call) == "ok"


async def test_opening_half_opening_and_closing_are_each_logged(
    breaker: CircuitBreaker, store: _Store, clock: _Clock
) -> None:
    with structlog.testing.capture_logs() as logs:
        await _fail(breaker, store, 5)
        clock.now += 30
        store.down = False
        await breaker.call(store.call)

    changes = [(log["previous_state"], log["state"]) for log in logs]
    assert changes == [
        ("closed", "open"),
        ("open", "half_open"),
        ("half_open", "closed"),
    ]
    assert all(log["breaker"] == "test" for log in logs)
    assert logs[0]["log_level"] == "warning"


async def test_a_slow_call_that_succeeds_after_it_opened_does_not_close_it(
    breaker: CircuitBreaker, store: _Store
) -> None:
    release = asyncio.Event()

    async def slow_success() -> str:
        await release.wait()
        return "ok"

    slow_call = asyncio.create_task(breaker.call(slow_success))
    await asyncio.sleep(0)
    await _fail(breaker, store, 5)

    release.set()
    assert await slow_call == "ok"

    with pytest.raises(CircuitOpenError):
        await breaker.call(store.call)


async def test_a_slow_call_that_fails_during_the_probe_is_not_the_probes_verdict(
    breaker: CircuitBreaker, store: _Store, clock: _Clock
) -> None:
    release = asyncio.Event()

    async def slow_failure() -> None:
        await release.wait()
        raise _StoreDown

    slow_call = asyncio.create_task(breaker.call(slow_failure))
    await asyncio.sleep(0)
    await _fail(breaker, store, 5)
    clock.now += 30
    store.down = False

    probe_gate = asyncio.Event()

    async def probe() -> str:
        await probe_gate.wait()
        return "ok"

    probe_call = asyncio.create_task(breaker.call(probe))
    await asyncio.sleep(0)
    release.set()
    with pytest.raises(_StoreDown):
        await slow_call
    probe_gate.set()

    assert await probe_call == "ok"
    assert await breaker.call(store.call) == "ok"
