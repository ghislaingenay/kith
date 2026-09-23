"""Pydantic API schemas for the users domain."""

from pydantic import BaseModel, EmailStr, Field, field_validator


class ProfileResponse(BaseModel):
    """The caller's own Profile. `name` and `avatar_url` are `None` until
    set; the email is always present so a client can fall back to it."""

    email: EmailStr
    name: str | None
    avatar_url: str | None


class UpdateProfileRequest(BaseModel):
    """`name` is required in the body so an empty `{}` can't clear it by
    accident; a blank or `null` name is stored as unset."""

    name: str | None = Field(max_length=100)

    @field_validator("name", mode="before")
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value
