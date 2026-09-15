from pydantic import BaseModel


class RoleResponse(BaseModel):
    """API representation of a Role returned by GET /roles."""

    id: str
    name: str
    display_name: str
    description: str
    permissions: list[str]
    is_system_role: bool


class PermissionResponse(BaseModel):
    """API representation of a Permission returned by GET /permissions."""

    id: str
    name: str
    resource: str
    action: str
    description: str
