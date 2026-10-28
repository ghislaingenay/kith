"""Load Test Tenants, Users and Sessions for k6 (ADR-0021). The command that
runs it is `scripts/load_test_sessions.py` (`make load-test-sessions`).

Sessions come from `SessionService.create_session()`, the path a real
sign-in takes, so k6 signs in hundreds of Users without Magic Links and no
HTTP endpoint exists that could do the same on prod."""

import math
import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import async_sessionmaker

from auth.session import SessionService
from core.cache.provider import CacheProvider
from credits.repository import CreditsRepository
from credits.service import TOKENS_PER_CREDIT
from loadtest.config import LoadTestSettings
from loadtest.exceptions import (
    InvalidLoadTestSizeError,
    LoadTestDisabledError,
    NonReservedEmailDomainError,
)
from loadtest.repository import LoadTestRepository
from tenants.permissions import Role
from users.repository import UserRepository

# RFC 2606 `.example` never delivers; the API's email validation refuses `.invalid`.
LOAD_TEST_EMAIL_DOMAIN = "loadtest.example"
# Matches the default seat count of a Tenant made through onboarding.
_MIN_MAX_USERS = 5


@dataclass(frozen=True)
class LoadTestSession:
    email: str
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    # Out of `repr` so a logged or printed result never carries a live cookie.
    session_id: str = field(repr=False)


def _tenant_slug(index: int) -> str:
    return f"load-test-{index:02d}"


def _user_email(index: int, domain: str) -> str:
    return f"load-test-user-{index:04d}@{domain}"


async def create_load_test_sessions(
    session_factory: async_sessionmaker,
    cache: CacheProvider,
    settings: LoadTestSettings,
    *,
    tenants: int,
    users: int,
    credits: int,
    email_domain: str = LOAD_TEST_EMAIL_DOMAIN,
) -> list[LoadTestSession]:
    """Creates or re-uses `tenants` Load Test Tenants and `users` Load Test
    Users dealt round-robin across them, tops each Tenant's Credit Balance
    up to `credits` with a Credit Adjustment, and issues one fresh Session
    per User. A refusal writes nothing."""
    if not settings.enabled:
        raise LoadTestDisabledError(
            "LOAD_TEST_ENABLED is not set; this only runs on the load-test VPS."
        )
    if email_domain != LOAD_TEST_EMAIL_DOMAIN:
        raise NonReservedEmailDomainError(
            f"Load Test Users must be on {LOAD_TEST_EMAIL_DOMAIN}, got {email_domain!r}."
        )
    if min(tenants, users, credits) < 1:
        raise InvalidLoadTestSizeError(
            f"Tenants, Users and Credits must each be at least 1, got "
            f"{tenants}, {users} and {credits}."
        )

    max_users = max(_MIN_MAX_USERS, math.ceil(users / tenants))
    target_tokens = credits * TOKENS_PER_CREDIT
    async with session_factory() as session:
        load_test_repository = LoadTestRepository(session)
        credits_repository = CreditsRepository(session)
        tenant_ids = []
        for index in range(1, tenants + 1):
            tenant_id = await load_test_repository.upsert_tenant(
                slug=_tenant_slug(index),
                name=f"Load Test Tenant {index:02d}",
                max_users=max_users,
            )
            # Topped up, not added, so re-runs don't grow it (ADR-0017 ledger rule).
            missing = target_tokens - await credits_repository.sum_tokens(tenant_id)
            if missing > 0:
                await credits_repository.add_adjustment(
                    tenant_id=tenant_id,
                    tokens=missing,
                    note=f"Load test top-up to {credits:,} Credits",
                )
            tenant_ids.append(tenant_id)
        await session.commit()

        user_repository = UserRepository(session)
        session_service = SessionService(cache)
        load_test_sessions = []
        for index in range(users):
            email = _user_email(index + 1, email_domain)
            user, _ = await user_repository.get_or_create_user(email)
            tenant_id = tenant_ids[index % tenants]
            await load_test_repository.set_only_membership(
                user_id=user.id, tenant_id=tenant_id, role=Role.MEMBER
            )
            await session.commit()
            load_test_sessions.append(
                LoadTestSession(
                    email=email,
                    user_id=user.id,
                    tenant_id=tenant_id,
                    session_id=await session_service.create_session(user.id),
                )
            )
    return load_test_sessions
