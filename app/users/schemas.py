from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel, Field


class DeleteMeRequest(BaseModel):
    reason: str = Field(..., min_length=1)


class UpdateProfileRequest(BaseModel):
    display_name: Optional[str] = Field(None, min_length=1, max_length=100)
    email_opt_in: Optional[bool] = None


class ProfileResponse(BaseModel):
    user_id: uuid.UUID
    display_name: Optional[str]
    email_opt_in: bool


class OnboardingProfileRequest(BaseModel):
    working_style: Optional[str] = None
    home_area: Optional[str] = None
    work_area: Optional[str] = None
    wfh_days: Optional[list[str]] = None


class OnboardingProfileResponse(BaseModel):
    status: str


class UserProfileData(BaseModel):
    exists: bool
    user_id: Optional[uuid.UUID] = None
    working_style: Optional[str] = None
    home_area: Optional[str] = None
    work_area: Optional[str] = None
    wfh_days: Optional[list[str]] = None


class PushTokenRequest(BaseModel):
    token: str = Field(..., min_length=1)
