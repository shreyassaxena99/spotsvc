from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.toilets.schemas import ToiletDetail, ToiletsResponse
from app.toilets.service import get_toilet, list_toilets

router = APIRouter()


@router.get("", response_model=ToiletsResponse, tags=["toilets"])
async def get_toilets() -> ToiletsResponse:
    toilets, total = list_toilets()
    return ToiletsResponse(toilets=toilets, total=total)


@router.get("/{toilet_id}", response_model=ToiletDetail, tags=["toilets"])
async def get_toilet_detail(toilet_id: uuid.UUID) -> ToiletDetail:
    return get_toilet(toilet_id)
