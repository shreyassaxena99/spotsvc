from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from geoalchemy2 import WKTElement
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.schemas import CreateSpotRequest, SpotResponse
from app.db.models import Spot
from app.google_places.client import google_places_client
from app.google_places.schemas import PlaceDetails

logger = logging.getLogger(__name__)


def _build_spot_response(spot: Spot, latitude: float, longitude: float) -> SpotResponse:
    return SpotResponse(
        id=spot.id,
        google_place_id=spot.google_place_id,
        name=spot.name,
        formatted_address=spot.formatted_address,
        short_address=spot.short_address,
        latitude=latitude,
        longitude=longitude,
        phone_national=spot.phone_national,
        phone_international=spot.phone_international,
        google_maps_uri=spot.google_maps_uri,
        website_uri=spot.website_uri,
        price_level=spot.price_level,
        rating=float(spot.rating) if spot.rating is not None else None,
        user_rating_count=spot.user_rating_count,
        editorial_summary=spot.editorial_summary,
        business_status=spot.business_status,
        timezone=spot.timezone,
        regular_hours=spot.regular_hours,
        current_hours=spot.current_hours,
        photos=spot.photos or [],
        outdoor_seating=spot.outdoor_seating,
        restroom=spot.restroom,
        serves_breakfast=spot.serves_breakfast,
        serves_lunch=spot.serves_lunch,
        serves_dinner=spot.serves_dinner,
        serves_brunch=spot.serves_brunch,
        serves_coffee=spot.serves_coffee,
        allows_dogs=spot.allows_dogs,
        good_for_groups=spot.good_for_groups,
        dine_in=spot.dine_in,
        takeout=spot.takeout,
        delivery=spot.delivery,
        reservable=spot.reservable,
        parking_options=spot.parking_options,
        payment_options=spot.payment_options,
        accessibility_options=spot.accessibility_options,
        category=spot.category,
        access_type=spot.access_type,
        wifi_available=spot.wifi_available,
        power_outlets=spot.power_outlets,
        noise_level=spot.noise_level,
        description=spot.description,
        admin_notes=spot.admin_notes,
        is_active=spot.is_active,
        google_data_updated_at=spot.google_data_updated_at,
        created_at=spot.created_at,
        updated_at=spot.updated_at,
    )


async def create_spot(
    db: AsyncSession,
    payload: CreateSpotRequest,
    admin_user_id: uuid.UUID,
) -> SpotResponse:
    # 1. Guard against duplicate place IDs
    existing = await db.scalar(
        select(Spot).where(Spot.google_place_id == payload.google_place_id)
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"A spot with google_place_id '{payload.google_place_id}' already exists.",
        )

    # 2. Fetch full place data from Google Places (sync call; acceptable for admin endpoints)
    try:
        place: PlaceDetails = google_places_client.get_details(payload.google_place_id)
    except Exception as exc:
        logger.error("Google Places API error for place_id=%s: %s", payload.google_place_id, exc)
        raise HTTPException(
            status_code=502,
            detail=f"Google Places API error: {exc}",
        )

    # 3. Persist — location as WKT geography point (PostGIS expects POINT(lon lat))
    spot = Spot(
        google_place_id=payload.google_place_id,
        name=place.name,
        formatted_address=place.formatted_address,
        short_address=place.short_address,
        location=WKTElement(f"POINT({place.longitude} {place.latitude})", srid=4326),
        phone_national=place.phone_national,
        phone_international=place.phone_international,
        google_maps_uri=place.google_maps_uri,
        website_uri=place.website_uri,
        price_level=place.price_level,
        rating=place.rating,
        user_rating_count=place.user_rating_count,
        editorial_summary=place.editorial_summary,
        business_status=place.business_status,
        timezone=place.timezone or "Europe/London",
        regular_hours=place.regular_hours,
        current_hours=place.current_hours,
        photos=place.photos,
        outdoor_seating=place.outdoor_seating,
        restroom=place.restroom,
        serves_breakfast=place.serves_breakfast,
        serves_lunch=place.serves_lunch,
        serves_dinner=place.serves_dinner,
        serves_brunch=place.serves_brunch,
        serves_coffee=place.serves_coffee,
        allows_dogs=place.allows_dogs,
        good_for_groups=place.good_for_groups,
        dine_in=place.dine_in,
        takeout=place.takeout,
        delivery=place.delivery,
        reservable=place.reservable,
        parking_options=place.parking_options,
        payment_options=place.payment_options,
        accessibility_options=place.accessibility_options,
        category=payload.category,
        access_type=payload.access_type,
        wifi_available=payload.wifi_available,
        power_outlets=payload.power_outlets,
        noise_level=payload.noise_level,
        description=payload.description,
        admin_notes=payload.admin_notes,
        is_active=True,
        created_by=admin_user_id,
        google_data_updated_at=datetime.now(timezone.utc),
    )
    db.add(spot)
    await db.commit()

    # 4. Re-fetch with coordinates extracted via PostGIS functions
    row = await db.execute(
        select(
            Spot,
            func.ST_Y(Spot.location).label("latitude"),
            func.ST_X(Spot.location).label("longitude"),
        ).where(Spot.id == spot.id)
    )
    spot_row = row.one()
    return _build_spot_response(spot_row[0], spot_row[1], spot_row[2])


async def list_spots(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
) -> tuple[list[SpotResponse], int]:
    base_query = select(
        Spot,
        func.ST_Y(Spot.location).label("latitude"),
        func.ST_X(Spot.location).label("longitude"),
    )
    count_query = select(func.count(Spot.id))

    if search:
        filter_clause = Spot.name.ilike(f"%{search}%")
        base_query = base_query.where(filter_clause)
        count_query = count_query.where(filter_clause)

    total = await db.scalar(count_query)

    result = await db.execute(
        base_query
        .order_by(Spot.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = result.all()

    return (
        [_build_spot_response(row[0], row[1], row[2]) for row in rows],
        total or 0,
    )
