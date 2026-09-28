from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class ToiletPin(BaseModel):
    id: uuid.UUID
    name: Optional[str]
    short_address: Optional[str]
    area_name: Optional[str]
    latitude: float
    longitude: float
    accessible: Optional[bool]
    baby_change: Optional[bool]
    men: Optional[bool]
    women: Optional[bool]
    all_gender: Optional[bool]
    is_free: Optional[bool]


class ToiletDetail(ToiletPin):
    description: Optional[str]
    formatted_address: Optional[str]
    children: Optional[bool]
    urinal_only: Optional[bool]
    attended: Optional[bool]
    automatic: Optional[bool]
    radar_key_required: Optional[bool]
    payment_details: Optional[str]
    regular_hours: Optional[Any]
    current_hours: Optional[Any]
    source_updated_at: Optional[datetime]
    source_verified_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class ToiletsResponse(BaseModel):
    toilets: list[ToiletPin]
    total: int
