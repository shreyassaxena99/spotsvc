from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Optional

from geoalchemy2 import Geography
from sqlalchemy import Boolean, Enum as SAEnum, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class SpotCategory(str, enum.Enum):
    cafe = "cafe"
    gym = "gym"
    hotel_lobby = "hotel_lobby"
    coworking = "coworking"
    library = "library"
    restaurant = "restaurant"
    other = "other"


class AccessType(str, enum.Enum):
    free = "free"
    purchase_required = "purchase_required"
    members_only = "members_only"


class Spot(Base):
    __tablename__ = "spots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # --- Google Places data ---
    google_place_id: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    formatted_address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    short_address: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    # GEOGRAPHY(POINT, 4326) — stored as WGS84; PostGIS expects POINT(lon lat) order
    location: Mapped[object] = mapped_column(
        Geography(geometry_type="POINT", srid=4326), nullable=False
    )
    phone_national: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    phone_international: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    google_maps_uri: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    website_uri: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    price_level: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    user_rating_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    editorial_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    business_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    timezone: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, default="Europe/London"
    )
    regular_hours: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    current_hours: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    photos: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    # Google boolean amenity fields
    outdoor_seating: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    restroom: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    serves_breakfast: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    serves_lunch: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    serves_dinner: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    serves_brunch: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    serves_coffee: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    allows_dogs: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    good_for_groups: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    dine_in: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    takeout: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    delivery: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    reservable: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # Google JSONB option objects
    parking_options: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    payment_options: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    accessibility_options: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    # --- Curated fields (set by admin) ---
    category: Mapped[SpotCategory] = mapped_column(
        SAEnum(SpotCategory, name="spot_category", create_type=False), nullable=False
    )
    access_type: Mapped[AccessType] = mapped_column(
        SAEnum(AccessType, name="access_type", create_type=False), nullable=False
    )
    wifi_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    power_outlets: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    noise_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    admin_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # References auth.users(id) — FK enforced in DB schema, not ORM
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    google_data_updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
