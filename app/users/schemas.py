from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel, Field


class UpdateProfileRequest(BaseModel):
    display_name: Optional[str] = Field(None, min_length=1, max_length=100)
    email_opt_in: Optional[bool] = None


class ProfileResponse(BaseModel):
    user_id: uuid.UUID
    display_name: Optional[str]
    email_opt_in: bool
