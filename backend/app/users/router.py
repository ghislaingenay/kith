"""HTTP layer for the users domain: a User's own Profile."""

from typing import Annotated

from auth.dependencies import get_current_user
from auth.schemas import AuthenticatedUser
from core.security.dependencies import require_allowed_origin
from fastapi import APIRouter, Depends, UploadFile
from users.avatar import MAX_AVATAR_BYTES
from users.dependencies import get_profile_service
from users.schemas import ProfileResponse, UpdateProfileRequest
from users.service import ProfileService

router = APIRouter(prefix="/users", tags=["users"])


@router.patch(
    "/me/profile",
    response_model=ProfileResponse,
    dependencies=[Depends(require_allowed_origin)],
)
async def update_my_profile(
    data: UpdateProfileRequest,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    service: Annotated[ProfileService, Depends(get_profile_service)],
) -> ProfileResponse:
    """Updates the caller's profile name.

    Every User should already have a Profile created at signup; if the Profile row is missing, the service raises `ProfileNotFound` (HTTP 500)."""
    return await service.update_name(user, data.name)


@router.put(
    "/me/avatar",
    response_model=ProfileResponse,
    dependencies=[Depends(require_allowed_origin)],
)
async def upload_my_avatar(
    file: UploadFile,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    service: Annotated[ProfileService, Depends(get_profile_service)],
) -> ProfileResponse:
    """PUT because the avatar is a single replaceable object per User. Reads
    one byte past the limit so an oversized file fails size validation
    immediately — note this doesn't avoid buffering: Starlette has already
    spooled the whole multipart body into `file` before this handler runs."""
    data = await file.read(MAX_AVATAR_BYTES + 1)
    return await service.upload_avatar(user, content_type=file.content_type, data=data)
