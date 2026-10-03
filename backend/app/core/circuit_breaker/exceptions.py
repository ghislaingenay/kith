"""Exceptions for the circuit breaker."""


class CircuitOpenError(Exception):
    """The circuit breaker is open: the call failed fast without being
    attempted, and is not worth retrying. `service` is the name of the
    breaker, i.e. of the service it guards."""

    def __init__(self, service: str) -> None:
        self.service = service
        super().__init__(
            f"Circuit breaker for {service!r} is open; call not attempted."
        )
