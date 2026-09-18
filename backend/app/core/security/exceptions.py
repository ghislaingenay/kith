"""Exceptions for cross-domain HTTP security checks."""


class OriginNotAllowedError(Exception):
    """Raised when a state-changing request's `Origin` header isn't in the
    configured allow-list (ADR-0006's CSRF mitigation: `SameSite=Lax` plus
    this check). Mapped to HTTP 403 at the API boundary."""

    def __init__(self, origin: str) -> None:
        self.origin = origin
        super().__init__(f"Origin '{origin}' is not allowed.")
