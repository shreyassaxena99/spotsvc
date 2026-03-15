from __future__ import annotations

import uuid
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.dependencies import get_current_user

# Bypass auth for router tests — override get_current_user dependency
FAKE_USER_ID = str(uuid.uuid4())
FAKE_USER = {"sub": FAKE_USER_ID}

SPOT_ID = str(uuid.uuid4())
COLL_ID = str(uuid.uuid4())

NOW = "2026-03-15T10:00:00+00:00"

MOCK_SAVED_SPOT_RESPONSE = {
    "spot": {
        "id": SPOT_ID,
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
        "is_open_now": None,
        "cover_photo": None,
    },
    "saved_at": NOW,
    "collection_ids": [],
}

MOCK_COLLECTION_RESPONSE = {
    "id": COLL_ID,
    "name": "My List",
    "is_shareable": False,
    "spot_count": 0,
    "created_at": NOW,
    "updated_at": NOW,
}


async def fake_current_user() -> dict:
    return FAKE_USER


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def authed_client():
    app.dependency_overrides[get_current_user] = fake_current_user
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestSavedSpotsEndpoints:
    def test_get_saved_spots_requires_auth(self, client):
        resp = client.get("/me/saved-spots")
        assert resp.status_code == 403

    @patch("app.saved.router.list_saved_spots")
    def test_get_saved_spots_returns_200(self, mock_list, authed_client):
        from app.saved.schemas import SavedSpotsResponse
        mock_list.return_value = SavedSpotsResponse(spots=[])
        resp = authed_client.get("/me/saved-spots")
        assert resp.status_code == 200
        assert resp.json() == {"spots": []}

    @patch("app.saved.router.save_spot")
    def test_post_saved_spots_returns_200(self, mock_save, authed_client):
        from app.saved.schemas import SavedSpotResponse
        from app.spots.schemas import SpotPin
        from app.db.models import SpotCategory, AccessType
        pin = SpotPin(
            id=uuid.UUID(SPOT_ID), name="Test Cafe", short_address=None,
            latitude=51.5, longitude=-0.1, category=SpotCategory.cafe,
            access_type=AccessType.free, wifi_available=True, power_outlets=True,
            noise_matrix=None, rating=None, is_open_now=None, cover_photo=None,
        )
        mock_save.return_value = SavedSpotResponse(
            spot=pin,
            saved_at=datetime.fromisoformat(NOW),
            collection_ids=[],
        )
        resp = authed_client.post(
            "/me/saved-spots",
            json={"spot_id": SPOT_ID},
        )
        assert resp.status_code == 200

    @patch("app.saved.router.unsave_spot")
    def test_delete_saved_spot_returns_204(self, mock_unsave, authed_client):
        mock_unsave.return_value = None
        resp = authed_client.delete(f"/me/saved-spots/{SPOT_ID}")
        assert resp.status_code == 204


class TestCollectionsEndpoints:
    @patch("app.saved.router.list_collections")
    def test_get_collections_returns_200(self, mock_list, authed_client):
        from app.saved.schemas import CollectionListResponse
        mock_list.return_value = CollectionListResponse(collections=[])
        resp = authed_client.get("/me/collections")
        assert resp.status_code == 200

    @patch("app.saved.router.create_collection")
    def test_post_collections_returns_201(self, mock_create, authed_client):
        from app.saved.schemas import CollectionResponse
        mock_create.return_value = CollectionResponse(
            id=uuid.UUID(COLL_ID), name="My List", is_shareable=False,
            spot_count=0, created_at=datetime.fromisoformat(NOW),
            updated_at=datetime.fromisoformat(NOW),
        )
        resp = authed_client.post(
            "/me/collections",
            json={"name": "My List"},
        )
        assert resp.status_code == 201

    @patch("app.saved.router.delete_collection")
    def test_delete_collection_returns_204(self, mock_del, authed_client):
        mock_del.return_value = None
        resp = authed_client.delete(f"/me/collections/{COLL_ID}")
        assert resp.status_code == 204


class TestPublicCollectionEndpoint:
    @patch("app.saved.router.get_public_collection")
    def test_public_endpoint_no_auth_required(self, mock_get, client):
        from app.saved.schemas import PublicCollectionResponse
        mock_get.return_value = PublicCollectionResponse(
            id=uuid.UUID(COLL_ID), name="Shared", spot_count=0, spots=[]
        )
        resp = client.get(f"/collections/{COLL_ID}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Shared"
