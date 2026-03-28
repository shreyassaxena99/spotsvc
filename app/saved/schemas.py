from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.spots.schemas import SpotPin


class SaveSpotRequest(BaseModel):
    spot_id: uuid.UUID
    collection_ids: list[uuid.UUID] = []


class CreateCollectionRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    source_collection_id: Optional[uuid.UUID] = None


class UpdateCollectionRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    is_shareable: Optional[bool] = None


class AddSpotToCollectionRequest(BaseModel):
    spot_id: uuid.UUID


class CollectionResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    is_shareable: bool
    spot_count: int
    created_at: datetime
    updated_at: datetime


class CollectionListResponse(BaseModel):
    collections: list[CollectionResponse]


class SavedSpotResponse(BaseModel):
    spot: SpotPin
    saved_at: datetime
    collection_ids: list[uuid.UUID]


class SavedSpotsResponse(BaseModel):
    spots: list[SavedSpotResponse]


class PublicCollectionResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    spot_count: int
    spots: list[SpotPin]
