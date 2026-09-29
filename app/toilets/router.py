from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from app.toilets.schemas import NearestToiletResponse, ToiletDetail, ToiletsResponse
from app.toilets.service import get_toilet, list_toilets, nearest_toilet

router = APIRouter()


@router.get("/nearest", response_model=NearestToiletResponse, tags=["toilets"])
def get_nearest_toilet(
    latitude: float = Query(..., alias="lat"),
    longitude: float = Query(..., alias="lng"),
) -> NearestToiletResponse:
    toilet, walking_distance, walking_minutes = nearest_toilet(latitude, longitude)
    return NearestToiletResponse(
        toilet=toilet,
        walking_distance_meters=walking_distance,
        walking_minutes=walking_minutes,
    )


@router.get("", response_model=ToiletsResponse, tags=["toilets"])
async def get_toilets() -> ToiletsResponse:
    toilets, total = list_toilets()
    return ToiletsResponse(toilets=toilets, total=total)


@router.get("/{toilet_id}", response_model=ToiletDetail, tags=["toilets"])
async def get_toilet_detail(toilet_id: uuid.UUID) -> ToiletDetail:
    return get_toilet(toilet_id)
