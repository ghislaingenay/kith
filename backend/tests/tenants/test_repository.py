"""Integration tests for TenantsRepository against a real Postgres. Requires
DATABASE_URL — skipped automatically otherwise (see conftest.py)."""

import uuid

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from tenants.permissions import Role
from tenants.repository import TenantsRepository
from users.models import User


async def _make_user(db_session: AsyncSession, email: str) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        email_verified=True,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


class TestProvisionDefaultMembership:
    async def test_creates_tenant_and_owner_membership(
        self, repository: TenantsRepository, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "dana@example.com")

        membership = await repository.provision_default_membership(
            user_id=user.id, email=user.email, first_name="Dana"
        )

        assert membership.user_id == user.id
        assert membership.role == Role.OWNER

    async def test_is_idempotent_for_a_retried_call(
        self, repository: TenantsRepository, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "eve@example.com")

        first = await repository.provision_default_membership(
            user_id=user.id, email=user.email, first_name="Eve"
        )
        second = await repository.provision_default_membership(
            user_id=user.id, email=user.email, first_name="Eve"
        )

        assert first.tenant_id == second.tenant_id


class TestListActiveMembershipDetails:
    async def test_joins_tenant_name_and_reads_role_from_the_row(
        self, repository: TenantsRepository, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "hank@example.com")
        await repository.provision_default_membership(
            user_id=user.id, email=user.email, first_name="Hank"
        )

        rows = await repository.list_active_membership_details(user.id)

        assert len(rows) == 1
        _, tenant_name, tenant_slug, role = rows[0]
        assert tenant_name == "Hank's organization"
        assert tenant_slug
        assert role == Role.OWNER


class TestCreateTenant:
    async def test_creates_tenant_and_owner_membership_with_supplied_name(
        self, repository: TenantsRepository, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "ivan@example.com")

        membership, tenant_name, tenant_slug, role = await repository.create_tenant(
            user_id=user.id, name="Ivan's Second Company"
        )

        assert membership.user_id == user.id
        assert membership.role == Role.OWNER
        assert tenant_name == "Ivan's Second Company"
        assert tenant_slug
        assert role == Role.OWNER

    async def test_two_calls_with_same_name_create_distinct_tenants(
        self, repository: TenantsRepository, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "jill@example.com")

        first, _, _, _ = await repository.create_tenant(user_id=user.id, name="Acme")
        second, _, _, _ = await repository.create_tenant(user_id=user.id, name="Acme")

        assert first.tenant_id != second.tenant_id


class TestGetActiveMembership:
    async def test_returns_membership_when_exists(
        self, repository: TenantsRepository, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "leo@example.com")
        created_membership = await repository.provision_default_membership(
            user_id=user.id, email=user.email, first_name="Leo"
        )

        found = await repository.get_active_membership(
            user_id=user.id, tenant_id=created_membership.tenant_id
        )

        assert found is not None
        assert found.user_id == user.id
        assert found.tenant_id == created_membership.tenant_id

    async def test_returns_none_when_membership_does_not_exist(
        self, repository: TenantsRepository, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "maria@example.com")

        found = await repository.get_active_membership(
            user_id=user.id, tenant_id=uuid.uuid4()
        )

        assert found is None

    async def test_returns_none_when_membership_is_deactivated(
        self, repository: TenantsRepository, db_session: AsyncSession
    ) -> None:
        from datetime import UTC, datetime
        from tenants.models import TenantMembership

        user = await _make_user(db_session, "nina@example.com")
        membership = await repository.provision_default_membership(
            user_id=user.id, email=user.email, first_name="Nina"
        )

        # Manually deactivate the membership
        from sqlalchemy import update as sa_update

        await db_session.execute(
            sa_update(TenantMembership)
            .where(
                TenantMembership.tenant_id == membership.tenant_id,
                TenantMembership.user_id == membership.user_id,
            )
            .values(deactivated_at=datetime.now(UTC))
        )
        await db_session.commit()

        found = await repository.get_active_membership(
            user_id=user.id, tenant_id=membership.tenant_id
        )

        assert found is None


class TestProvisionDefaultMembershipEdgeCases:
    async def test_tenant_name_uses_first_name_when_available(
        self, repository: TenantsRepository, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "oliver@example.com")

        await repository.provision_default_membership(
            user_id=user.id, email=user.email, first_name="Oliver"
        )

        rows = await repository.list_active_membership_details(user.id)
        _, tenant_name, _, _ = rows[0]
        assert tenant_name == "Oliver's organization"

    async def test_tenant_name_uses_email_prefix_when_no_first_name(
        self, repository: TenantsRepository, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "paula@example.com")

        await repository.provision_default_membership(
            user_id=user.id, email=user.email, first_name=None
        )

        rows = await repository.list_active_membership_details(user.id)
        _, tenant_name, _, _ = rows[0]
        assert tenant_name == "paula's organization"


class TestListActiveMembershipDetailsMultipleTenants:
    async def test_returns_all_memberships_for_user_in_multiple_tenants(
        self, repository: TenantsRepository, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "rachel@example.com")
        await repository.provision_default_membership(
            user_id=user.id, email=user.email, first_name="Rachel"
        )
        await repository.create_tenant(user_id=user.id, name="Rachel's Side Project")

        rows = await repository.list_active_membership_details(user.id)

        assert len(rows) == 2
        tenant_names = {row[1] for row in rows}
        assert "Rachel's organization" in tenant_names
        assert "Rachel's Side Project" in tenant_names

    async def test_excludes_deactivated_memberships_from_details(
        self, repository: TenantsRepository, db_session: AsyncSession
    ) -> None:
        from datetime import UTC, datetime
        from tenants.models import TenantMembership

        user = await _make_user(db_session, "sam@example.com")
        first_membership = await repository.provision_default_membership(
            user_id=user.id, email=user.email, first_name="Sam"
        )
        await repository.create_tenant(user_id=user.id, name="Sam's Active Company")

        # Deactivate the first membership
        from sqlalchemy import update as sa_update

        await db_session.execute(
            sa_update(TenantMembership)
            .where(
                TenantMembership.tenant_id == first_membership.tenant_id,
                TenantMembership.user_id == first_membership.user_id,
            )
            .values(deactivated_at=datetime.now(UTC))
        )
        await db_session.commit()

        rows = await repository.list_active_membership_details(user.id)

        assert len(rows) == 1
        _, tenant_name, _, _ = rows[0]
        assert tenant_name == "Sam's Active Company"

    async def test_returns_empty_list_when_no_memberships(
        self, repository: TenantsRepository, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "tina@example.com")

        rows = await repository.list_active_membership_details(user.id)

        assert rows == []


class TestRoleColumnConstraint:
    async def test_rejects_a_role_outside_the_four_values(
        self, repository: TenantsRepository, db_session: AsyncSession
    ) -> None:
        from tenants.models import TenantMembership

        user = await _make_user(db_session, "uma@example.com")
        tenant_membership, _, _, _ = await repository.create_tenant(
            user_id=user.id, name="Uma's Company"
        )

        db_session.add(
            TenantMembership(
                tenant_id=tenant_membership.tenant_id,
                user_id=uuid.uuid4(),
                role="superuser",
            )
        )
        with pytest.raises(DBAPIError):
            await db_session.commit()


class TestSlugGeneration:
    async def test_slug_handles_special_characters(
        self, repository: TenantsRepository, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "user@example.com")

        membership, _, _, _ = await repository.create_tenant(
            user_id=user.id, name="Test@Company#123!"
        )

        # Retrieve the tenant to check its slug
        from tenants.models import Tenant
        from sqlalchemy import select

        tenant = await db_session.scalar(
            select(Tenant).where(Tenant.id == membership.tenant_id)
        )

        assert tenant is not None
        # Slug should have special characters replaced with hyphens
        assert "test-company-123" in tenant.slug

    async def test_slug_handles_unicode_characters(
        self, repository: TenantsRepository, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "user@example.com")

        membership, _, _, _ = await repository.create_tenant(
            user_id=user.id, name="Café Société"
        )

        # Retrieve the tenant to check its slug
        from tenants.models import Tenant
        from sqlalchemy import select

        tenant = await db_session.scalar(
            select(Tenant).where(Tenant.id == membership.tenant_id)
        )

        assert tenant is not None
        # Slug should be ASCII-safe
        assert tenant.slug is not None
        assert len(tenant.slug) > 0

    async def test_slug_handles_very_long_names(
        self, repository: TenantsRepository, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "user@example.com")
        long_name = "A" * 200  # Very long tenant name

        membership, _, _, _ = await repository.create_tenant(
            user_id=user.id, name=long_name
        )

        # Retrieve the tenant to check its slug
        from tenants.models import Tenant
        from sqlalchemy import select

        tenant = await db_session.scalar(
            select(Tenant).where(Tenant.id == membership.tenant_id)
        )

        assert tenant is not None
        # Slug should be truncated to prevent database issues
        assert len(tenant.slug) <= 89  # 80 chars + hyphen + 8-char suffix
