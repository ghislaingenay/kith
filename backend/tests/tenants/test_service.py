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
        self.pending_memberships: list[PendingMembership] = []
        self.commits = 0

    async def acquire_user_tenant_lock(self, user_id):
        self.locks_acquired.append(user_id)

    async def provision_default_membership(self, *, user_id, email, first_name=None):
        self.provisioned.append(
            {"user_id": user_id, "email": email, "first_name": first_name}
        )
        return TenantMembership(
            tenant_id=uuid.uuid4(), user_id=user_id, role=Role.OWNER
        )

    async def commit(self):
        self.commits += 1

    async def create_tenant(self, *, user_id, name):
        self.created.append({"user_id": user_id, "name": name})
        membership = TenantMembership(
            tenant_id=uuid.uuid4(), user_id=user_id, role=Role.OWNER
        )
        return membership, name, f"{name.lower()}-slug", Role.OWNER

    async def list_active_membership_details(self, user_id):
        return [row for row in self.membership_details if row[0].user_id == user_id]

    async def list_pending_memberships(self, email):
        return [p for p in self.pending_memberships if p.email == email]

    async def activate_pending_memberships(self, *, user_id, email, tenant_ids):
        self.activation_calls.append(
            {"user_id": user_id, "email": email, "tenant_ids": list(tenant_ids)}
        )
        return []


class FakeCreditsService:
    """Records each grant with how many commits the repository had made by
    then, so a test can tell whether the grant landed before the commit."""

    def __init__(self, repository: FakeTenantsRepository | None = None) -> None:
        self.repository = repository
        self.granted: list[tuple[uuid.UUID, int | None]] = []

    async def grant_starting_credits(self, tenant_id):
        commits = self.repository.commits if self.repository else None
        self.granted.append((tenant_id, commits))


class TestListMyMemberships:
    async def test_maps_repository_rows_to_summaries(self) -> None:
        repo = FakeTenantsRepository()
        user_id = uuid.uuid4()
        membership = TenantMembership(
            tenant_id=uuid.uuid4(), user_id=user_id, role=Role.OWNER
        )
        repo.membership_details.append((membership, "Acme Inc", "acme-inc", Role.OWNER))
        service = TenantsService(repo, FakeCreditsService())

        summaries = await service.list_my_memberships(user_id)

        assert len(summaries) == 1
        assert summaries[0].tenant_name == "Acme Inc"
        assert summaries[0].tenant_slug == "acme-inc"
        assert summaries[0].role == Role.OWNER

    async def test_returns_empty_list_for_no_memberships(self) -> None:
        service = TenantsService(FakeTenantsRepository(), FakeCreditsService())

        summaries = await service.list_my_memberships(uuid.uuid4())

        assert summaries == []


class TestCreateTenant:
    async def test_delegates_to_repository_and_maps_to_summary(self) -> None:
        repo = FakeTenantsRepository()
        service = TenantsService(repo, FakeCreditsService())
        user_id = uuid.uuid4()

        summary = await service.create_tenant(user_id=user_id, name="Acme")

        assert repo.created == [{"user_id": user_id, "name": "Acme"}]
        assert summary.tenant_name == "Acme"
        assert summary.tenant_slug == "acme-slug"
        assert summary.role == Role.OWNER
        assert repo.locks_acquired == [user_id]

    async def test_grants_starting_credits_to_the_new_tenant_before_committing(
        self,
    ) -> None:
        repo = FakeTenantsRepository()
        credits_service = FakeCreditsService(repo)
        service = TenantsService(repo, credits_service)

        summary = await service.create_tenant(user_id=uuid.uuid4(), name="Acme")

        assert credits_service.granted == [(summary.tenant_id, 0)]
        assert repo.commits == 1

    async def test_raises_when_user_already_has_an_active_membership(self) -> None:
        repo = FakeTenantsRepository()
        user_id = uuid.uuid4()
        existing_membership = TenantMembership(
            tenant_id=uuid.uuid4(), user_id=user_id, role=Role.OWNER
        )
        repo.membership_details.append(
            (existing_membership, "Acme Inc", "acme-inc", Role.OWNER)
        )
        credits_service = FakeCreditsService(repo)
        service = TenantsService(repo, credits_service)

        with pytest.raises(TenantAlreadyExistsError):
            await service.create_tenant(user_id=user_id, name="Another Co")

        assert repo.created == []
        assert credits_service.granted == []
        assert repo.commits == 0

    async def test_raises_when_user_has_a_non_owner_active_membership(self) -> None:
        repo = FakeTenantsRepository()
        user_id = uuid.uuid4()
        existing_membership = TenantMembership(
            tenant_id=uuid.uuid4(), user_id=user_id, role=Role.MEMBER
        )
        repo.membership_details.append(
            (existing_membership, "Acme Inc", "acme-inc", Role.MEMBER)
        )
        service = TenantsService(repo, FakeCreditsService())

        with pytest.raises(TenantAlreadyExistsError):
            await service.create_tenant(user_id=user_id, name="Another Co")

        assert repo.created == []


class TestProvisionDefaultMembership:
    async def test_delegates_to_repository(self) -> None:
        repo = FakeTenantsRepository()
        service = TenantsService(repo, FakeCreditsService())
        user_id = uuid.uuid4()

        await service.provision_default_membership(
            user_id=user_id, email="a@example.com", first_name="A"
        )

        assert repo.provisioned == [
            {"user_id": user_id, "email": "a@example.com", "first_name": "A"}
        ]


class TestActivatePendingMemberships:
    async def test_activates_every_listed_tenant_in_a_single_repository_call(
        self,
    ) -> None:
        """One call, not one per row: the repository closes all of them in
        one transaction so a failure can't leave the email half-activated."""
        repo = FakeTenantsRepository()
        user_id = uuid.uuid4()
        first_tenant, second_tenant = uuid.uuid4(), uuid.uuid4()
        repo.pending_memberships = [
            PendingMembership(
                tenant_id=first_tenant, email="dana@example.com", role=Role.ADMIN
            ),
            PendingMembership(
                tenant_id=second_tenant, email="dana@example.com", role=Role.VIEWER
            ),
        ]
        service = TenantsService(repo, FakeCreditsService())

        await service.activate_pending_memberships(
            user_id=user_id, email="dana@example.com"
        )

        assert repo.activation_calls == [
            {
                "user_id": user_id,
                "email": "dana@example.com",
                "tenant_ids": [first_tenant, second_tenant],
            }
        ]

    async def test_does_not_call_the_repository_when_nothing_is_pending(self) -> None:
        repo = FakeTenantsRepository()
        service = TenantsService(repo, FakeCreditsService())

        await service.activate_pending_memberships(
            user_id=uuid.uuid4(), email="nobody@example.com"
        )

        assert repo.activation_calls == []
