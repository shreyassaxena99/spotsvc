from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response

from app.dependencies import get_current_user
from app.saved.schemas import (
    AddSpotToCollectionRequest,
    CollectionListResponse,
    CollectionResponse,
    CreateCollectionRequest,
    PublicCollectionResponse,
    SavedSpotResponse,
    SavedSpotsResponse,
    SaveSpotRequest,
    UpdateCollectionRequest,
)
from app.saved.service import (
    add_spot_to_collection,
    create_collection,
    delete_collection,
    get_public_collection,
    list_collections,
    list_saved_spots,
    remove_spot_from_collection,
    save_spot,
    unsave_spot,
    update_collection,
)

router = APIRouter(tags=["saved"])


@router.get("/me/saved-spots", response_model=SavedSpotsResponse)
async def get_saved_spots(
    collection_id: Optional[uuid.UUID] = Query(None),
    user: dict = Depends(get_current_user),
) -> SavedSpotsResponse:
    """List saved spots. Filter by collection_id to see only spots in that collection."""
    return list_saved_spots(uuid.UUID(user["user_id"]), collection_id)


@router.post("/me/saved-spots", response_model=SavedSpotResponse)
async def post_saved_spot(
    payload: SaveSpotRequest,
    user: dict = Depends(get_current_user),
) -> SavedSpotResponse:
    """Save a spot. Optionally add to one or more collections in the same call."""
    return save_spot(uuid.UUID(user["user_id"]), payload.spot_id, payload.collection_ids)


@router.delete("/me/saved-spots/{spot_id}")
async def delete_saved_spot(
    spot_id: uuid.UUID,
    user: dict = Depends(get_current_user),
) -> Response:
    """Unsave a spot. Also removes it from all of the user's collections."""
    unsave_spot(uuid.UUID(user["user_id"]), spot_id)
    return Response(status_code=204)


@router.get("/me/collections", response_model=CollectionListResponse)
async def get_collections(
    user: dict = Depends(get_current_user),
) -> CollectionListResponse:
    """List all of the user's collections with spot counts."""
    return list_collections(uuid.UUID(user["user_id"]))


@router.post("/me/collections", response_model=CollectionResponse, status_code=201)
async def post_collection(
    payload: CreateCollectionRequest,
    user: dict = Depends(get_current_user),
) -> CollectionResponse:
    """Create a collection. Use source_collection_id to copy a shareable collection."""
    return create_collection(uuid.UUID(user["user_id"]), payload.name, payload.description, payload.source_collection_id)


@router.patch("/me/collections/{collection_id}", response_model=CollectionResponse)
async def patch_collection(
    collection_id: uuid.UUID,
    payload: UpdateCollectionRequest,
    user: dict = Depends(get_current_user),
) -> CollectionResponse:
    """Rename or toggle is_shareable on a collection."""
    return update_collection(uuid.UUID(user["user_id"]), collection_id, payload)


@router.delete("/me/collections/{collection_id}")
async def delete_collection_route(
    collection_id: uuid.UUID,
    user: dict = Depends(get_current_user),
) -> Response:
    """Delete a collection. Spots remain saved."""
    delete_collection(uuid.UUID(user["user_id"]), collection_id)
    return Response(status_code=204)


@router.post("/me/collections/{collection_id}/spots", response_model=SavedSpotResponse)
async def post_spot_to_collection(
    collection_id: uuid.UUID,
    payload: AddSpotToCollectionRequest,
    user: dict = Depends(get_current_user),
) -> SavedSpotResponse:
    """Add a spot to a collection. Also saves the spot if not already saved."""
    return add_spot_to_collection(uuid.UUID(user["user_id"]), collection_id, payload.spot_id)


@router.delete("/me/collections/{collection_id}/spots/{spot_id}")
async def delete_spot_from_collection(
    collection_id: uuid.UUID,
    spot_id: uuid.UUID,
    user: dict = Depends(get_current_user),
) -> Response:
    """Remove a spot from a collection. Does not unsave the spot."""
    remove_spot_from_collection(uuid.UUID(user["user_id"]), collection_id, spot_id)
    return Response(status_code=204)


@router.get("/collections/{collection_id}", response_model=PublicCollectionResponse)
async def get_public_collection_route(
    collection_id: uuid.UUID,
) -> PublicCollectionResponse:
    """View a shareable collection and its spots. No auth required. Returns 404 if not shareable."""
    return get_public_collection(collection_id)
