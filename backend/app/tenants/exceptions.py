"""Domain exceptions for the tenants domain. Mapped to HTTP at the router/app boundary."""


class TenantNotFound(Exception):
    """Raised when a tenant is not found in the database."""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        msg = f"Tenant '{tenant_id}' not found." if tenant_id else "Tenant not found."
        super().__init__(msg)


class InvalidLogoUploadError(Exception):
    """Raised when an uploaded tenant logo is the wrong content type or too
    large. Mapped to HTTP 422 at the API boundary."""


class OwnerRoleNotConfiguredError(Exception):
    """The 'owner' role is missing — run `scripts.seed_rbac` before any
    tenant can be provisioned or created."""


# This app consider only one tenant = one user
class TenantAlreadyExistsError(Exception):
    """Raised when the user already has an active tenant membership — this
    app enforces one active tenant per user, so no additional tenant can be
    created regardless of the requested name."""

    def __init__(self, name: str):
        self.name = name
        msg = (
            f"Cannot create tenant '{name}': you already belong to a tenant. "
            "Only one active tenant per user is allowed."
        )
        super().__init__(msg)
