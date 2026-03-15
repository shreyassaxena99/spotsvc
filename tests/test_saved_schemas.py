from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.saved.schemas import (
    SaveSpotRequest,
    CreateCollectionRequest,
    UpdateCollectionRequest,
    AddSpotToCollectionRequest,
    CollectionResponse,
    CollectionListResponse,
    SavedSpotResponse,
    SavedSpotsResponse,
    PublicCollectionResponse,
)
from app.spots.schemas import SpotPin
from app.db.models import SpotCategory, AccessType


SPOT_PIN = SpotPin(
    id=uuid.uuid4(),
    name="Test Cafe",
    short_address="1 Test St",
    latitude=51.5,
    longitude=-0.1,
    category=SpotCategory.cafe,
    access_type=AccessType.free,
    wifi_available=True,
    power_outlets=True,
    noise_matrix=None,
    rating=4.2,
    is_open_now=True,
    cover_photo=None,
)

NOW = datetime.now(timezone.utc)
COLL_ID = uuid.uuid4()
SPOT_ID = uuid.uuid4()


class TestSaveSpotRequest:
    def test_defaults_to_empty_collection_ids(self):
        req = SaveSpotRequest(spot_id=SPOT_ID)
        assert req.collection_ids == []

    def test_accepts_collection_ids(self):
        req = SaveSpotRequest(spot_id=SPOT_ID, collection_ids=[COLL_ID])
        assert req.collection_ids == [COLL_ID]


class TestCreateCollectionRequest:
    def test_name_required(self):
        with pytest.raises(ValidationError):
            CreateCollectionRequest(name="")

    def test_name_max_length(self):
        with pytest.raises(ValidationError):
            CreateCollectionRequest(name="x" * 101)

    def test_source_collection_id_optional(self):
        req = CreateCollectionRequest(name="My List")
        assert req.source_collection_id is None


class TestUpdateCollectionRequest:
    def test_all_fields_optional(self):
        req = UpdateCollectionRequest()
        assert req.name is None
        assert req.is_shareable is None


class TestCollectionResponse:
    def test_roundtrip(self):
        resp = CollectionResponse(
            id=COLL_ID,
            name="My List",
            is_shareable=False,
            spot_count=3,
            created_at=NOW,
            updated_at=NOW,
        )
        assert resp.spot_count == 3
        assert resp.is_shareable is False


class TestSavedSpotResponse:
    def test_roundtrip(self):
        resp = SavedSpotResponse(
            spot=SPOT_PIN,
            saved_at=NOW,
            collection_ids=[COLL_ID],
        )
        assert resp.collection_ids == [COLL_ID]


class TestPublicCollectionResponse:
    def test_spot_count_matches_spots(self):
        resp = PublicCollectionResponse(
            id=COLL_ID,
            name="Shared",
            spot_count=1,
            spots=[SPOT_PIN],
        )
        assert resp.spot_count == 1
        assert len(resp.spots) == 1
