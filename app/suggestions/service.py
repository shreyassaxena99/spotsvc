from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from app.admin.schemas import CreateSpotRequest
from app.admin.service import create_spot
from app.db.database import supabase
from app.db.models import AccessType, SpotCategory
from app.suggestions.schemas import SubmitSuggestionRequest, SuggestionResponse

logger = logging.getLogger(__name__)


def _build_suggestion_response(data: dict) -> SuggestionResponse:
    return SuggestionResponse(
        id=data["id"],
        google_place_id=data["google_place_id"],
        place_name=data["place_name"],
        place_address=data.get("place_address"),
        suggester_name=data.get("suggester_name"),
        suggester_email=data.get("suggester_email"),
        note=data.get("note"),
        status=data["status"],
        admin_notes=data.get("admin_notes"),
        created_at=data["created_at"],
        updated_at=data["updated_at"],
    )


def submit_suggestion(payload: SubmitSuggestionRequest) -> SuggestionResponse:
    row: dict = {
        "google_place_id": payload.google_place_id,
        "place_name": payload.place_name,
        "place_address": payload.place_address,
        "suggester_name": payload.suggester_name,
        "suggester_email": payload.suggester_email,
        "note": payload.note,
    }
    row = {k: v for k, v in row.items() if v is not None}

    try:
        result = supabase.table("spot_suggestions").insert(row).execute()
    except Exception as exc:
        logger.error("DB insert failed for suggestion: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"DB error: {exc}")

    if not result.data:
        raise HTTPException(status_code=500, detail="Insert returned no data")

    return _build_suggestion_response(result.data[0])


def list_suggestions(
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
) -> tuple[list[SuggestionResponse], int]:
    query = supabase.table("spot_suggestions").select("*", count="exact")

    if status:
        query = query.eq("status", status)

    result = (
        query.order("created_at", desc=True)
        .range((page - 1) * page_size, page * page_size - 1)
        .execute()
    )

    suggestions = [_build_suggestion_response(row) for row in result.data]
    return suggestions, result.count or 0


def update_suggestion_status(
    suggestion_id: uuid.UUID,
    status: str,
    admin_notes: Optional[str],
    category: Optional[SpotCategory] = None,
    access_type: Optional[AccessType] = None,
    noise_level: Optional[str] = None,
    description: Optional[str] = None,
) -> SuggestionResponse:
    # Fetch the suggestion first
    fetch = (
        supabase.table("spot_suggestions")
        .select("*")
        .eq("id", str(suggestion_id))
        .execute()
    )
    if not fetch.data:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    suggestion = fetch.data[0]

    # On approval, create the spot from the suggestion's google_place_id
    if status == "approved":
        spot_payload = CreateSpotRequest(
            google_place_id=suggestion["google_place_id"],
            category=category,
            access_type=access_type,
            noise_level=noise_level,
            description=description,
            admin_notes=admin_notes,
        )
        create_spot(spot_payload, admin_user_id=None)

    update_data: dict = {
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if admin_notes is not None:
        update_data["admin_notes"] = admin_notes

    try:
        result = (
            supabase.table("spot_suggestions")
            .update(update_data)
            .eq("id", str(suggestion_id))
            .execute()
        )
    except Exception as exc:
        logger.error("DB update failed for suggestion %s: %s", suggestion_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"DB error: {exc}")

    return _build_suggestion_response(result.data[0])
