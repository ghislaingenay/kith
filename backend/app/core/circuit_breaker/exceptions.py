"""Exceptions for the circuit breaker."""


class CircuitOpenError(Exception):
    """The circuit breaker is open: the call failed fast without being
    attempted, and is not worth retrying."""

    def __init__(self) -> None:
        super().__init__("Circuit breaker is open; call not attempted.")
