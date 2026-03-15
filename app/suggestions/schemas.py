from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, model_validator

from app.db.models import AccessType, SpotCategory
from app.db.noise import NoiseMatrixInput


class SubmitSuggestionRequest(BaseModel):
    google_place_id: str
    place_name: str
    place_address: Optional[str] = None
    suggester_name: Optional[str] = None
    suggester_email: Optional[str] = None
    note: Optional[str] = None


class SuggestionResponse(BaseModel):
    id: uuid.UUID
    google_place_id: str
    place_name: str
    place_address: Optional[str]
    suggester_name: Optional[str]
    suggester_email: Optional[str]
    note: Optional[str]
    status: str
    admin_notes: Optional[str]
    created_at: datetime
    updated_at: datetime


class UpdateSuggestionStatusRequest(BaseModel):
    status: Literal["approved", "rejected"]
    admin_notes: Optional[str] = None
    # Required when status == "approved"
    category: Optional[SpotCategory] = None
    access_type: Optional[AccessType] = None
    # Optional curated fields
    noise_matrix: Optional[NoiseMatrixInput] = None
    description: Optional[str] = None

    @model_validator(mode="after")
    def require_curated_fields_on_approval(self) -> UpdateSuggestionStatusRequest:
        if self.status == "approved":
            if self.category is None:
                raise ValueError("category is required when approving a suggestion")
            if self.access_type is None:
                raise ValueError("access_type is required when approving a suggestion")
        return self


class SuggestionListResponse(BaseModel):
    suggestions: list[SuggestionResponse]
    total: int
    page: int
    page_size: int
