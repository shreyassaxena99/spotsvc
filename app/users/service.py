from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from app.db.database import supabase
from app.users.schemas import ProfileResponse

logger = logging.getLogger(__name__)


def update_profile(
    user_id: uuid.UUID,
    display_name: Optional[str] = None,
    email_opt_in: Optional[bool] = None,
) -> ProfileResponse:
    if display_name is None and email_opt_in is None:
        raise HTTPException(status_code=422, detail="No fields provided to update")

    updated_display_name: Optional[str] = None
    updated_email_opt_in: bool = False

    if display_name is not None:
        auth_result = supabase.auth.admin.update_user_by_id(
            str(user_id), {"user_metadata": {"full_name": display_name}}
        )
        updated_display_name = auth_result.user.user_metadata.get("full_name")

    if email_opt_in is not None:
        now = datetime.now(timezone.utc).isoformat()
        pref_result = (
            supabase.table("user_preferences")
            .upsert(
                {"user_id": str(user_id), "email_opt_in": email_opt_in, "updated_at": now},
                on_conflict="user_id",
            )
            .execute()
        )
        updated_email_opt_in = pref_result.data[0]["email_opt_in"]

    return ProfileResponse(
        user_id=user_id,
        display_name=updated_display_name,
        email_opt_in=updated_email_opt_in,
    )
