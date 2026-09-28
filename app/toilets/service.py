from __future__ import annotations

import uuid

from fastapi import HTTPException

from app.db.database import supabase
from app.toilets.schemas import ToiletDetail, ToiletPin

# Approximate M25 envelope. Keeping this filter in the API preserves the full
# UK source dataset in Supabase and lets us tighten or expand the geography
# without running a destructive reimport.
LONDON_MIN_LATITUDE = 51.25
LONDON_MAX_LATITUDE = 51.75
LONDON_MIN_LONGITUDE = -0.55
LONDON_MAX_LONGITUDE = 0.35


def _london_query(table: str):
    return (
        supabase.table(table)
        .eq("source", "toilet_map")
        .eq("is_active", True)
        .gte("latitude", LONDON_MIN_LATITUDE)
        .lte("latitude", LONDON_MAX_LATITUDE)
        .gte("longitude", LONDON_MIN_LONGITUDE)
        .lte("longitude", LONDON_MAX_LONGITUDE)
    )


def _build_toilet_pin(row: dict) -> ToiletPin:
    return ToiletPin(
        id=row["id"],
        name=row.get("name"),
        short_address=row.get("short_address"),
        area_name=row.get("area_name"),
        latitude=row["latitude"],
        longitude=row["longitude"],
        accessible=row.get("accessible"),
        baby_change=row.get("baby_change"),
        men=row.get("men"),
        women=row.get("women"),
        all_gender=row.get("all_gender"),
        is_free=row.get("is_free"),
    )


def _build_toilet_detail(row: dict) -> ToiletDetail:
    return ToiletDetail(
        **_build_toilet_pin(row).model_dump(),
        description=row.get("description"),
        formatted_address=row.get("formatted_address"),
        children=row.get("children"),
        urinal_only=row.get("urinal_only"),
        attended=row.get("attended"),
        automatic=row.get("automatic"),
        radar_key_required=row.get("radar_key_required"),
        payment_details=row.get("payment_details"),
        regular_hours=row.get("regular_hours"),
        current_hours=row.get("current_hours"),
        source_updated_at=row.get("source_updated_at"),
        source_verified_at=row.get("source_verified_at"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def list_toilets() -> tuple[list[ToiletPin], int]:
    result = _london_query("toilets").select(
        "id,name,short_address,area_name,latitude,longitude,"
        "accessible,baby_change,men,women,all_gender,is_free"
    ).execute()
    toilets = [_build_toilet_pin(row) for row in (result.data or [])]
    return toilets, len(toilets)


def get_toilet(toilet_id: uuid.UUID) -> ToiletDetail:
    result = _london_query("toilets").select("*").eq("id", str(toilet_id)).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Toilet not found")
    return _build_toilet_detail(result.data[0])
