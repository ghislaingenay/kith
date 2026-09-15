"""Backfill default roles and permissions.

Idempotent: safe to re-run. Run with `PYTHONPATH=src python -m scripts.seed_rbac`.
"""

import asyncio

from sqlalchemy import select

from core.database import DatabaseSettings, create_engine, create_session_factory
from rbac.models import Permission, Role

_RESOURCES = ("users", "tenants", "roles", "permissions")
_ACTIONS = ("read", "create", "update", "delete")

_PERMISSIONS = [
    {
        "name": f"{resource}:{action}",
        "resource": resource,
        "action": action,
        "description": f"Can {action} {resource}",
    }
    for resource in _RESOURCES
    for action in _ACTIONS
]

_ROLES = [
    {
        "name": "owner",
        "display_name": "Owner",
        "description": (
            "Full access within their own tenant; assigned automatically to "
            "whoever provisions a tenant via solo signup."
        ),
        "is_system_role": True,
        "permission_names": [p["name"] for p in _PERMISSIONS],
    },
    {
        "name": "admin",
        "display_name": "Admin",
        "description": "Full access to every resource.",
        "is_system_role": True,
        "permission_names": [p["name"] for p in _PERMISSIONS],
    },
    {
        "name": "manager",
        "display_name": "Manager",
        "description": "Can read and update users.",
        "is_system_role": True,
        "permission_names": ["users:read", "users:update"],
    },
    {
        "name": "viewer",
        "display_name": "Viewer",
        "description": "Read-only access to every resource.",
        "is_system_role": True,
        "permission_names": [f"{resource}:read" for resource in _RESOURCES],
    },
]


async def seed_rbac() -> None:
    settings = DatabaseSettings()
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)

    inserted_permissions = 0
    inserted_roles = 0

    async with session_factory() as session:
        permissions_by_name: dict[str, Permission] = {}

        for data in _PERMISSIONS:
            existing = await session.scalar(
                select(Permission).where(Permission.name == data["name"])
            )
            if existing is not None:
                permissions_by_name[data["name"]] = existing
                continue

            permission = Permission(
                name=data["name"],
                resource=data["resource"],
                action=data["action"],
                description=data["description"],
            )
            session.add(permission)
            permissions_by_name[data["name"]] = permission
            inserted_permissions += 1

        await session.flush()

        for data in _ROLES:
            existing = await session.scalar(
                select(Role).where(Role.name == data["name"])
            )
            if existing is not None:
                continue

            role = Role(
                name=data["name"],
                display_name=data["display_name"],
                description=data["description"],
                is_system_role=data["is_system_role"],
                permissions=[
                    permissions_by_name[name] for name in data["permission_names"]
                ],
            )
            session.add(role)
            inserted_roles += 1

        await session.commit()

    await engine.dispose()

    print(
        f"Seeded {inserted_permissions} permission(s) and {inserted_roles} role(s) "
        f"(already present entries were left untouched)."
    )


if __name__ == "__main__":
    asyncio.run(seed_rbac())
