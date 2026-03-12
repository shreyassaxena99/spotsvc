from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, SecretStr

from app.db.models import AccessType, SpotCategory
from app.google_places.schemas import PlaceDetails, PlaceSuggestion


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

class ValidateRequest(BaseModel):
    password: SecretStr


class ValidateResponse(BaseModel):
    valid: bool


class CreateSpotRequest(BaseModel):
    google_place_id: str = Field(..., description="Google Place ID obtained from autocomplete")
    category: SpotCategory
    access_type: AccessType
    wifi_available: bool = True
    power_outlets: bool = True
    noise_level: Optional[Literal["quiet", "moderate", "lively"]] = None
    description: Optional[str] = Field(None, description="Editorial description shown to users")
    admin_notes: Optional[str] = Field(None, description="Internal team notes, not shown to users")


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------

class SpotResponse(BaseModel):
    id: uuid.UUID
    google_place_id: str
    name: str
    formatted_address: Optional[str]
    short_address: Optional[str]
    latitude: float
    longitude: float
    phone_national: Optional[str]
    phone_international: Optional[str]
    google_maps_uri: Optional[str]
    website_uri: Optional[str]
    price_level: Optional[str]
    rating: Optional[float]
    user_rating_count: Optional[int]
    editorial_summary: Optional[str]
    business_status: Optional[str]
    timezone: Optional[str]
    regular_hours: Optional[Any]
    current_hours: Optional[Any]
    photos: list[Any]
    outdoor_seating: Optional[bool]
    restroom: Optional[bool]
    serves_breakfast: Optional[bool]
    serves_lunch: Optional[bool]
    serves_dinner: Optional[bool]
    serves_brunch: Optional[bool]
    serves_coffee: Optional[bool]
    allows_dogs: Optional[bool]
    good_for_groups: Optional[bool]
    dine_in: Optional[bool]
    takeout: Optional[bool]
    delivery: Optional[bool]
    reservable: Optional[bool]
    parking_options: Optional[Any]
    payment_options: Optional[Any]
    accessibility_options: Optional[Any]
    # Curated fields
    category: SpotCategory
    access_type: AccessType
    wifi_available: bool
    power_outlets: bool
    noise_level: Optional[str]
    description: Optional[str]
    admin_notes: Optional[str]
    is_active: bool
    google_data_updated_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class SpotListResponse(BaseModel):
    spots: list[SpotResponse]
    total: int
    page: int
    page_size: int


class AutocompleteResponse(BaseModel):
    suggestions: list[PlaceSuggestion]


class GooglePlacePreviewResponse(BaseModel):
    place: PlaceDetails
