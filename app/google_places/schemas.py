from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class PlaceSuggestion(BaseModel):
    place_id: str
    text: str
    secondary_text: Optional[str] = None


class PlaceDetails(BaseModel):
    place_id: str
    name: str
    formatted_address: Optional[str] = None
    short_address: Optional[str] = None
    latitude: float
    longitude: float
    phone_national: Optional[str] = None
    phone_international: Optional[str] = None
    google_maps_uri: Optional[str] = None
    website_uri: Optional[str] = None
    price_level: Optional[str] = None
    rating: Optional[float] = None
    user_rating_count: Optional[int] = None
    editorial_summary: Optional[str] = None
    business_status: Optional[str] = None
    timezone: Optional[str] = None
    regular_hours: Optional[dict[str, Any]] = None
    current_hours: Optional[dict[str, Any]] = None
    photo_references: list[str] = []
    outdoor_seating: Optional[bool] = None
    restroom: Optional[bool] = None
    serves_breakfast: Optional[bool] = None
    serves_lunch: Optional[bool] = None
    serves_dinner: Optional[bool] = None
    serves_brunch: Optional[bool] = None
    serves_coffee: Optional[bool] = None
    allows_dogs: Optional[bool] = None
    good_for_groups: Optional[bool] = None
    dine_in: Optional[bool] = None
    takeout: Optional[bool] = None
    delivery: Optional[bool] = None
    reservable: Optional[bool] = None
    parking_options: Optional[dict[str, Any]] = None
    payment_options: Optional[dict[str, Any]] = None
    accessibility_options: Optional[dict[str, Any]] = None
