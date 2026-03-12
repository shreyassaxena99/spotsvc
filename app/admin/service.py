from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from app.admin.schemas import CreateSpotRequest, SpotResponse
from app.db.database import supabase
from app.google_places.client import google_places_client
from app.google_places.schemas import PlaceDetails

logger = logging.getLogger(__name__)


def _build_spot_response(data: dict) -> SpotResponse:
    return SpotResponse(
        id=data["id"],
        google_place_id=data["google_place_id"],
        name=data["name"],
        formatted_address=data.get("formatted_address"),
        short_address=data.get("short_address"),
        latitude=data["latitude"],
        longitude=data["longitude"],
        phone_national=data.get("phone_national"),
        phone_international=data.get("phone_international"),
        google_maps_uri=data.get("google_maps_uri"),
        website_uri=data.get("website_uri"),
        price_level=data.get("price_level"),
        rating=data.get("rating"),
        user_rating_count=data.get("user_rating_count"),
        editorial_summary=data.get("editorial_summary"),
        business_status=data.get("business_status"),
        timezone=data.get("timezone"),
        regular_hours=data.get("regular_hours"),
        current_hours=data.get("current_hours"),
        photos=data.get("photos") or [],
        outdoor_seating=data.get("outdoor_seating"),
        restroom=data.get("restroom"),
        serves_breakfast=data.get("serves_breakfast"),
        serves_lunch=data.get("serves_lunch"),
        serves_dinner=data.get("serves_dinner"),
        serves_brunch=data.get("serves_brunch"),
        serves_coffee=data.get("serves_coffee"),
        allows_dogs=data.get("allows_dogs"),
        good_for_groups=data.get("good_for_groups"),
        dine_in=data.get("dine_in"),
        takeout=data.get("takeout"),
        delivery=data.get("delivery"),
        reservable=data.get("reservable"),
        parking_options=data.get("parking_options"),
        payment_options=data.get("payment_options"),
        accessibility_options=data.get("accessibility_options"),
        category=data["category"],
        access_type=data["access_type"],
        wifi_available=data.get("wifi_available", True),
        power_outlets=data.get("power_outlets", True),
        noise_level=data.get("noise_level"),
        description=data.get("description"),
        admin_notes=data.get("admin_notes"),
        is_active=data.get("is_active", True),
        google_data_updated_at=data.get("google_data_updated_at"),
        created_at=data["created_at"],
        updated_at=data["updated_at"],
    )


def create_spot(
    payload: CreateSpotRequest,
    admin_user_id: Optional[uuid.UUID],
) -> SpotResponse:
    # 1. Guard against duplicate place IDs
    existing = (
        supabase.table("spots")
        .select("id")
        .eq("google_place_id", payload.google_place_id)
        .execute()
    )
    if existing.data:
        raise HTTPException(
            status_code=409,
            detail=f"A spot with google_place_id '{payload.google_place_id}' already exists.",
        )

    # 2. Fetch full place data from Google
    try:
        place: PlaceDetails = google_places_client.get_details(payload.google_place_id)
    except Exception as exc:
        logger.error("Google Places API error for place_id=%s: %s", payload.google_place_id, exc)
        raise HTTPException(status_code=502, detail=f"Google Places API error: {exc}")

    # 3. Build insert payload — None values are excluded so DB defaults/NULLs apply
    spot_data: dict = {
        "google_place_id": payload.google_place_id,
        "name": place.name,
        "formatted_address": place.formatted_address,
        "short_address": place.short_address,
        "latitude": place.latitude,
        "longitude": place.longitude,
        "phone_national": place.phone_national,
        "phone_international": place.phone_international,
        "google_maps_uri": place.google_maps_uri,
        "website_uri": place.website_uri,
        "price_level": place.price_level,
        "rating": place.rating,
        "user_rating_count": place.user_rating_count,
        "editorial_summary": place.editorial_summary,
        "business_status": place.business_status,
        "timezone": place.timezone or "Europe/London",
        "regular_hours": place.regular_hours,
        "current_hours": place.current_hours,
        "photos": place.photos,
        "outdoor_seating": place.outdoor_seating,
        "restroom": place.restroom,
        "serves_breakfast": place.serves_breakfast,
        "serves_lunch": place.serves_lunch,
        "serves_dinner": place.serves_dinner,
        "serves_brunch": place.serves_brunch,
        "serves_coffee": place.serves_coffee,
        "allows_dogs": place.allows_dogs,
        "good_for_groups": place.good_for_groups,
        "dine_in": place.dine_in,
        "takeout": place.takeout,
        "delivery": place.delivery,
        "reservable": place.reservable,
        "parking_options": place.parking_options,
        "payment_options": place.payment_options,
        "accessibility_options": place.accessibility_options,
        "category": payload.category.value,
        "access_type": payload.access_type.value,
        "wifi_available": payload.wifi_available,
        "power_outlets": payload.power_outlets,
        "noise_level": payload.noise_level,
        "description": payload.description,
        "admin_notes": payload.admin_notes,
        "is_active": True,
        "created_by": str(admin_user_id) if admin_user_id else None,
        "google_data_updated_at": datetime.now(timezone.utc).isoformat(),
    }
    spot_data = {k: v for k, v in spot_data.items() if v is not None}

    try:
        result = supabase.table("spots").insert(spot_data).execute()
    except Exception as exc:
        logger.error("DB insert failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"DB error: {exc}")

    if not result.data:
        raise HTTPException(status_code=500, detail="Insert returned no data")

    return _build_spot_response(result.data[0])


def list_spots(
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
) -> tuple[list[SpotResponse], int]:
    query = supabase.table("spots").select("*", count="exact")

    if search:
        query = query.ilike("name", f"%{search}%")

    result = (
        query.order("created_at", desc=True)
        .range((page - 1) * page_size, page * page_size - 1)
        .execute()
    )

    spots = [_build_spot_response(row) for row in result.data]
    return spots, result.count or 0
