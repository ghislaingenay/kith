"""Authentication domain exceptions."""


class AuthenticationError(Exception):
    """Raised when a request is not authenticated."""


class MagicLinkTokenInvalidError(Exception):
    """Raised when a magic-link token can't be redeemed — deliberately one
    exception for "missing", "expired", and "already used": `CacheProvider`
    can't distinguish a key that never existed from one that expired from
    one this same call just deleted, and telling a visitor which applies
    would need state this design doesn't keep."""