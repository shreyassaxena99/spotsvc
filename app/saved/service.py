from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from app.db.database import supabase
from app.saved.schemas import (
    CollectionListResponse,
    CollectionResponse,
    PublicCollectionResponse,
    SavedSpotResponse,
    SavedSpotsResponse,
    UpdateCollectionRequest,
)
from app.spots.service import _build_spot_pin

logger = logging.getLogger(__name__)


def save_spot(
    user_id: uuid.UUID,
    spot_id: uuid.UUID,
    collection_ids: list[uuid.UUID],
) -> SavedSpotResponse:
    # Step 1: Verify spot exists and is active
    spot_result = (
        supabase.table("spots")
        .select("*")
        .eq("id", str(spot_id))
        .eq("is_active", True)
        .execute()
    )
    if not spot_result.data:
        raise HTTPException(status_code=404, detail="Spot not found")
    spot_row = spot_result.data[0]

    # Step 2: Validate all collection_ids in one query (skip if empty)
    if collection_ids:
        cid_strs = [str(cid) for cid in collection_ids]
        coll_check = (
            supabase.table("collections")
            .select("id")
            .in_("id", cid_strs)
            .eq("user_id", str(user_id))
            .execute()
        )
        if len(coll_check.data) != len(collection_ids):
            raise HTTPException(
                status_code=403,
                detail="One or more collection IDs are invalid or not owned by you",
            )

    # Step 3: Upsert into saved_spots (no created_at — preserves existing on conflict)
    ss_result = (
        supabase.table("saved_spots")
        .upsert({"user_id": str(user_id), "spot_id": str(spot_id)}, on_conflict="user_id,spot_id")
        .execute()
    )
    saved_at = ss_result.data[0]["created_at"]

    # Step 4: Bulk upsert into collection_spots (single call, not a loop)
    if collection_ids:
        cs_rows = [{"collection_id": str(cid), "spot_id": str(spot_id)} for cid in collection_ids]
        supabase.table("collection_spots").upsert(
            cs_rows, on_conflict="collection_id,spot_id", ignore_duplicates=True
        ).execute()

    # Step 5: Fetch all user collection IDs
    user_colls_result = (
        supabase.table("collections").select("id").eq("user_id", str(user_id)).execute()
    )
    user_collection_ids = [row["id"] for row in user_colls_result.data]

    # Step 6: Fetch which of those collections this spot belongs to
    response_collection_ids: list[uuid.UUID] = []
    if user_collection_ids:
        cs_result = (
            supabase.table("collection_spots")
            .select("collection_id")
            .in_("collection_id", user_collection_ids)
            .eq("spot_id", str(spot_id))
            .execute()
        )
        response_collection_ids = [uuid.UUID(row["collection_id"]) for row in cs_result.data]

    return SavedSpotResponse(
        spot=_build_spot_pin(spot_row),
        saved_at=saved_at,
        collection_ids=response_collection_ids,
    )


def list_saved_spots(
    user_id: uuid.UUID,
    collection_id: Optional[uuid.UUID] = None,
) -> SavedSpotsResponse:
    if collection_id is not None:
        return _list_saved_spots_filtered(user_id, collection_id)
    return _list_saved_spots_all(user_id)


def _list_saved_spots_filtered(
    user_id: uuid.UUID,
    collection_id: uuid.UUID,
) -> SavedSpotsResponse:
    # Step 1: Verify collection ownership
    coll_result = (
        supabase.table("collections")
        .select("id,user_id")
        .eq("id", str(collection_id))
        .execute()
    )
    if not coll_result.data:
        raise HTTPException(status_code=404, detail="Collection not found")
    if coll_result.data[0]["user_id"] != str(user_id):
        raise HTTPException(status_code=403, detail="Not your collection")

    # Step 2: Fetch all user's collection IDs (for full collection_ids in response)
    user_colls = (
        supabase.table("collections").select("id").eq("user_id", str(user_id)).execute()
    )
    user_collection_ids = [row["id"] for row in user_colls.data]

    # Step 3: Fetch spots in this collection, ordered by added_at ASC
    cs_result = (
        supabase.table("collection_spots")
        .select("spot_id")
        .eq("collection_id", str(collection_id))
        .order("added_at")
        .execute()
    )
    if not cs_result.data:
        return SavedSpotsResponse(spots=[])
    spot_ids = [row["spot_id"] for row in cs_result.data]

    # Step 4: Batch fetch spot rows, re-sort to added_at ASC order
    spots_result = supabase.table("spots").select("*").in_("id", spot_ids).execute()
    spot_map = {row["id"]: row for row in spots_result.data}

    # Step 5: Fetch saved_at timestamps
    ss_result = (
        supabase.table("saved_spots")
        .select("spot_id,created_at")
        .eq("user_id", str(user_id))
        .in_("spot_id", spot_ids)
        .execute()
    )
    saved_at_map = {row["spot_id"]: row["created_at"] for row in ss_result.data}

    # Step 6: Fetch full collection membership across all user's collections
    cs_all: dict[str, list[uuid.UUID]] = {}
    if user_collection_ids:
        cs_all_result = (
            supabase.table("collection_spots")
            .select("collection_id,spot_id")
            .in_("collection_id", user_collection_ids)
            .execute()
        )
        for row in cs_all_result.data:
            cs_all.setdefault(row["spot_id"], []).append(uuid.UUID(row["collection_id"]))

    # Step 7: Build response preserving added_at ASC order from step 3
    spots = []
    for sid in spot_ids:
        row = spot_map.get(sid)
        if row is None:
            continue
        spots.append(
            SavedSpotResponse(
                spot=_build_spot_pin(row),
                saved_at=saved_at_map[sid],
                collection_ids=cs_all.get(sid, []),
            )
        )
    return SavedSpotsResponse(spots=spots)


def _list_saved_spots_all(user_id: uuid.UUID) -> SavedSpotsResponse:
    # Step 1: Fetch saved spots ordered by created_at DESC
    ss_result = (
        supabase.table("saved_spots")
        .select("spot_id,created_at")
        .eq("user_id", str(user_id))
        .order("created_at", desc=True)
        .execute()
    )
    if not ss_result.data:
        return SavedSpotsResponse(spots=[])
    spot_ids = [row["spot_id"] for row in ss_result.data]
    saved_at_map = {row["spot_id"]: row["created_at"] for row in ss_result.data}

    # Step 2: Fetch all user's collection IDs
    user_colls = (
        supabase.table("collections").select("id").eq("user_id", str(user_id)).execute()
    )
    user_collection_ids = [row["id"] for row in user_colls.data]

    # Step 3: Batch fetch spot rows, re-sort to created_at DESC order
    spots_result = supabase.table("spots").select("*").in_("id", spot_ids).execute()
    spot_map = {row["id"]: row for row in spots_result.data}

    # Step 4: Fetch collection membership for all user's collections
    cs_all: dict[str, list[uuid.UUID]] = {}
    if user_collection_ids:
        cs_all_result = (
            supabase.table("collection_spots")
            .select("collection_id,spot_id")
            .in_("collection_id", user_collection_ids)
            .execute()
        )
        for row in cs_all_result.data:
            cs_all.setdefault(row["spot_id"], []).append(uuid.UUID(row["collection_id"]))

    # Step 5: Build response preserving created_at DESC order from step 1
    spots = []
    for sid in spot_ids:
        row = spot_map.get(sid)
        if row is None:
            continue
        spots.append(
            SavedSpotResponse(
                spot=_build_spot_pin(row),
                saved_at=saved_at_map[sid],
                collection_ids=cs_all.get(sid, []),
            )
        )
    return SavedSpotsResponse(spots=spots)


def unsave_spot(user_id: uuid.UUID, spot_id: uuid.UUID) -> None:
    # Step 1: Verify the spot is saved (404 before any destructive write)
    check = (
        supabase.table("saved_spots")
        .select("id")
        .eq("user_id", str(user_id))
        .eq("spot_id", str(spot_id))
        .execute()
    )
    if not check.data:
        raise HTTPException(status_code=404, detail="Spot is not saved")

    # Step 2: Fetch all user collection IDs
    colls = supabase.table("collections").select("id").eq("user_id", str(user_id)).execute()
    collection_ids = [row["id"] for row in colls.data]

    # Step 3: Delete from collection_spots (skip if user has no collections)
    if len(collection_ids) > 0:
        supabase.table("collection_spots").delete().in_(
            "collection_id", collection_ids
        ).eq("spot_id", str(spot_id)).execute()

    # Step 4: Delete from saved_spots
    supabase.table("saved_spots").delete().eq("user_id", str(user_id)).eq(
        "spot_id", str(spot_id)
    ).execute()
