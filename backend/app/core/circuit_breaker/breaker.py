"""A reusable circuit breaker for calls to an unreliable service, written
without a library. Closed it passes calls through; `failure_threshold`
consecutive failures open it, and calls then fail fast without reaching the
service. After `reset_timeout_seconds` one probe call is let through: its
success closes the breaker, its failure reopens it for another timeout.

Every state change is logged, with the breaker's `name`."""

import time
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import NoReturn

from core.circuit_breaker.exceptions import CircuitOpenError
from core.logging import setup_logger

logger = setup_logger(__name__)


class _State(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        *,
        name: str,
        failure_threshold: int,
        reset_timeout_seconds: float,
        failure_types: tuple[type[BaseException], ...],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._name = name
        self._failure_threshold = failure_threshold
        self._reset_timeout_seconds = reset_timeout_seconds
        self._failure_types = failure_types
        self._clock = clock
        self._state = _State.CLOSED
        self._consecutive_failures = 0
        self._opened_at = 0.0

    async def call[T](self, func: Callable[[], Awaitable[T]]) -> T:
        if self._state == _State.OPEN:
            if self._clock() - self._opened_at < self._reset_timeout_seconds:
                self._reject()
            self._transition(_State.HALF_OPEN)
        elif self._state == _State.HALF_OPEN:
            # The probe is still in flight: only one call is let through.
            self._reject()

        started_in = self._state
        try:
            result = await func()
        except self._failure_types:
            # A call that began while closed and ends after the breaker
            # opened is stale: it says nothing about the probe.
            if started_in == _State.HALF_OPEN or self._state == _State.CLOSED:
                self._record_failure()
            raise
        except BaseException:
            # Not a store failure (a bug, a cancellation): neither counts
            # against the service nor proves it healthy, but a probe that
            # never reported back must not wedge the breaker half open.
            if self._state == _State.HALF_OPEN:
                self._transition(_State.OPEN)
            raise
        # Only a call that began as the probe, or one that ends while closed,
        # speaks for the service; a stale success must not close an open
        # breaker without a probe.
        if started_in == _State.HALF_OPEN or self._state == _State.CLOSED:
            self._consecutive_failures = 0
            self._transition(_State.CLOSED)
        return result

    def _record_failure(self) -> None:
        self._consecutive_failures += 1
        if (
            self._state == _State.HALF_OPEN
            or self._consecutive_failures >= self._failure_threshold
        ):
            self._transition(_State.OPEN)

    def _reject(self) -> NoReturn:
        logger.warning(
            "circuit_breaker_call_rejected", breaker=self._name, state=self._state
        )
        raise CircuitOpenError(self._name)

    def _transition(self, new_state: _State) -> None:
        previous = self._state
        self._state = new_state
        if new_state == _State.OPEN:
            self._opened_at = self._clock()
        if previous == new_state:
            return
        log = logger.warning if new_state == _State.OPEN else logger.info
        log(
            "circuit_breaker_state_changed",
            breaker=self._name,
            previous_state=previous,
            state=new_state,
            consecutive_failures=self._consecutive_failures,
        )
