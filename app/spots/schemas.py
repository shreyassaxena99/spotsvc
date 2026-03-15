from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel

from app.db.models import AccessType, SpotCategory
from app.db.noise import NoiseMatrixOutput


class SpotPin(BaseModel):
    id: uuid.UUID
    name: str
    short_address: Optional[str]
    latitude: float
    longitude: float
    category: SpotCategory
    access_type: AccessType
    wifi_available: bool
    power_outlets: bool
    noise_matrix: Optional[NoiseMatrixOutput]
    rating: Optional[float]
    is_open_now: Optional[bool]
    cover_photo: Optional[str]


class SpotDetail(BaseModel):
    id: uuid.UUID
    name: str
    short_address: Optional[str]
    latitude: float
    longitude: float
    category: SpotCategory
    access_type: AccessType
    wifi_available: bool
    power_outlets: bool
    noise_matrix: Optional[NoiseMatrixOutput]
    rating: Optional[float]
    is_open_now: Optional[bool]
    cover_photo: Optional[str]
    # Extended fields
    formatted_address: Optional[str]
    phone_national: Optional[str]
    google_maps_uri: Optional[str]
    website_uri: Optional[str]
    price_level: Optional[str]
    user_rating_count: Optional[int]
    editorial_summary: Optional[str]
    business_status: Optional[str]
    regular_hours: Optional[Any]
    photos: list[Any]
    outdoor_seating: Optional[bool]
    restroom: Optional[bool]
    serves_coffee: Optional[bool]
    allows_dogs: Optional[bool]
    good_for_groups: Optional[bool]
    parking_options: Optional[Any]
    payment_options: Optional[Any]
    accessibility_options: Optional[Any]
    description: Optional[str]
    created_at: datetime
    updated_at: datetime


class SpotsResponse(BaseModel):
    spots: list[SpotPin]
    total: int
