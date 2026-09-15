from collections import defaultdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from rbac.models import Permission, Role, RolePermission


class RoleRepository:
    """Repository class for managing Role entities."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_role_by_name(
        self, role_name: str, with_permissions: bool = False
    ) -> Role | None:
        """Fetch a role by its name."""
        stmt = select(Role).where(Role.name == role_name)
        if with_permissions:
            stmt = stmt.options(selectinload(Role.permissions))
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_all_roles(self, with_permissions: bool = False) -> list[Role]:
        """Fetch all roles."""
        stmt = select(Role).order_by(Role.name)
        if with_permissions:
            stmt = stmt.options(selectinload(Role.permissions))
        result = await self.session.execute(stmt)
        return result.scalars().all()


class PermissionRepository:
    """Repository class for managing Permission entities."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_permission_by_name(self, permission_name: str) -> Permission | None:
        """Fetch a permission by its name."""
        stmt = select(Permission).where(Permission.name == permission_name)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_all_permissions(self) -> list[Permission]:
        """Fetch all permissions."""
        stmt = select(Permission).order_by(Permission.resource, Permission.action)
        result = await self.session.execute(stmt)
        return result.scalars().all()


class RolePermissionRepository:
    """Repository class for managing RolePermission associations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_permissions_for_role(self, role_id: UUID) -> list[Permission]:
        """Fetch all permissions associated with a given role."""
        stmt = select(Permission).join(Role.permissions).where(Role.id == role_id)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_permission_names_by_role(self) -> dict[UUID, list[str]]:
        """Fetch permission names for every role, grouped by role id."""
        stmt = (
            select(RolePermission.role_id, Permission.name)
            .join(Permission, RolePermission.permission_id == Permission.id)
            .order_by(RolePermission.role_id, Permission.name)
        )
        result = await self.session.execute(stmt)

        by_role: dict[str, list[str]] = defaultdict(list)
        for role_id, perm_name in result.all():
            by_role[role_id].append(perm_name)

        return by_role
