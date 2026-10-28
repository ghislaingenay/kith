"""Domain exceptions for the load-test domain."""


class LoadTestDisabledError(Exception):
    """`LOAD_TEST_ENABLED` is not set, so this is not the load-test VPS."""


class InvalidLoadTestSizeError(Exception):
    """Tenants, Users and Credits must each be a whole number of at least 1."""


class NonReservedEmailDomainError(Exception):
    """Load Test Users only ever live on the reserved non-deliverable domain."""
