from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


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


class SuggestionListResponse(BaseModel):
    suggestions: list[SuggestionResponse]
    total: int
    page: int
    page_size: int
