from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user
from app.users.schemas import ProfileResponse, UpdateProfileRequest
from app.users.service import update_profile

router = APIRouter(tags=["users"])


@router.patch("/me", response_model=ProfileResponse)
async def patch_me(
    payload: UpdateProfileRequest,
    user: dict = Depends(get_current_user),
) -> ProfileResponse:
    """Update the current user's profile (e.g. email_opt_in)."""
    if payload.display_name is None and payload.email_opt_in is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="No fields provided to update")
    return update_profile(
        uuid.UUID(user["user_id"]),
        display_name=payload.display_name,
        email_opt_in=payload.email_opt_in,
    )
