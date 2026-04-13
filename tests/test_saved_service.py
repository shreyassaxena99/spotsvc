from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.saved.schemas import CollectionListResponse, CollectionResponse, PublicCollectionResponse, SavedSpotResponse, SavedSpotsResponse


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
DEFAULT_COLL_ID = uuid.uuid4()

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
    "is_default": False,
    "created_at": "2026-03-15T09:00:00+00:00",
    "updated_at": "2026-03-15T09:00:00+00:00",
}

DEFAULT_COLL_ROW = {
    "id": str(DEFAULT_COLL_ID),
    "user_id": str(USER_ID),
    "name": "Favourite Spots",
    "is_shareable": False,
    "is_default": True,
    "created_at": "2026-03-15T08:00:00+00:00",
    "updated_at": "2026-03-15T08:00:00+00:00",
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

    @patch("app.saved.service.supabase")
    def test_resave_spot_uses_fallback_for_saved_at(self, mock_sb):
        # saved_spots upsert returns empty data (conflict case), fallback SELECT returns saved_at
        ss_upsert = _chain(data=[])   # empty on conflict
        ss_fallback = _chain(data=[SAVED_ROW])  # fallback fetch
        ss_call_count = {"n": 0}
        def dispatch(name):
            if name == "spots":
                return _chain(data=[SPOT_ROW])
            if name == "saved_spots":
                ss_call_count["n"] += 1
                if ss_call_count["n"] == 1:
                    return ss_upsert  # upsert — empty
                return ss_fallback    # fallback SELECT
            if name == "collections":
                return _chain(data=[])
            return _chain()
        mock_sb.table.side_effect = dispatch
        from app.saved.service import save_spot
        result = save_spot(USER_ID, SPOT_ID, [])
        assert isinstance(result, SavedSpotResponse)
        assert result.saved_at is not None

    @patch("app.saved.service.supabase")
    def test_collection_ids_excludes_default_collection(self, mock_sb):
        # User has a default collection; spot is auto-added to it.
        # The default collection must NOT appear in collection_ids on the response.
        def dispatch(name):
            if name == "spots":
                return _chain(data=[SPOT_ROW])
            if name == "saved_spots":
                return _chain(data=[SAVED_ROW])
            if name == "collections":
                return _chain(data=[DEFAULT_COLL_ROW])
            if name == "collection_spots":
                # Spot is in the default collection
                return _chain(data=[{"collection_id": str(DEFAULT_COLL_ID)}])
            return _chain()
        mock_sb.table.side_effect = dispatch
        from app.saved.service import save_spot
        result = save_spot(USER_ID, SPOT_ID, [])
        assert DEFAULT_COLL_ID not in result.collection_ids

    @patch("app.saved.service.supabase")
    def test_auto_adds_spot_to_default_collection(self, mock_sb):
        # When saving a spot, collection_spots should be upserted for the default collection.
        cs_mock = _chain(data=[])
        upserted_rows: list = []
        def cs_upsert(rows, **kwargs):
            upserted_rows.extend(rows if isinstance(rows, list) else [rows])
            return cs_mock
        cs_mock.upsert.side_effect = cs_upsert

        def dispatch(name):
            if name == "spots":
                return _chain(data=[SPOT_ROW])
            if name == "saved_spots":
                return _chain(data=[SAVED_ROW])
            if name == "collections":
                return _chain(data=[DEFAULT_COLL_ROW])
            if name == "collection_spots":
                return cs_mock
            return _chain()
        mock_sb.table.side_effect = dispatch
        from app.saved.service import save_spot
        save_spot(USER_ID, SPOT_ID, [])
        collection_ids_upserted = [r.get("collection_id") for r in upserted_rows]
        assert str(DEFAULT_COLL_ID) in collection_ids_upserted


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


# ---------------------------------------------------------------------------
# list_saved_spots
# ---------------------------------------------------------------------------

class TestListSavedSpots:
    @patch("app.saved.service.supabase")
    def test_unfiltered_empty_returns_empty_response(self, mock_sb):
        mock_sb.table.return_value = _chain(data=[])
        from app.saved.service import list_saved_spots
        result = list_saved_spots(USER_ID)
        assert isinstance(result, SavedSpotsResponse)
        assert result.spots == []

    @patch("app.saved.service.supabase")
    def test_filtered_collection_not_found_raises_404(self, mock_sb):
        mock_sb.table.return_value = _chain(data=[])
        from app.saved.service import list_saved_spots
        with pytest.raises(HTTPException) as exc:
            list_saved_spots(USER_ID, COLL_ID)
        assert exc.value.status_code == 404

    @patch("app.saved.service.supabase")
    def test_filtered_other_users_collection_raises_403(self, mock_sb):
        other_user_coll = {**COLL_ROW, "user_id": str(uuid.uuid4())}
        mock_sb.table.return_value = _chain(data=[other_user_coll])
        from app.saved.service import list_saved_spots
        with pytest.raises(HTTPException) as exc:
            list_saved_spots(USER_ID, COLL_ID)
        assert exc.value.status_code == 403

    @patch("app.saved.service.supabase")
    def test_filtered_empty_collection_returns_empty_response(self, mock_sb):
        # collections ownership check passes, then collection_spots is empty
        call_order = []
        def dispatch(name):
            call_order.append(name)
            if name == "collections" and len([x for x in call_order if x == "collections"]) == 1:
                return _chain(data=[COLL_ROW])  # ownership check
            if name == "collections":
                return _chain(data=[COLL_ROW])  # user_collection_ids
            if name == "collection_spots":
                return _chain(data=[])  # empty collection
            return _chain()
        mock_sb.table.side_effect = dispatch
        from app.saved.service import list_saved_spots
        result = list_saved_spots(USER_ID, COLL_ID)
        assert result.spots == []

    @patch("app.saved.service.supabase")
    def test_unfiltered_orders_by_saved_at_desc(self, mock_sb):
        # Two saved spots, first in list should be most recently saved
        older_saved = {**SAVED_ROW, "spot_id": str(uuid.uuid4()), "created_at": "2026-03-01T10:00:00+00:00"}
        newer_saved = {**SAVED_ROW, "spot_id": str(SPOT_ID), "created_at": "2026-03-15T10:00:00+00:00"}
        # saved_spots returns newer first (desc order)
        ordered_ss = [newer_saved, older_saved]
        spot_rows = [
            SPOT_ROW,
            {**SPOT_ROW, "id": older_saved["spot_id"]},
        ]
        responses = {
            "saved_spots": _chain(data=ordered_ss),
            "collections": _chain(data=[]),
            "spots": _chain(data=spot_rows),
            "collection_spots": _chain(data=[]),
        }
        mock_sb.table.side_effect = _tables(**responses)
        from app.saved.service import list_saved_spots
        result = list_saved_spots(USER_ID)
        assert len(result.spots) == 2
        # First spot should be the newer one
        assert str(result.spots[0].spot.id) == str(SPOT_ID)


# ---------------------------------------------------------------------------
# list_collections
# ---------------------------------------------------------------------------

class TestListCollections:
    @patch("app.saved.service.supabase")
    def test_no_collections_returns_empty(self, mock_sb):
        mock_sb.table.return_value = _chain(data=[])
        from app.saved.service import list_collections
        result = list_collections(USER_ID)
        assert isinstance(result, CollectionListResponse)
        assert result.collections == []

    @patch("app.saved.service.supabase")
    def test_returns_collections_with_spot_counts(self, mock_sb):
        cs_row = {"collection_id": str(COLL_ID)}
        responses = {
            "collections": _chain(data=[COLL_ROW]),
            "collection_spots": _chain(data=[cs_row, cs_row]),  # 2 spots
        }
        mock_sb.table.side_effect = _tables(**responses)
        from app.saved.service import list_collections
        result = list_collections(USER_ID)
        assert len(result.collections) == 1
        assert result.collections[0].spot_count == 2

    @patch("app.saved.service.supabase")
    def test_default_collection_appears_first(self, mock_sb):
        # DB returns regular collection before default (created_at order).
        # Response must reorder: default first.
        responses = {
            "collections": _chain(data=[COLL_ROW, DEFAULT_COLL_ROW]),
            "collection_spots": _chain(data=[]),
        }
        mock_sb.table.side_effect = _tables(**responses)
        from app.saved.service import list_collections
        result = list_collections(USER_ID)
        assert len(result.collections) == 2
        assert result.collections[0].id == DEFAULT_COLL_ID

    @patch("app.saved.service.supabase")
    def test_response_includes_is_default_field(self, mock_sb):
        responses = {
            "collections": _chain(data=[DEFAULT_COLL_ROW, COLL_ROW]),
            "collection_spots": _chain(data=[]),
        }
        mock_sb.table.side_effect = _tables(**responses)
        from app.saved.service import list_collections
        result = list_collections(USER_ID)
        ids_to_default = {c.id: c.is_default for c in result.collections}
        assert ids_to_default[DEFAULT_COLL_ID] is True
        assert ids_to_default[COLL_ID] is False


# ---------------------------------------------------------------------------
# create_collection
# ---------------------------------------------------------------------------

class TestCreateCollection:
    @patch("app.saved.service.supabase")
    def test_limit_reached_raises_422(self, mock_sb):
        # Return 50 existing collections
        mock_sb.table.return_value = _chain(data=[COLL_ROW] * 50)
        from app.saved.service import create_collection
        with pytest.raises(HTTPException) as exc:
            create_collection(USER_ID, "New List")
        assert exc.value.status_code == 422

    @patch("app.saved.service.supabase")
    def test_creates_collection_without_source(self, mock_sb):
        # First call: count check (returns empty list = 0 collections)
        # Second call: insert (returns new row)
        calls = {"n": 0}
        def dispatch(name):
            if name == "collections":
                calls["n"] += 1
                if calls["n"] == 1:
                    return _chain(data=[])  # count = 0
                return _chain(data=[COLL_ROW])  # insert result
            return _chain()
        mock_sb.table.side_effect = dispatch
        from app.saved.service import create_collection
        result = create_collection(USER_ID, "My List")
        assert isinstance(result, CollectionResponse)
        assert result.spot_count == 0

    @patch("app.saved.service.supabase")
    def test_copy_non_shareable_raises_404(self, mock_sb):
        non_shareable = {**COLL_ROW, "is_shareable": False}
        calls = {"n": 0}
        def dispatch(name):
            if name == "collections":
                calls["n"] += 1
                if calls["n"] == 1:
                    return _chain(data=[])          # count check — 0 existing
                return _chain(data=[non_shareable]) # source collection fetch (before insert)
            return _chain()
        mock_sb.table.side_effect = dispatch
        from app.saved.service import create_collection
        with pytest.raises(HTTPException) as exc:
            create_collection(USER_ID, "Copy", source_collection_id=uuid.uuid4())
        assert exc.value.status_code == 404

    @patch("app.saved.service.supabase")
    def test_copy_own_collection_raises_400(self, mock_sb):
        shareable_own = {**COLL_ROW, "is_shareable": True, "user_id": str(USER_ID)}
        calls = {"n": 0}
        def dispatch(name):
            if name == "collections":
                calls["n"] += 1
                if calls["n"] == 1:
                    return _chain(data=[])           # count check
                return _chain(data=[shareable_own])  # source collection fetch (before insert)
            return _chain()
        mock_sb.table.side_effect = dispatch
        from app.saved.service import create_collection
        with pytest.raises(HTTPException) as exc:
            create_collection(USER_ID, "Copy", source_collection_id=uuid.uuid4())
        assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# update_collection
# ---------------------------------------------------------------------------

class TestUpdateCollection:
    @patch("app.saved.service.supabase")
    def test_not_found_raises_404(self, mock_sb):
        mock_sb.table.return_value = _chain(data=[])
        from app.saved.service import update_collection
        from app.saved.schemas import UpdateCollectionRequest
        with pytest.raises(HTTPException) as exc:
            update_collection(USER_ID, COLL_ID, UpdateCollectionRequest(name="New"))
        assert exc.value.status_code == 404

    @patch("app.saved.service.supabase")
    def test_wrong_user_raises_403(self, mock_sb):
        other = {**COLL_ROW, "user_id": str(uuid.uuid4())}
        mock_sb.table.return_value = _chain(data=[other])
        from app.saved.service import update_collection
        from app.saved.schemas import UpdateCollectionRequest
        with pytest.raises(HTTPException) as exc:
            update_collection(USER_ID, COLL_ID, UpdateCollectionRequest(name="New"))
        assert exc.value.status_code == 403

    @patch("app.saved.service.supabase")
    def test_empty_payload_raises_422(self, mock_sb):
        mock_sb.table.return_value = _chain(data=[COLL_ROW])
        from app.saved.service import update_collection
        from app.saved.schemas import UpdateCollectionRequest
        with pytest.raises(HTTPException) as exc:
            update_collection(USER_ID, COLL_ID, UpdateCollectionRequest())
        assert exc.value.status_code == 422

    @patch("app.saved.service.supabase")
    def test_default_collection_raises_400(self, mock_sb):
        mock_sb.table.return_value = _chain(data=[DEFAULT_COLL_ROW])
        from app.saved.service import update_collection
        from app.saved.schemas import UpdateCollectionRequest
        with pytest.raises(HTTPException) as exc:
            update_collection(USER_ID, DEFAULT_COLL_ID, UpdateCollectionRequest(name="Renamed"))
        assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# delete_collection
# ---------------------------------------------------------------------------

class TestDeleteCollection:
    @patch("app.saved.service.supabase")
    def test_not_found_raises_404(self, mock_sb):
        mock_sb.table.return_value = _chain(data=[])
        from app.saved.service import delete_collection
        with pytest.raises(HTTPException) as exc:
            delete_collection(USER_ID, COLL_ID)
        assert exc.value.status_code == 404

    @patch("app.saved.service.supabase")
    def test_wrong_user_raises_403(self, mock_sb):
        other = {**COLL_ROW, "user_id": str(uuid.uuid4())}
        mock_sb.table.return_value = _chain(data=[other])
        from app.saved.service import delete_collection
        with pytest.raises(HTTPException) as exc:
            delete_collection(USER_ID, COLL_ID)
        assert exc.value.status_code == 403

    @patch("app.saved.service.supabase")
    def test_delete_succeeds(self, mock_sb):
        mock_sb.table.return_value = _chain(data=[COLL_ROW])
        from app.saved.service import delete_collection
        # Should not raise
        delete_collection(USER_ID, COLL_ID)

    @patch("app.saved.service.supabase")
    def test_default_collection_raises_400(self, mock_sb):
        mock_sb.table.return_value = _chain(data=[DEFAULT_COLL_ROW])
        from app.saved.service import delete_collection
        with pytest.raises(HTTPException) as exc:
            delete_collection(USER_ID, DEFAULT_COLL_ID)
        assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# add_spot_to_collection
# ---------------------------------------------------------------------------

class TestAddSpotToCollection:
    @patch("app.saved.service.supabase")
    def test_collection_not_found_raises_404(self, mock_sb):
        mock_sb.table.return_value = _chain(data=[])
        from app.saved.service import add_spot_to_collection
        with pytest.raises(HTTPException) as exc:
            add_spot_to_collection(USER_ID, COLL_ID, SPOT_ID)
        assert exc.value.status_code == 404

    @patch("app.saved.service.supabase")
    def test_wrong_user_collection_raises_403(self, mock_sb):
        other_coll = {**COLL_ROW, "user_id": str(uuid.uuid4())}
        mock_sb.table.return_value = _chain(data=[other_coll])
        from app.saved.service import add_spot_to_collection
        with pytest.raises(HTTPException) as exc:
            add_spot_to_collection(USER_ID, COLL_ID, SPOT_ID)
        assert exc.value.status_code == 403

    @patch("app.saved.service.supabase")
    def test_spot_not_found_raises_404(self, mock_sb):
        def dispatch(name):
            if name == "collections":
                return _chain(data=[COLL_ROW])
            if name == "spots":
                return _chain(data=[])  # spot not found
            return _chain()
        mock_sb.table.side_effect = dispatch
        from app.saved.service import add_spot_to_collection
        with pytest.raises(HTTPException) as exc:
            add_spot_to_collection(USER_ID, COLL_ID, SPOT_ID)
        assert exc.value.status_code == 404

    @patch("app.saved.service.supabase")
    def test_returns_saved_spot_response(self, mock_sb):
        def dispatch(name):
            if name == "collections":
                return _chain(data=[COLL_ROW])
            if name == "spots":
                return _chain(data=[SPOT_ROW])
            if name == "collection_spots":
                return _chain(data=[])
            if name == "saved_spots":
                return _chain(data=[SAVED_ROW])
            return _chain()
        mock_sb.table.side_effect = dispatch
        from app.saved.service import add_spot_to_collection
        result = add_spot_to_collection(USER_ID, COLL_ID, SPOT_ID)
        assert isinstance(result, SavedSpotResponse)


# ---------------------------------------------------------------------------
# remove_spot_from_collection
# ---------------------------------------------------------------------------

class TestRemoveSpotFromCollection:
    @patch("app.saved.service.supabase")
    def test_collection_not_found_raises_404(self, mock_sb):
        mock_sb.table.return_value = _chain(data=[])
        from app.saved.service import remove_spot_from_collection
        with pytest.raises(HTTPException) as exc:
            remove_spot_from_collection(USER_ID, COLL_ID, SPOT_ID)
        assert exc.value.status_code == 404

    @patch("app.saved.service.supabase")
    def test_wrong_user_raises_403(self, mock_sb):
        other_coll = {**COLL_ROW, "user_id": str(uuid.uuid4())}
        mock_sb.table.return_value = _chain(data=[other_coll])
        from app.saved.service import remove_spot_from_collection
        with pytest.raises(HTTPException) as exc:
            remove_spot_from_collection(USER_ID, COLL_ID, SPOT_ID)
        assert exc.value.status_code == 403

    @patch("app.saved.service.supabase")
    def test_remove_idempotent_no_raise(self, mock_sb):
        # collection found, delete is a no-op — should return 204 silently
        mock_sb.table.return_value = _chain(data=[COLL_ROW])
        from app.saved.service import remove_spot_from_collection
        remove_spot_from_collection(USER_ID, COLL_ID, SPOT_ID)  # must not raise


# ---------------------------------------------------------------------------
# get_public_collection
# ---------------------------------------------------------------------------

class TestGetPublicCollection:
    @patch("app.saved.service.supabase")
    def test_not_found_raises_404(self, mock_sb):
        mock_sb.table.return_value = _chain(data=[])
        from app.saved.service import get_public_collection
        with pytest.raises(HTTPException) as exc:
            get_public_collection(COLL_ID)
        assert exc.value.status_code == 404

    @patch("app.saved.service.supabase")
    def test_non_shareable_raises_404(self, mock_sb):
        non_shareable = {**COLL_ROW, "is_shareable": False}
        mock_sb.table.return_value = _chain(data=[non_shareable])
        from app.saved.service import get_public_collection
        with pytest.raises(HTTPException) as exc:
            get_public_collection(COLL_ID)
        assert exc.value.status_code == 404

    @patch("app.saved.service.supabase")
    def test_empty_collection_returns_empty_spots(self, mock_sb):
        shareable = {**COLL_ROW, "is_shareable": True}
        def dispatch(name):
            if name == "collections":
                return _chain(data=[shareable])
            if name == "collection_spots":
                return _chain(data=[])
            return _chain()
        mock_sb.table.side_effect = dispatch
        from app.saved.service import get_public_collection
        result = get_public_collection(COLL_ID)
        assert isinstance(result, PublicCollectionResponse)
        assert result.spots == []
        assert result.spot_count == 0

    @patch("app.saved.service.supabase")
    def test_returns_spots_in_added_at_order(self, mock_sb):
        shareable = {**COLL_ROW, "is_shareable": True}
        spot_id_1 = str(uuid.uuid4())
        spot_id_2 = str(SPOT_ID)
        # collection_spots returns in added_at ASC order: spot_id_1 first
        cs_data = [{"spot_id": spot_id_1}, {"spot_id": spot_id_2}]
        spot_1 = {**SPOT_ROW, "id": spot_id_1}
        spot_2 = {**SPOT_ROW, "id": spot_id_2}
        # spots .in_() returns in arbitrary order (spot_2 first)
        def dispatch(name):
            if name == "collections":
                return _chain(data=[shareable])
            if name == "collection_spots":
                return _chain(data=cs_data)
            if name == "spots":
                return _chain(data=[spot_2, spot_1])  # deliberately reversed
            return _chain()
        mock_sb.table.side_effect = dispatch
        from app.saved.service import get_public_collection
        result = get_public_collection(COLL_ID)
        assert len(result.spots) == 2
        # Must be re-sorted to added_at ASC: spot_id_1 first
        assert str(result.spots[0].id) == spot_id_1
        assert str(result.spots[1].id) == spot_id_2
