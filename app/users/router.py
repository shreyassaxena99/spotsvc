from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_user
from app.users.schemas import (
    OnboardingProfileRequest,
    OnboardingProfileResponse,
    ProfileResponse,
    UpdateProfileRequest,
    UserProfileData,
)
from app.users.service import get_user_profile, update_profile, upsert_user_profile

router = APIRouter(tags=["users"])


@router.patch("/me", response_model=ProfileResponse)
async def patch_me(
    payload: UpdateProfileRequest,
    user: dict = Depends(get_current_user),
) -> ProfileResponse:
    """Update the current user's profile (e.g. email_opt_in)."""
    if payload.display_name is None and payload.email_opt_in is None:
        raise HTTPException(status_code=422, detail="No fields provided to update")
    return update_profile(
        uuid.UUID(user["user_id"]),
        display_name=payload.display_name,
        email_opt_in=payload.email_opt_in,
    )


@router.post("/users/profile", response_model=OnboardingProfileResponse)
async def post_user_profile(
    payload: OnboardingProfileRequest,
    user: dict = Depends(get_current_user),
) -> OnboardingProfileResponse:
    """Upsert onboarding profile data for the authenticated user."""
    upsert_user_profile(
        uuid.UUID(user["user_id"]),
        working_style=payload.working_style,
        home_area=payload.home_area,
        work_area=payload.work_area,
    )
    return OnboardingProfileResponse(status="ok")


@router.get("/users/profile/{user_id}", response_model=UserProfileData)
async def get_profile(
    user_id: uuid.UUID,
    user: dict = Depends(get_current_user),
) -> UserProfileData:
    """Return the onboarding profile for the authenticated user, or exists=false if not yet set."""
    if str(user_id) != user["user_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    data = get_user_profile(user_id)
    return UserProfileData(**data)
