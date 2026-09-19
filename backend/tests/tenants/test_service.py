"""Unit tests for the tenants domain service layer — no DB."""

import uuid

import pytest
from tenants.exceptions import TenantAlreadyExistsError
from tenants.models import PendingMembership, TenantMembership
from tenants.permissions import Role
from tenants.service import TenantsService


class FakeTenantsRepository:
    """In-memory stand-in for TenantsRepository, matching its async interface."""

    def __init__(self) -> None:
        self.membership_details: list[tuple[TenantMembership, str, str, Role]] = []
        self.provisioned: list[dict] = []
        self.created: list[dict] = []
        self.locks_acquired: list[uuid.UUID] = []
        self.activation_calls: list[dict] = []
        self.next_activated: TenantMembership | None = None
        self.next_earliest_pending: PendingMembership | None = None

    async def acquire_user_tenant_lock(self, user_id):
        self.locks_acquired.append(user_id)

    async def provision_default_membership(self, *, user_id, email, first_name=None):
        self.provisioned.append(
            {"user_id": user_id, "email": email, "first_name": first_name}
        )
        return TenantMembership(
            tenant_id=uuid.uuid4(), user_id=user_id, role=Role.OWNER
        )

    async def create_tenant(self, *, user_id, name):
        self.created.append({"user_id": user_id, "name": name})
        membership = TenantMembership(
            tenant_id=uuid.uuid4(), user_id=user_id, role=Role.OWNER
        )
        return membership, name, f"{name.lower()}-slug", Role.OWNER

    async def list_active_membership_details(self, user_id):
        return [row for row in self.membership_details if row[0].user_id == user_id]

    async def get_earliest_pending_membership(self, email):
        return self.next_earliest_pending

    async def activate_pending_membership(self, *, user_id, tenant_id, email):
        self.activation_calls.append(
            {"user_id": user_id, "tenant_id": tenant_id, "email": email}
        )
        return self.next_activated


class TestListMyMemberships:
    async def test_maps_repository_rows_to_summaries(self) -> None:
        repo = FakeTenantsRepository()
        user_id = uuid.uuid4()
        membership = TenantMembership(
            tenant_id=uuid.uuid4(), user_id=user_id, role=Role.OWNER
        )
        repo.membership_details.append((membership, "Acme Inc", "acme-inc", Role.OWNER))
        service = TenantsService(repo)

        summaries = await service.list_my_memberships(user_id)

        assert len(summaries) == 1
        assert summaries[0].tenant_name == "Acme Inc"
        assert summaries[0].tenant_slug == "acme-inc"
        assert summaries[0].role == Role.OWNER

    async def test_returns_empty_list_for_no_memberships(self) -> None:
        service = TenantsService(FakeTenantsRepository())

        summaries = await service.list_my_memberships(uuid.uuid4())

        assert summaries == []


class TestCreateTenant:
    async def test_delegates_to_repository_and_maps_to_summary(self) -> None:
        repo = FakeTenantsRepository()
        service = TenantsService(repo)
        user_id = uuid.uuid4()

        summary = await service.create_tenant(user_id=user_id, name="Acme")

        assert repo.created == [{"user_id": user_id, "name": "Acme"}]
        assert summary.tenant_name == "Acme"
        assert summary.tenant_slug == "acme-slug"
        assert summary.role == Role.OWNER
        assert repo.locks_acquired == [user_id]

    async def test_raises_when_user_already_has_an_active_membership(self) -> None:
        repo = FakeTenantsRepository()
        user_id = uuid.uuid4()
        existing_membership = TenantMembership(
            tenant_id=uuid.uuid4(), user_id=user_id, role=Role.OWNER
        )
        repo.membership_details.append(
            (existing_membership, "Acme Inc", "acme-inc", Role.OWNER)
        )
        service = TenantsService(repo)

        with pytest.raises(TenantAlreadyExistsError):
            await service.create_tenant(user_id=user_id, name="Another Co")

        assert repo.created == []

    async def test_raises_when_user_has_a_non_owner_active_membership(self) -> None:
        repo = FakeTenantsRepository()
        user_id = uuid.uuid4()
        existing_membership = TenantMembership(
            tenant_id=uuid.uuid4(), user_id=user_id, role=Role.MEMBER
        )
        repo.membership_details.append(
            (existing_membership, "Acme Inc", "acme-inc", Role.MEMBER)
        )
        service = TenantsService(repo)

        with pytest.raises(TenantAlreadyExistsError):
            await service.create_tenant(user_id=user_id, name="Another Co")

        assert repo.created == []


class TestProvisionDefaultMembership:
    async def test_delegates_to_repository(self) -> None:
        repo = FakeTenantsRepository()
        service = TenantsService(repo)
        user_id = uuid.uuid4()

        await service.provision_default_membership(
            user_id=user_id, email="a@example.com", first_name="A"
        )

        assert repo.provisioned == [
            {"user_id": user_id, "email": "a@example.com", "first_name": "A"}
        ]


class TestActivatePendingMembership:
    async def test_activates_at_the_earliest_pending_membership_s_tenant(self) -> None:
        repo = FakeTenantsRepository()
        tenant_id = uuid.uuid4()
        repo.next_earliest_pending = PendingMembership(
            tenant_id=tenant_id, email="a@example.com", role=Role.MEMBER
        )
        service = TenantsService(repo)
        user_id = uuid.uuid4()

        await service.activate_pending_membership(user_id=user_id, email="a@example.com")

        assert repo.activation_calls == [
            {"user_id": user_id, "tenant_id": tenant_id, "email": "a@example.com"}
        ]

    async def test_does_nothing_when_there_is_no_pending_membership(self) -> None:
        repo = FakeTenantsRepository()
        repo.next_earliest_pending = None
        service = TenantsService(repo)
        user_id = uuid.uuid4()

        await service.activate_pending_membership(user_id=user_id, email="a@example.com")

        assert repo.activation_calls == []
