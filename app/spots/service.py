from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

import pytz
from fastapi import HTTPException

from app.db.database import supabase
from app.db.models import SpotCategory
from app.spots.schemas import SpotDetail, SpotPin

logger = logging.getLogger(__name__)


def compute_is_open_now(regular_hours: Optional[dict], timezone_str: Optional[str]) -> Optional[bool]:
    if not regular_hours or not timezone_str:
        return None
    periods = regular_hours.get("periods")
    if not periods:
        return None
    try:
        tz = pytz.timezone(timezone_str)
        now = datetime.now(tz)
        # Python weekday: Monday=0; Google weekday: Sunday=0
        google_day = (now.weekday() + 1) % 7
        current_minutes = now.hour * 60 + now.minute
        for period in periods:
            open_info = period.get("open", {})
            close_info = period.get("close")
            if open_info.get("day") != google_day:
                continue
            open_minutes = open_info.get("hour", 0) * 60 + open_info.get("minute", 0)
            if close_info is None:
                # Open 24 hours
                return True
            close_day = close_info.get("day", google_day)
            close_minutes = close_info.get("hour", 0) * 60 + close_info.get("minute", 0)
            if close_day == google_day:
                if open_minutes <= current_minutes < close_minutes:
                    return True
            else:
                # Closes after midnight — treat as open until close_minutes past midnight
                if current_minutes >= open_minutes:
                    return True
        return False
    except Exception as exc:
        logger.warning("compute_is_open_now failed: %s", exc)
        return None


def _extract_cover_photo(photos: Optional[list]) -> Optional[str]:
    if not photos:
        return None
    return photos[0] if isinstance(photos[0], str) else None


def _build_spot_pin(row: dict) -> SpotPin:
    photos = row.get("photos") or []
    return SpotPin(
        id=row["id"],
        name=row["name"],
        short_address=row.get("short_address"),
        latitude=row["latitude"],
        longitude=row["longitude"],
        category=row["category"],
        access_type=row["access_type"],
        wifi_available=row.get("wifi_available", True),
        power_outlets=row.get("power_outlets", True),
        noise_level=row.get("noise_level"),
        rating=row.get("rating"),
        is_open_now=compute_is_open_now(row.get("regular_hours"), row.get("timezone")),
        cover_photo=_extract_cover_photo(photos),
    )


def _build_spot_detail(row: dict) -> SpotDetail:
    photos = row.get("photos") or []
    return SpotDetail(
        id=row["id"],
        name=row["name"],
        short_address=row.get("short_address"),
        latitude=row["latitude"],
        longitude=row["longitude"],
        category=row["category"],
        access_type=row["access_type"],
        wifi_available=row.get("wifi_available", True),
        power_outlets=row.get("power_outlets", True),
        noise_level=row.get("noise_level"),
        rating=row.get("rating"),
        is_open_now=compute_is_open_now(row.get("regular_hours"), row.get("timezone")),
        cover_photo=_extract_cover_photo(photos),
        formatted_address=row.get("formatted_address"),
        phone_national=row.get("phone_national"),
        google_maps_uri=row.get("google_maps_uri"),
        website_uri=row.get("website_uri"),
        price_level=row.get("price_level"),
        user_rating_count=row.get("user_rating_count"),
        editorial_summary=row.get("editorial_summary"),
        business_status=row.get("business_status"),
        regular_hours=row.get("regular_hours"),
        photos=photos,
        outdoor_seating=row.get("outdoor_seating"),
        restroom=row.get("restroom"),
        serves_coffee=row.get("serves_coffee"),
        allows_dogs=row.get("allows_dogs"),
        good_for_groups=row.get("good_for_groups"),
        parking_options=row.get("parking_options"),
        payment_options=row.get("payment_options"),
        accessibility_options=row.get("accessibility_options"),
        description=row.get("description"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def list_spots(
    category: Optional[SpotCategory] = None,
    is_open_now_filter: Optional[bool] = None,
) -> tuple[list[SpotPin], int]:
    query = supabase.table("spots").select("*").eq("is_active", True)
    if category is not None:
        query = query.eq("category", category.value)
    result = query.execute()
    pins = [_build_spot_pin(row) for row in result.data]
    if is_open_now_filter is not None:
        pins = [p for p in pins if p.is_open_now == is_open_now_filter]
    return pins, len(pins)


def get_spot(spot_id: uuid.UUID) -> SpotDetail:
    result = (
        supabase.table("spots")
        .select("*")
        .eq("id", str(spot_id))
        .eq("is_active", True)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Spot not found")
    return _build_spot_detail(result.data[0])
