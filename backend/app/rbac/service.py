import asyncio
import json
from collections.abc import Callable
from datetime import timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from core.cache.provider import CacheProvider
from core.logging import setup_logger
from rbac.config import PERMISSIONS_CACHE_KEY, ROLE_CACHE_TTL, ROLES_CACHE_KEY
from rbac.exceptions import CacheLoad
from rbac.models import Permission, Role
from rbac.repository import PermissionRepository, RoleRepository
from rbac.schemas import PermissionResponse, RoleResponse

logger = setup_logger(__name__)

type LoadedFromCache = bool


class RoleRepositoryProtocol(Protocol):
    async def get_all_roles(self, with_permissions: bool = False) -> list[Role]:
        ...


class PermissionRepositoryProtocol(Protocol):
    async def get_all_permissions(self) -> list[Permission]:
        ...


RoleRepositoryFactory = Callable[[AsyncSession], RoleRepositoryProtocol]
PermissionRepositoryFactory = Callable[[AsyncSession], PermissionRepositoryProtocol]


class RolePermissionCacheService:
    """
    Service class for managing the in-memory cache of roles and permissions.
    """

    def __init__(
        self,
        *,
        session_factory: Callable[[], AsyncSession],
        cache_provider: CacheProvider,
        role_repository_factory: RoleRepositoryFactory = RoleRepository,
        permission_repository_factory: PermissionRepositoryFactory = PermissionRepository,
        ttl: timedelta = ROLE_CACHE_TTL,
    ):
        # `refresh()` opens a brand-new session per call (this service is a
        # long-lived singleton refreshed on an interval, not a per-request
        # object), so repositories can't be handed in as ready-made instances
        # bound to one session — they'd outlive it. Factories let a fresh
        # repository be built against each fresh session instead.
        self._session_factory = session_factory
        self._cache_provider = cache_provider
        self._role_repository_factory = role_repository_factory
        self._permission_repository_factory = permission_repository_factory
        self._ttl = ttl

        self._lock = asyncio.Lock()  # Ensure thread-safe cache loading

        self._roles: list[RoleResponse] = []
        self._permissions: list[PermissionResponse] = []
        self._roles_by_name: dict[str, RoleResponse] = {}
        self._roles_by_id: dict[str, RoleResponse] = {}

    async def _try_load_from_redis(
        self,
    ) -> tuple[list[RoleResponse], list[PermissionResponse], LoadedFromCache]:
        if not self._cache_provider:
            return [], [], False

        try:
            roles_raw, perms_raw = await asyncio.gather(
                self._cache_provider.get(ROLES_CACHE_KEY),
                self._cache_provider.get(PERMISSIONS_CACHE_KEY),
            )

            if not roles_raw or not perms_raw:
                return [], [], False

            try:
                roles = [RoleResponse(**r) for r in json.loads(roles_raw)]
                permissions = [PermissionResponse(**p) for p in json.loads(perms_raw)]
            except (json.JSONDecodeError, TypeError):
                logger.warning(
                    "Failed to decode roles or permissions from cache", exc_info=True
                )
                return [], [], False

            return roles, permissions, True

        except Exception:
            logger.warning(
                "Failed to load roles or permissions from cache", exc_info=True
            )
            return [], [], False

    async def _write_through(
        self, roles: list[RoleResponse], permissions: list[PermissionResponse]
    ) -> None:
        if not self._cache_provider:
            return

        ttl_seconds = int(self._ttl.total_seconds())

        try:
            roles_json = json.dumps([r.model_dump(mode="json") for r in roles])
            await self._cache_provider.set(ROLES_CACHE_KEY, roles_json, ttl_seconds)
        except Exception as e:
            logger.warning(
                "rbac: failed to write role cache to redis key=%s error=%s",
                ROLES_CACHE_KEY,
                str(e),
            )

        try:
            perms_json = json.dumps([p.model_dump(mode="json") for p in permissions])
            await self._cache_provider.set(
                PERMISSIONS_CACHE_KEY, perms_json, ttl_seconds
            )
        except Exception as e:
            logger.warning(
                "rbac: failed to write permission cache to redis key=%s error=%s",
                PERMISSIONS_CACHE_KEY,
                str(e),
            )

    async def _load_from_postgres(
        self,
    ) -> tuple[list[RoleResponse], list[PermissionResponse]]:
        try:
            async with self._session_factory() as session:
                role_repository = self._role_repository_factory(session)
                permission_repository = self._permission_repository_factory(session)
                roles = await self._load_roles(role_repository)
                permissions = await self._load_permissions(permission_repository)
                return roles, permissions
        except Exception as e:
            raise CacheLoad(str(e)) from e

    async def _load_roles(
        self, role_repository: RoleRepositoryProtocol
    ) -> list[RoleResponse]:
        db_roles = await role_repository.get_all_roles(with_permissions=True)

        return [
            RoleResponse(
                id=str(r.id),
                name=r.name,
                display_name=r.display_name,
                description=r.description,
                is_system_role=r.is_system_role,
                permissions=[p.name for p in r.permissions],
            )
            for r in db_roles
        ]

    async def _load_permissions(
        self, permission_repository: PermissionRepositoryProtocol
    ) -> list[PermissionResponse]:
        db_perms = await permission_repository.get_all_permissions()

        return [
            PermissionResponse(
                id=str(p.id),
                name=p.name,
                resource=p.resource,
                action=p.action,
                description=p.description,
            )
            for p in db_perms
        ]

    async def _set_state(
        self, roles: list[RoleResponse], permissions: list[PermissionResponse]
    ) -> None:
        roles_by_name = {r.name: r for r in roles}
        roles_by_id = {r.id: r for r in roles}

        async with self._lock:
            self._roles = roles
            self._roles_by_name = roles_by_name
            self._roles_by_id = roles_by_id
            self._permissions = permissions

    async def refresh(self) -> None:
        roles, permissions = await self._load_from_postgres()
        await self._set_state(roles, permissions)
        await self._write_through(roles, permissions)
        logger.info(
            "rbac: refreshed role cache roles=%d permissions=%d",
            len(roles),
            len(permissions),
        )

    async def get_role(self, name: str) -> tuple[RoleResponse | None, bool]:
        async with self._lock:
            role = self._roles_by_name.get(name)
            return role, role is not None

    async def get_role_by_id(self, role_id: UUID) -> tuple[RoleResponse | None, bool]:
        async with self._lock:
            role = self._roles_by_id.get(str(role_id))
            return role, role is not None

    async def all(self) -> list[RoleResponse]:
        async with self._lock:
            return list(self._roles)

    async def all_permissions(self) -> list[PermissionResponse]:
        async with self._lock:
            return list(self._permissions)
