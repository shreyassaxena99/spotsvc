from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response

from app.admin.schemas import (
    AutocompleteResponse,
    CreateSpotRequest,
    GooglePlacePreviewResponse,
    SpotListResponse,
    SpotResponse,
    UpdateSpotRequest,
    ValidateRequest,
    ValidateResponse,
)
from app.admin.service import create_spot, delete_spot, list_spots, update_spot
from app.config import settings
from app.dependencies import no_auth as get_admin_user
from app.google_places.client import google_places_client

router = APIRouter()


@router.post("/validate", response_model=ValidateResponse)
async def validate_password(payload: ValidateRequest):
    """Check provided password against ADMIN_PWD environment variable."""
    valid = payload.password.get_secret_value() == settings.admin_pwd
    return ValidateResponse(valid=valid)


@router.get("/google-autocomplete", response_model=AutocompleteResponse)
async def autocomplete_places(
    q: str = Query(..., min_length=2, description="Search query (min 2 chars)"),
    admin: dict = Depends(get_admin_user),
):
    """Proxy Google Places Autocomplete, biased to London. Used by the admin panel search box."""
    suggestions = google_places_client.autocomplete(q)
    return AutocompleteResponse(suggestions=suggestions)


@router.get("/google-place/{place_id}", response_model=GooglePlacePreviewResponse)
async def get_google_place_preview(
    place_id: str,
    admin: dict = Depends(get_admin_user),
):
    """Fetch full Google Place details for admin preview before saving a spot."""
    place = google_places_client.get_details(place_id)
    return GooglePlacePreviewResponse(place=place)


@router.get("/spots", response_model=SpotListResponse)
async def list_admin_spots(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="Filter by spot name"),
    admin: dict = Depends(get_admin_user),
):
    """List all spots (active and inactive). Paginated, with optional name search."""
    spots, total = list_spots(page, page_size, search)
    return SpotListResponse(spots=spots, total=total, page=page, page_size=page_size)


@router.post("/spots", response_model=SpotResponse, status_code=201)
async def add_spot(
    payload: CreateSpotRequest,
    admin: dict = Depends(get_admin_user),
):
    """
    Create a new curated spot.

    Flow:
    1. Admin uses /admin/google-autocomplete to search for a place.
    2. Admin selects a suggestion and previews it via /admin/google-place/{place_id}.
    3. Admin fills in the manual fields (category, access_type, etc.) and POSTs here.
    4. Service fetches all place data from Google and stores the spot in the DB.
    """
    created_by = uuid.UUID(admin["user_id"]) if admin.get("user_id") else None
    return create_spot(payload, created_by)


@router.put("/spots/{spot_id}", response_model=SpotResponse)
async def edit_spot(
    spot_id: uuid.UUID,
    payload: UpdateSpotRequest,
    admin: dict = Depends(get_admin_user),
) -> SpotResponse:
    """Update curated fields on an existing spot. Only provided fields are changed."""
    return update_spot(spot_id, payload)


@router.delete("/spots/{spot_id}", status_code=204, response_class=Response, tags=["admin"])
async def remove_spot(
    spot_id: uuid.UUID,
    admin: dict = Depends(get_admin_user),
) -> None:
    """Soft-delete a spot (sets is_active = false)."""
    delete_spot(spot_id)
