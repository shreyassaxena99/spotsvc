from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.saved.schemas import SavedSpotResponse, SavedSpotsResponse


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _chain(data=None):
    m = MagicMock()
    m.execute.return_value = MagicMock(data=data if data is not None else [])
    for method in ("select", "eq", "in_", "order", "limit",
                   "upsert", "insert", "update", "delete"):
        getattr(m, method).return_value = m
    return m


def _tables(**by_name):
    default = _chain()
    def dispatch(name):
        return by_name.get(name, default)
    return dispatch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

USER_ID = uuid.uuid4()
SPOT_ID = uuid.uuid4()
COLL_ID = uuid.uuid4()

SPOT_ROW = {
    "id": str(SPOT_ID),
    "name": "Test Cafe",
    "short_address": "1 Test St",
    "latitude": 51.5,
    "longitude": -0.1,
    "category": "cafe",
    "access_type": "free",
    "wifi_available": True,
    "power_outlets": True,
    "noise_matrix": None,
    "rating": 4.2,
    "regular_hours": None,
    "timezone": "Europe/London",
    "photos": [],
    "is_active": True,
}

SAVED_ROW = {
    "id": str(uuid.uuid4()),
    "user_id": str(USER_ID),
    "spot_id": str(SPOT_ID),
    "created_at": "2026-03-15T10:00:00+00:00",
}

COLL_ROW = {
    "id": str(COLL_ID),
    "user_id": str(USER_ID),
    "name": "My List",
    "is_shareable": False,
    "created_at": "2026-03-15T09:00:00+00:00",
    "updated_at": "2026-03-15T09:00:00+00:00",
}


# ---------------------------------------------------------------------------
# save_spot
# ---------------------------------------------------------------------------

class TestSaveSpot:
    @patch("app.saved.service.supabase")
    def test_spot_not_found_raises_404(self, mock_sb):
        mock_sb.table.return_value = _chain(data=[])
        from app.saved.service import save_spot
        with pytest.raises(HTTPException) as exc:
            save_spot(USER_ID, SPOT_ID, [])
        assert exc.value.status_code == 404

    @patch("app.saved.service.supabase")
    def test_inactive_spot_raises_404(self, mock_sb):
        inactive_row = {**SPOT_ROW, "is_active": False}
        mock_sb.table.return_value = _chain(data=[])  # eq("is_active", True) returns nothing
        from app.saved.service import save_spot
        with pytest.raises(HTTPException) as exc:
            save_spot(USER_ID, SPOT_ID, [])
        assert exc.value.status_code == 404

    @patch("app.saved.service.supabase")
    def test_unowned_collection_raises_403(self, mock_sb):
        # spots returns SPOT_ROW, collections ownership check returns 0 rows
        call_count = {"n": 0}
        def dispatch(name):
            if name == "spots":
                return _chain(data=[SPOT_ROW])
            if name == "collections":
                return _chain(data=[])  # validates 0 IDs — mismatch → 403
            return _chain()
        mock_sb.table.side_effect = dispatch
        from app.saved.service import save_spot
        with pytest.raises(HTTPException) as exc:
            save_spot(USER_ID, SPOT_ID, [COLL_ID])
        assert exc.value.status_code == 403

    @patch("app.saved.service.supabase")
    def test_save_spot_no_collections_returns_saved_spot_response(self, mock_sb):
        # Call sequence: spots, saved_spots upsert, collections (user list)
        # When collection_ids is empty, skip collection validation and bulk upsert
        responses = {
            "spots": _chain(data=[SPOT_ROW]),
            "saved_spots": _chain(data=[SAVED_ROW]),
            "collections": _chain(data=[]),  # user has no collections
            "collection_spots": _chain(data=[]),
        }
        mock_sb.table.side_effect = _tables(**responses)
        from app.saved.service import save_spot
        result = save_spot(USER_ID, SPOT_ID, [])
        assert isinstance(result, SavedSpotResponse)
        assert str(result.spot.id) == str(SPOT_ID)
        assert result.collection_ids == []


# ---------------------------------------------------------------------------
# unsave_spot
# ---------------------------------------------------------------------------

class TestUnsaveSpot:
    @patch("app.saved.service.supabase")
    def test_spot_not_saved_raises_404(self, mock_sb):
        mock_sb.table.return_value = _chain(data=[])
        from app.saved.service import unsave_spot
        with pytest.raises(HTTPException) as exc:
            unsave_spot(USER_ID, SPOT_ID)
        assert exc.value.status_code == 404

    @patch("app.saved.service.supabase")
    def test_unsave_succeeds_with_no_collections(self, mock_sb):
        responses = {
            "saved_spots": _chain(data=[SAVED_ROW]),
            "collections": _chain(data=[]),
        }
        mock_sb.table.side_effect = _tables(**responses)
        from app.saved.service import unsave_spot
        # Should not raise
        unsave_spot(USER_ID, SPOT_ID)
