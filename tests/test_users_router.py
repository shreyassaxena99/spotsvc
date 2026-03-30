from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.dependencies import get_current_user

FAKE_USER_ID = str(uuid.uuid4())
FAKE_USER = {"user_id": FAKE_USER_ID}


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


class TestPatchMe:
    def test_patch_me_requires_auth(self, client):
        resp = client.patch("/me", json={"email_opt_in": True})
        assert resp.status_code == 403

    @patch("app.users.router.update_profile")
    def test_patch_me_updates_email_opt_in(self, mock_update, authed_client):
        from app.users.schemas import ProfileResponse
        mock_update.return_value = ProfileResponse(
            user_id=uuid.UUID(FAKE_USER_ID),
            display_name=None,
            email_opt_in=True,
        )
        resp = authed_client.patch("/me", json={"email_opt_in": True})
        assert resp.status_code == 200
        assert resp.json()["email_opt_in"] is True
        mock_update.assert_called_once_with(uuid.UUID(FAKE_USER_ID), display_name=None, email_opt_in=True)

    @patch("app.users.router.update_profile")
    def test_patch_me_updates_display_name(self, mock_update, authed_client):
        from app.users.schemas import ProfileResponse
        mock_update.return_value = ProfileResponse(
            user_id=uuid.UUID(FAKE_USER_ID),
            display_name="Alice",
            email_opt_in=False,
        )
        resp = authed_client.patch("/me", json={"display_name": "Alice"})
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Alice"
        mock_update.assert_called_once_with(uuid.UUID(FAKE_USER_ID), display_name="Alice", email_opt_in=None)

    @patch("app.users.router.update_profile")
    def test_patch_me_with_no_fields_returns_422(self, mock_update, authed_client):
        resp = authed_client.patch("/me", json={})
        assert resp.status_code == 422
        mock_update.assert_not_called()


class TestPostUserProfile:
    def test_requires_auth(self, client):
        resp = client.post("/users/profile", json={"working_style": "Fully remote"})
        assert resp.status_code == 403

    @patch("app.users.router.upsert_user_profile")
    def test_calls_upsert_with_jwt_user_id(self, mock_upsert, authed_client):
        resp = authed_client.post("/users/profile", json={"working_style": "Fully remote", "home_area": "North London"})
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        mock_upsert.assert_called_once_with(
            uuid.UUID(FAKE_USER_ID),
            working_style="Fully remote",
            home_area="North London",
            work_area=None,
        )

    @patch("app.users.router.upsert_user_profile")
    def test_accepts_empty_body(self, mock_upsert, authed_client):
        resp = authed_client.post("/users/profile", json={})
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        mock_upsert.assert_called_once_with(
            uuid.UUID(FAKE_USER_ID),
            working_style=None,
            home_area=None,
            work_area=None,
        )


class TestGetUserProfile:
    def test_requires_auth(self, client):
        resp = client.get(f"/users/profile/{FAKE_USER_ID}")
        assert resp.status_code == 403

    @patch("app.users.router.get_user_profile")
    def test_returns_403_if_user_id_mismatch(self, mock_get, authed_client):
        other_id = str(uuid.uuid4())
        resp = authed_client.get(f"/users/profile/{other_id}")
        assert resp.status_code == 403
        mock_get.assert_not_called()

    @patch("app.users.router.get_user_profile")
    def test_returns_profile_when_exists(self, mock_get, authed_client):
        mock_get.return_value = {
            "exists": True,
            "user_id": FAKE_USER_ID,
            "working_style": "Fully remote",
            "home_area": "North London",
            "work_area": None,
        }
        resp = authed_client.get(f"/users/profile/{FAKE_USER_ID}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["exists"] is True
        assert data["working_style"] == "Fully remote"
        mock_get.assert_called_once_with(uuid.UUID(FAKE_USER_ID))

    @patch("app.users.router.get_user_profile")
    def test_returns_not_exists(self, mock_get, authed_client):
        mock_get.return_value = {"exists": False}
        resp = authed_client.get(f"/users/profile/{FAKE_USER_ID}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["exists"] is False
        assert data["user_id"] is None
        assert data["working_style"] is None
        assert data["home_area"] is None
        assert data["work_area"] is None
