from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Query

from app.suggestions.schemas import (
    SuggestionListResponse,
    SuggestionResponse,
    SubmitSuggestionRequest,
    UpdateSuggestionStatusRequest,
)
from app.suggestions.service import list_suggestions, submit_suggestion, update_suggestion_status

router = APIRouter()


@router.post("/suggestions", response_model=SuggestionResponse, status_code=201, tags=["suggestions"])
async def suggest_spot(payload: SubmitSuggestionRequest):
    """Submit a public suggestion for a new spot. No authentication required."""
    return submit_suggestion(payload)


@router.get("/admin/suggestions", response_model=SuggestionListResponse, tags=["admin"])
async def list_admin_suggestions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, description="Filter by status: pending, approved, rejected"),
):
    """List all spot suggestions. Paginated, with optional status filter."""
    suggestions, total = list_suggestions(page, page_size, status)
    return SuggestionListResponse(suggestions=suggestions, total=total, page=page, page_size=page_size)


@router.patch("/admin/suggestions/{suggestion_id}", response_model=SuggestionResponse, tags=["admin"])
async def update_suggestion(
    suggestion_id: uuid.UUID,
    payload: UpdateSuggestionStatusRequest,
):
    """Approve or reject a spot suggestion."""
    return update_suggestion_status(suggestion_id, payload.status, payload.admin_notes)
