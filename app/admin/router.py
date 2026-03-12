from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.schemas import (
    AutocompleteResponse,
    CreateSpotRequest,
    GooglePlacePreviewResponse,
    SpotListResponse,
    SpotResponse,
)
from app.admin.service import create_spot, list_spots
from app.dependencies import get_admin_user, get_db
from app.google_places.client import google_places_client

router = APIRouter()


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
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_admin_user),
):
    """List all spots (active and inactive). Paginated, with optional name search."""
    spots, total = await list_spots(db, page, page_size, search)
    return SpotListResponse(spots=spots, total=total, page=page, page_size=page_size)


@router.post("/spots", response_model=SpotResponse, status_code=201)
async def add_spot(
    payload: CreateSpotRequest,
    db: AsyncSession = Depends(get_db),
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
    return await create_spot(db, payload, uuid.UUID(admin["user_id"]))
