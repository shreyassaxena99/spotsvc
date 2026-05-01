from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from app.core.posthog import identify
from app.db.database import supabase
from app.users.schemas import ProfileResponse

logger = logging.getLogger(__name__)


def delete_user(user_id: uuid.UUID, reason: str) -> None:
    supabase.table("account_deletion_reasons").insert(
        {"user_id": str(user_id), "reason": reason}
    ).execute()

    for table in ("saved_spots", "user_preferences", "user_profiles"):
        try:
            supabase.table(table).delete().eq("user_id", str(user_id)).execute()
        except Exception as exc:
            logger.error("Failed to delete from %s for user %s: %s", table, user_id, exc)

    try:
        supabase.auth.admin.delete_user(str(user_id))
    except Exception as exc:
        logger.error("Failed to delete auth user %s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail="Failed to delete account")


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


def upsert_user_profile(
    user_id: uuid.UUID,
    working_style: Optional[str] = None,
    home_area: Optional[str] = None,
    work_area: Optional[str] = None,
    wfh_days: Optional[list[str]] = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    payload: dict = {"user_id": str(user_id), "updated_at": now}
    for key, val in (("working_style", working_style), ("home_area", home_area), ("work_area", work_area)):
        if val is not None:
            payload[key] = val
    if wfh_days is not None:
        payload["wfh_days"] = wfh_days

    try:
        supabase.table("user_profiles").upsert(
            payload,
            on_conflict="user_id",
        ).execute()
    except Exception as exc:
        logger.error("Failed to upsert user profile for %s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail="Failed to save profile")

    props = {
        k: v for k, v in {
            "working_style": working_style,
            "home_area": home_area,
            "work_area": work_area,
        }.items() if v is not None
    }
    identify(str(user_id), props)


def get_me(user_id: uuid.UUID) -> ProfileResponse:
    try:
        auth_result = supabase.auth.admin.get_user_by_id(str(user_id))
    except Exception as exc:
        logger.error("Failed to fetch auth user %s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail="Failed to fetch user")

    display_name: Optional[str] = None
    if auth_result.user:
        display_name = auth_result.user.user_metadata.get("full_name")

    email_opt_in = False
    try:
        pref_result = (
            supabase.table("user_preferences")
            .select("email_opt_in")
            .eq("user_id", str(user_id))
            .maybe_single()
            .execute()
        )
        if pref_result.data:
            email_opt_in = pref_result.data.get("email_opt_in", False)
    except Exception as exc:
        logger.error("Failed to fetch preferences for %s: %s", user_id, exc)

    return ProfileResponse(user_id=user_id, display_name=display_name, email_opt_in=email_opt_in)


def get_user_profile(user_id: uuid.UUID) -> dict:
    try:
        result = (
            supabase.table("user_profiles")
            .select("user_id, working_style, home_area, work_area, wfh_days")
            .eq("user_id", str(user_id))
            .execute()
        )
    except Exception as exc:
        logger.error("Failed to fetch user profile for %s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail="Failed to fetch profile")
    if not result.data:
        return {"exists": False}
    row = result.data[0]
    return {
        "exists": True,
        "user_id": row["user_id"],
        "working_style": row.get("working_style"),
        "home_area": row.get("home_area"),
        "work_area": row.get("work_area"),
        "wfh_days": row.get("wfh_days"),
    }


def upsert_push_token(user_id: uuid.UUID, token: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    try:
        supabase.table("user_profiles").upsert(
            {"user_id": str(user_id), "push_token": token, "push_token_updated_at": now},
            on_conflict="user_id",
        ).execute()
    except Exception as exc:
        logger.error("Failed to upsert push token for %s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail="Failed to save push token")


def delete_push_token(user_id: uuid.UUID) -> None:
    now = datetime.now(timezone.utc).isoformat()
    try:
        supabase.table("user_profiles").upsert(
            {"user_id": str(user_id), "push_token": None, "push_token_updated_at": now},
            on_conflict="user_id",
        ).execute()
    except Exception as exc:
        logger.error("Failed to clear push token for %s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail="Failed to clear push token")
