class CacheLoad(Exception):
    """
    Raised when roles or permissions could not be loaded
    from the database into the in-memory RoleCache at startup.
    """

    def __init__(self, reason: str | None = None):
        message = "failed to load roles/permissions"
        if reason:
            message = f"{message}: {reason}"
        super().__init__(message)
