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
    if ss_result.data:
        saved_at = ss_result.data[0]["created_at"]
    else:
        # Fallback: supabase-py may return empty data on conflict — fetch separately
        fallback = (
            supabase.table("saved_spots")
            .select("created_at")
            .eq("user_id", str(user_id))
            .eq("spot_id", str(spot_id))
            .execute()
        )
        saved_at = fallback.data[0]["created_at"]

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


def list_collections(user_id: uuid.UUID) -> CollectionListResponse:
    result = (
        supabase.table("collections")
        .select("*")
        .eq("user_id", str(user_id))
        .order("created_at")
        .execute()
    )
    if not result.data:
        return CollectionListResponse(collections=[])
    collection_ids = [row["id"] for row in result.data]

    cs_result = (
        supabase.table("collection_spots")
        .select("collection_id")
        .in_("collection_id", collection_ids)
        .execute()
    )
    counts: dict[str, int] = {}
    for row in cs_result.data:
        counts[row["collection_id"]] = counts.get(row["collection_id"], 0) + 1

    colls = [
        CollectionResponse(
            id=row["id"],
            name=row["name"],
            is_shareable=row["is_shareable"],
            spot_count=counts.get(row["id"], 0),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in result.data
    ]
    return CollectionListResponse(collections=colls)


def create_collection(
    user_id: uuid.UUID,
    name: str,
    source_collection_id: Optional[uuid.UUID] = None,
) -> CollectionResponse:
    # Step 1: Enforce collection cap
    count_result = (
        supabase.table("collections").select("id").eq("user_id", str(user_id)).execute()
    )
    if len(count_result.data) >= 50:
        raise HTTPException(status_code=422, detail="Collection limit reached (50)")

    # Step 2: Validate source collection before insert (avoids orphaned collection on failure)
    source_spot_ids: list[str] = []
    if source_collection_id is not None:
        src_result = (
            supabase.table("collections")
            .select("*")
            .eq("id", str(source_collection_id))
            .execute()
        )
        if not src_result.data or not src_result.data[0]["is_shareable"]:
            raise HTTPException(status_code=404, detail="Collection not found")
        if src_result.data[0]["user_id"] == str(user_id):
            raise HTTPException(status_code=400, detail="Cannot copy your own collection")
        src_spots = (
            supabase.table("collection_spots")
            .select("spot_id")
            .eq("collection_id", str(source_collection_id))
            .execute()
        )
        source_spot_ids = [row["spot_id"] for row in src_spots.data]

    # Step 3: Insert new collection
    now = datetime.now(timezone.utc).isoformat()
    insert_result = supabase.table("collections").insert({
        "user_id": str(user_id),
        "name": name,
        "is_shareable": False,
        "created_at": now,
        "updated_at": now,
    }).execute()
    new_coll = insert_result.data[0]
    new_coll_id = new_coll["id"]

    spot_count = len(source_spot_ids)

    # Step 4: Copy spots if source provided
    if source_spot_ids:
        try:
            cs_rows = [{"collection_id": new_coll_id, "spot_id": sid} for sid in source_spot_ids]
            supabase.table("collection_spots").upsert(
                cs_rows, on_conflict="collection_id,spot_id", ignore_duplicates=True
            ).execute()
            ss_rows = [{"user_id": str(user_id), "spot_id": sid} for sid in source_spot_ids]
            supabase.table("saved_spots").upsert(
                ss_rows, on_conflict="user_id,spot_id", ignore_duplicates=True
            ).execute()
        except Exception as exc:
            logger.error(
                "create_collection copy failed after inserting collection: %s",
                exc,
                exc_info=True,
            )
            raise HTTPException(
                status_code=500, detail="Failed to copy collection spots"
            )

    return CollectionResponse(
        id=new_coll["id"],
        name=new_coll["name"],
        is_shareable=new_coll["is_shareable"],
        spot_count=spot_count,
        created_at=new_coll["created_at"],
        updated_at=new_coll["updated_at"],
    )


def update_collection(
    user_id: uuid.UUID,
    collection_id: uuid.UUID,
    payload: UpdateCollectionRequest,
) -> CollectionResponse:
    result = (
        supabase.table("collections").select("*").eq("id", str(collection_id)).execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Collection not found")
    if result.data[0]["user_id"] != str(user_id):
        raise HTTPException(status_code=403, detail="Not your collection")

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=422, detail="No fields provided to update")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    update_result = (
        supabase.table("collections").update(updates).eq("id", str(collection_id)).execute()
    )
    updated = update_result.data[0]

    # Note: separate read-after-write; no transaction — count is accurate under normal usage
    cs_result = (
        supabase.table("collection_spots").select("id").eq("collection_id", str(collection_id)).execute()
    )
    spot_count = len(cs_result.data)

    return CollectionResponse(
        id=updated["id"],
        name=updated["name"],
        is_shareable=updated["is_shareable"],
        spot_count=spot_count,
        created_at=updated["created_at"],
        updated_at=updated["updated_at"],
    )


def delete_collection(user_id: uuid.UUID, collection_id: uuid.UUID) -> None:
    result = (
        supabase.table("collections").select("id,user_id").eq("id", str(collection_id)).execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Collection not found")
    if result.data[0]["user_id"] != str(user_id):
        raise HTTPException(status_code=403, detail="Not your collection")
    supabase.table("collections").delete().eq("id", str(collection_id)).execute()


def add_spot_to_collection(
    user_id: uuid.UUID,
    collection_id: uuid.UUID,
    spot_id: uuid.UUID,
) -> SavedSpotResponse:
    # Step 1: Verify collection belongs to user
    coll_result = (
        supabase.table("collections").select("id,user_id").eq("id", str(collection_id)).execute()
    )
    if not coll_result.data:
        raise HTTPException(status_code=404, detail="Collection not found")
    if coll_result.data[0]["user_id"] != str(user_id):
        raise HTTPException(status_code=403, detail="Not your collection")

    # Step 2: Verify spot exists and is active
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

    # Step 3: Upsert into collection_spots
    supabase.table("collection_spots").upsert(
        {"collection_id": str(collection_id), "spot_id": str(spot_id)},
        on_conflict="collection_id,spot_id",
        ignore_duplicates=True,
    ).execute()

    # Step 4: Upsert into saved_spots (implicit save — ignore_duplicates preserves created_at)
    supabase.table("saved_spots").upsert(
        {"user_id": str(user_id), "spot_id": str(spot_id)},
        on_conflict="user_id,spot_id",
        ignore_duplicates=True,
    ).execute()

    # Step 5: Fetch saved_at (separate query since ignore_duplicates may return empty data)
    ss_result = (
        supabase.table("saved_spots")
        .select("created_at")
        .eq("user_id", str(user_id))
        .eq("spot_id", str(spot_id))
        .execute()
    )
    saved_at = ss_result.data[0]["created_at"]

    # Step 6: Fetch all user collection IDs and spot's full collection membership
    user_colls = (
        supabase.table("collections").select("id").eq("user_id", str(user_id)).execute()
    )
    user_collection_ids = [row["id"] for row in user_colls.data]

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


def remove_spot_from_collection(
    user_id: uuid.UUID,
    collection_id: uuid.UUID,
    spot_id: uuid.UUID,
) -> None:
    # Step 1: Verify collection belongs to user
    coll_result = (
        supabase.table("collections").select("id,user_id").eq("id", str(collection_id)).execute()
    )
    if not coll_result.data:
        raise HTTPException(status_code=404, detail="Collection not found")
    if coll_result.data[0]["user_id"] != str(user_id):
        raise HTTPException(status_code=403, detail="Not your collection")

    # Step 2: Delete from collection_spots (idempotent — no-op if not in collection)
    supabase.table("collection_spots").delete().eq(
        "collection_id", str(collection_id)
    ).eq("spot_id", str(spot_id)).execute()


def get_public_collection(collection_id: uuid.UUID) -> PublicCollectionResponse:
    # Step 1: Fetch collection — 404 if not found or not shareable
    result = (
        supabase.table("collections")
        .select("id,name,is_shareable")
        .eq("id", str(collection_id))
        .execute()
    )
    if not result.data or not result.data[0]["is_shareable"]:
        raise HTTPException(status_code=404, detail="Collection not found")
    coll = result.data[0]

    # Step 2: Fetch spots capped at 200, ordered by added_at ASC
    cs_result = (
        supabase.table("collection_spots")
        .select("spot_id")
        .eq("collection_id", str(collection_id))
        .order("added_at")
        .limit(200)
        .execute()
    )
    if not cs_result.data:
        return PublicCollectionResponse(
            id=coll["id"], name=coll["name"], spot_count=0, spots=[]
        )
    spot_ids = [row["spot_id"] for row in cs_result.data]

    # Step 3: Batch fetch spot rows, re-sort to preserve added_at ASC order
    spots_result = supabase.table("spots").select("*").in_("id", spot_ids).execute()
    spot_map = {row["id"]: row for row in spots_result.data}
    spots = [_build_spot_pin(spot_map[sid]) for sid in spot_ids if sid in spot_map]

    return PublicCollectionResponse(
        id=coll["id"],
        name=coll["name"],
        spot_count=len(spots),
        spots=spots,
    )


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
