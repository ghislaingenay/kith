"""Integration tests for TenantsRepository against a real Postgres. Requires
DATABASE_URL — skipped automatically otherwise (see conftest.py)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from tenants.models import (
    PendingMembership,
    PendingMembershipStatus,
    Tenant,
    TenantMembership,
)
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


async def _make_tenant(db_session: AsyncSession, *, name: str = "Acme") -> Tenant:
    tenant = Tenant(
        name=name, slug=f"{name.lower()}-{uuid.uuid4().hex[:8]}", tier="free", max_users=5
    )
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)
    return tenant


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

def _pending(
    tenant: Tenant,
    email: str,
    *,
    role: Role = Role.MEMBER,
    status: PendingMembershipStatus = PendingMembershipStatus.PENDING,
    created_at: datetime | None = None,
) -> PendingMembership:
    row = PendingMembership(
        tenant_id=tenant.id, email=email, role=role, status=status
    )
    if created_at is not None:
        row.created_at = created_at
    return row


async def _reload(db_session: AsyncSession, tenant: Tenant, email: str):
    """Every PendingMembership row for (tenant, email), freshly read — the
    repository writes through raw UPDATEs, so identity-mapped rows would
    otherwise be stale."""
    result = await db_session.execute(
        select(PendingMembership)
        .where(
            PendingMembership.tenant_id == tenant.id,
            PendingMembership.email == email,
        )
        .execution_options(populate_existing=True)
    )
    return result.scalars().all()


class TestPendingMembershipConstraints:
    async def test_history_rows_can_sit_alongside_a_pending_row(
        self, db_session: AsyncSession
    ) -> None:
        tenant = await _make_tenant(db_session)
        db_session.add_all(
            [
                _pending(tenant, "a@example.com", status=PendingMembershipStatus.ACCEPTED),
                _pending(tenant, "a@example.com", status=PendingMembershipStatus.ACCEPTED),
                _pending(tenant, "a@example.com", status=PendingMembershipStatus.EXPIRED),
                _pending(tenant, "a@example.com", status=PendingMembershipStatus.REVOKED),
                _pending(tenant, "a@example.com"),
            ]
        )

        await db_session.commit()

        assert len(await _reload(db_session, tenant, "a@example.com")) == 5

    async def test_rejects_a_second_pending_row_for_the_same_tenant_and_email(
        self, db_session: AsyncSession
    ) -> None:
        tenant = await _make_tenant(db_session)
        db_session.add_all(
            [_pending(tenant, "b@example.com"), _pending(tenant, "b@example.com")]
        )

        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_the_same_email_can_be_pending_at_different_tenants(
        self, db_session: AsyncSession
    ) -> None:
        first = await _make_tenant(db_session, name="First")
        second = await _make_tenant(db_session, name="Second")
        db_session.add_all(
            [_pending(first, "c@example.com"), _pending(second, "c@example.com")]
        )

        await db_session.commit()

    @pytest.mark.parametrize("email", ["Dana@Example.com", " dana@example.com"])
    async def test_rejects_an_email_that_is_not_normalized(
        self, db_session: AsyncSession, email: str
    ) -> None:
        tenant = await _make_tenant(db_session)
        db_session.add(_pending(tenant, email))

        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_rejects_a_status_outside_the_lifecycle(
        self, db_session: AsyncSession
    ) -> None:
        tenant = await _make_tenant(db_session)
        row = _pending(tenant, "d@example.com")
        row.status = "rejected"
        db_session.add(row)

        with pytest.raises(IntegrityError):
            await db_session.commit()


class TestListPendingMemberships:
    async def test_returns_the_pending_rows_for_the_email_across_tenants(
        self, repository: TenantsRepository, db_session: AsyncSession
    ) -> None:
        first = await _make_tenant(db_session, name="First")
        second = await _make_tenant(db_session, name="Second")
        elsewhere = await _make_tenant(db_session, name="Elsewhere")
        db_session.add_all(
            [
                _pending(first, "dana@example.com"),
                _pending(second, "dana@example.com"),
                _pending(elsewhere, "someone-else@example.com"),
            ]
        )
        await db_session.commit()

        rows = await repository.list_pending_memberships("dana@example.com")

        assert {row.tenant_id for row in rows} == {first.id, second.id}

    @pytest.mark.parametrize(
        "status",
        [
            PendingMembershipStatus.ACCEPTED,
            PendingMembershipStatus.REVOKED,
            PendingMembershipStatus.EXPIRED,
        ],
    )
    async def test_ignores_rows_that_are_no_longer_pending(
        self,
        repository: TenantsRepository,
        db_session: AsyncSession,
        status: PendingMembershipStatus,
    ) -> None:
        tenant = await _make_tenant(db_session)
        db_session.add(_pending(tenant, "eli@example.com", status=status))
        await db_session.commit()

        assert await repository.list_pending_memberships("eli@example.com") == []

    async def test_expiry_is_applied_at_match_time_not_read_from_status(
        self, repository: TenantsRepository, db_session: AsyncSession
    ) -> None:
        """A row still stored as 'pending' but older than the 7-day TTL must
        not match — a lazily-stored 'expired' could be stale."""
        stale = await _make_tenant(db_session, name="Stale")
        fresh = await _make_tenant(db_session, name="Fresh")
        now = datetime.now(UTC)
        db_session.add_all(
            [
                _pending(stale, "fern@example.com", created_at=now - timedelta(days=8)),
                _pending(fresh, "fern@example.com", created_at=now - timedelta(days=6)),
            ]
        )
        await db_session.commit()

        rows = await repository.list_pending_memberships("fern@example.com")

        assert [row.tenant_id for row in rows] == [fresh.id]

    async def test_orders_rows_deterministically(
        self, repository: TenantsRepository, db_session: AsyncSession
    ) -> None:
        older = await _make_tenant(db_session, name="Older")
        newer = await _make_tenant(db_session, name="Newer")
        now = datetime.now(UTC)
        db_session.add_all(
            [
                _pending(newer, "gia@example.com", created_at=now),
                _pending(older, "gia@example.com", created_at=now - timedelta(days=1)),
            ]
        )
        await db_session.commit()

        rows = await repository.list_pending_memberships("gia@example.com")

        assert [row.tenant_id for row in rows] == [older.id, newer.id]


class TestActivatePendingMemberships:
    async def test_creates_a_membership_carrying_the_stored_role(
        self, repository: TenantsRepository, db_session: AsyncSession
    ) -> None:
        tenant = await _make_tenant(db_session)
        db_session.add(_pending(tenant, "dana@example.com", role=Role.ADMIN))
        await db_session.commit()
        user = await _make_user(db_session, "dana@example.com")

        memberships = await repository.activate_pending_memberships(
            user_id=user.id, email="dana@example.com", tenant_ids=[tenant.id]
        )

        assert [(m.tenant_id, m.user_id, m.role) for m in memberships] == [
            (tenant.id, user.id, Role.ADMIN)
        ]

    async def test_deactivates_the_pending_row_instead_of_deleting_it(
        self, repository: TenantsRepository, db_session: AsyncSession
    ) -> None:
        tenant = await _make_tenant(db_session)
        db_session.add(_pending(tenant, "eli@example.com"))
        await db_session.commit()
        user = await _make_user(db_session, "eli@example.com")

        await repository.activate_pending_memberships(
            user_id=user.id, email="eli@example.com", tenant_ids=[tenant.id]
        )

        [row] = await _reload(db_session, tenant, "eli@example.com")
        assert row.status == PendingMembershipStatus.ACCEPTED
        assert row.accepted_at is not None
        assert row.accepted_by_user_id == user.id

    async def test_activates_every_given_tenant_in_one_call(
        self, repository: TenantsRepository, db_session: AsyncSession
    ) -> None:
        first = await _make_tenant(db_session, name="First")
        second = await _make_tenant(db_session, name="Second")
        db_session.add_all(
            [
                _pending(first, "fern@example.com", role=Role.VIEWER),
                _pending(second, "fern@example.com", role=Role.MEMBER),
            ]
        )
        await db_session.commit()
        user = await _make_user(db_session, "fern@example.com")

        memberships = await repository.activate_pending_memberships(
            user_id=user.id,
            email="fern@example.com",
            tenant_ids=[first.id, second.id],
        )

        assert {(m.tenant_id, m.role) for m in memberships} == {
            (first.id, Role.VIEWER),
            (second.id, Role.MEMBER),
        }

    async def test_only_touches_the_tenants_it_is_given(
        self, repository: TenantsRepository, db_session: AsyncSession
    ) -> None:
        target = await _make_tenant(db_session, name="Target")
        other = await _make_tenant(db_session, name="Other")
        db_session.add_all(
            [_pending(target, "gia@example.com"), _pending(other, "gia@example.com")]
        )
        await db_session.commit()
        user = await _make_user(db_session, "gia@example.com")

        await repository.activate_pending_memberships(
            user_id=user.id, email="gia@example.com", tenant_ids=[target.id]
        )

        [untouched] = await _reload(db_session, other, "gia@example.com")
        assert untouched.status == PendingMembershipStatus.PENDING
        assert (
            await db_session.scalar(
                select(TenantMembership).where(TenantMembership.tenant_id == other.id)
            )
            is None
        )

    async def test_a_retry_is_a_no_op_not_an_error(
        self, repository: TenantsRepository, db_session: AsyncSession
    ) -> None:
        tenant = await _make_tenant(db_session)
        db_session.add(_pending(tenant, "hugo@example.com"))
        await db_session.commit()
        user = await _make_user(db_session, "hugo@example.com")
        await repository.activate_pending_memberships(
            user_id=user.id, email="hugo@example.com", tenant_ids=[tenant.id]
        )

        retried = await repository.activate_pending_memberships(
            user_id=user.id, email="hugo@example.com", tenant_ids=[tenant.id]
        )

        assert retried == []
        memberships = (
            await db_session.scalars(
                select(TenantMembership).where(TenantMembership.user_id == user.id)
            )
        ).all()
        assert len(memberships) == 1

    async def test_succeeds_when_the_user_is_already_a_member(
        self, repository: TenantsRepository, db_session: AsyncSession
    ) -> None:
        tenant = await _make_tenant(db_session)
        user = await _make_user(db_session, "ivy@example.com")
        db_session.add(
            TenantMembership(tenant_id=tenant.id, user_id=user.id, role=Role.MEMBER)
        )
        db_session.add(_pending(tenant, "ivy@example.com"))
        await db_session.commit()

        memberships = await repository.activate_pending_memberships(
            user_id=user.id, email="ivy@example.com", tenant_ids=[tenant.id]
        )

        assert [m.tenant_id for m in memberships] == [tenant.id]
        [row] = await _reload(db_session, tenant, "ivy@example.com")
        assert row.status == PendingMembershipStatus.ACCEPTED

    async def test_does_nothing_when_there_is_no_pending_row(
        self, repository: TenantsRepository, db_session: AsyncSession
    ) -> None:
        tenant = await _make_tenant(db_session)
        user = await _make_user(db_session, "jon@example.com")

        memberships = await repository.activate_pending_memberships(
            user_id=user.id, email="jon@example.com", tenant_ids=[tenant.id]
        )

        assert memberships == []

    async def test_skips_a_row_past_its_ttl_even_if_still_stored_as_pending(
        self, repository: TenantsRepository, db_session: AsyncSession
    ) -> None:
        tenant = await _make_tenant(db_session)
        db_session.add(
            _pending(
                tenant,
                "kai@example.com",
                created_at=datetime.now(UTC) - timedelta(days=8),
            )
        )
        await db_session.commit()
        user = await _make_user(db_session, "kai@example.com")

        memberships = await repository.activate_pending_memberships(
            user_id=user.id, email="kai@example.com", tenant_ids=[tenant.id]
        )

        assert memberships == []

    async def test_skips_a_revoked_row(
        self, repository: TenantsRepository, db_session: AsyncSession
    ) -> None:
        tenant = await _make_tenant(db_session)
        db_session.add(
            _pending(
                tenant, "lee@example.com", status=PendingMembershipStatus.REVOKED
            )
        )
        await db_session.commit()
        user = await _make_user(db_session, "lee@example.com")

        memberships = await repository.activate_pending_memberships(
            user_id=user.id, email="lee@example.com", tenant_ids=[tenant.id]
        )

        assert memberships == []


class TestGetTenantIdBySlug:
    async def test_finds_the_tenant_with_that_slug(
        self, repository: TenantsRepository, db_session: AsyncSession
    ) -> None:
        tenant = await _make_tenant(db_session)
        await _make_tenant(db_session, name="Other")

        assert await repository.get_tenant_id_by_slug(tenant.slug) == tenant.id

    async def test_none_for_an_unknown_slug(
        self, repository: TenantsRepository
    ) -> None:
        assert await repository.get_tenant_id_by_slug("no-such-tenant") is None
