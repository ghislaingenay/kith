from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.logging import setup_logger
from users.exceptions import UserNotFound
from users.models import Profile, User

logger = setup_logger(__name__)


class UserRepository:
    """Repository class for managing user data."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_email(
        self, email: str, *, with_profile: bool = False
    ) -> User | None:
        """Fetch a user by their email address."""
        query = select(User).where(User.email == email)
        if with_profile:
            query = query.options(selectinload(User.profile))
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_user_id(
        self, user_id: str, *, with_profile: bool = False
    ) -> User | None:
        """Fetch a user by their user ID."""
        query = select(User).where(User.id == user_id)
        if with_profile:
            query = query.options(selectinload(User.profile))
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_user(self, user: User) -> User:
        """Create a new user in the database."""
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def get_or_create_user(self, email: str) -> User:
        """Fetch a user by email or create one: first sign-in is signup.
        Identity only — tenant/role assignment lives on TenantMembership,
        not User (see tenants/models.py)."""
        user = await self.get_by_email(email)
        if user is None:
            try:
                user = User(email=email)
                self.session.add(user)
                await self.session.commit()
                await self.session.refresh(user)
            except IntegrityError:
                # Concurrent insert/unique-constraint race: roll back and re-fetch the row that won.
                await self.session.rollback()
                user = await self.get_by_email(email)
        if not user:
            logger.error(f"User {email} not found and could not be created.")
            raise UserNotFound()
        return user

    async def update_user(self, user: User) -> User:
        """Update an existing user in the database."""
        await self.session.commit()
        await self.session.refresh(user)
        return user


class ProfileRepository:
    """Repository class for managing profile data."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user_id(self, user_id: str) -> Profile | None:
        """Fetch a profile by the associated user ID."""
        result = await self.session.execute(
            select(Profile).where(Profile.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def create_profile(self, profile: Profile) -> Profile:
        """Create a new profile in the database."""
        self.session.add(profile)
        await self.session.commit()
        await self.session.refresh(profile)
        return profile

    async def update_profile(self, profile: Profile) -> Profile:
        """Update an existing profile in the database."""
        await self.session.commit()
        await self.session.refresh(profile)
        return profile
