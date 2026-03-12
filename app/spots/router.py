from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter

from app.db.models import SpotCategory
from app.spots.schemas import SpotDetail, SpotsResponse
from app.spots.service import get_spot, list_spots

router = APIRouter()


@router.get("", response_model=SpotsResponse, tags=["spots"])
async def get_spots(
    category: Optional[SpotCategory] = None,
    is_open_now: Optional[bool] = None,
) -> SpotsResponse:
    pins, total = list_spots(category=category, is_open_now_filter=is_open_now)
    return SpotsResponse(spots=pins, total=total)


@router.get("/{spot_id}", response_model=SpotDetail, tags=["spots"])
async def get_spot_detail(spot_id: uuid.UUID) -> SpotDetail:
    return get_spot(spot_id)
