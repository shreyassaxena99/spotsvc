from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


def _chain(data=None):
    m = MagicMock()
    m.execute.return_value = MagicMock(data=data if data is not None else [])
    for method in ("select", "eq", "upsert", "update", "delete"):
        getattr(m, method).return_value = m
    return m


USER_ID = uuid.uuid4()


class TestUpdateProfile:
    @patch("app.users.service.supabase")
    def test_updates_display_name(self, mock_supabase):
        from app.users.service import update_profile

        mock_auth_user = MagicMock()
        mock_auth_user.user.user_metadata = {"full_name": "Alice"}
        mock_supabase.auth.admin.update_user_by_id.return_value = mock_auth_user

        result = update_profile(USER_ID, display_name="Alice")

        mock_supabase.auth.admin.update_user_by_id.assert_called_once_with(
            str(USER_ID), {"user_metadata": {"full_name": "Alice"}}
        )
        assert result.display_name == "Alice"

    @patch("app.users.service.supabase")
    def test_updates_email_opt_in(self, mock_supabase):
        from app.users.service import update_profile

        prefs_chain = _chain(data=[{"user_id": str(USER_ID), "email_opt_in": True}])
        mock_supabase.table.return_value = prefs_chain

        result = update_profile(USER_ID, email_opt_in=True)

        mock_supabase.table.assert_called_with("user_preferences")
        assert result.email_opt_in is True

    @patch("app.users.service.supabase")
    def test_updates_both_fields(self, mock_supabase):
        from app.users.service import update_profile

        mock_auth_user = MagicMock()
        mock_auth_user.user.user_metadata = {"full_name": "Bob"}
        mock_supabase.auth.admin.update_user_by_id.return_value = mock_auth_user

        prefs_chain = _chain(data=[{"user_id": str(USER_ID), "email_opt_in": False}])
        mock_supabase.table.return_value = prefs_chain

        result = update_profile(USER_ID, display_name="Bob", email_opt_in=False)

        assert result.display_name == "Bob"
        assert result.email_opt_in is False

    def test_raises_422_when_no_fields(self):
        from app.users.service import update_profile

        with pytest.raises(HTTPException) as exc:
            update_profile(USER_ID)
        assert exc.value.status_code == 422


class TestUpsertUserProfile:
    @patch("app.users.service.identify")
    @patch("app.users.service.supabase")
    def test_upserts_to_supabase_and_calls_identify(self, mock_supabase, mock_identify):
        from app.users.service import upsert_user_profile

        profile_chain = _chain(data=[{"user_id": str(USER_ID), "working_style": "Fully remote", "home_area": None, "work_area": None}])
        mock_supabase.table.return_value = profile_chain

        upsert_user_profile(USER_ID, working_style="Fully remote")

        mock_supabase.table.assert_called_with("user_profiles")
        mock_identify.assert_called_once_with(str(USER_ID), {"working_style": "Fully remote"})

    @patch("app.users.service.identify")
    @patch("app.users.service.supabase")
    def test_omits_none_props_from_identify(self, mock_supabase, mock_identify):
        from app.users.service import upsert_user_profile

        mock_supabase.table.return_value = _chain(data=[])

        upsert_user_profile(USER_ID, working_style="Student", home_area=None, work_area=None)

        mock_identify.assert_called_once_with(str(USER_ID), {"working_style": "Student"})

    @patch("app.users.service.identify")
    @patch("app.users.service.supabase")
    def test_raises_500_on_supabase_error(self, mock_supabase, mock_identify):
        from app.users.service import upsert_user_profile

        profile_chain = _chain()
        profile_chain.execute.side_effect = Exception("DB down")
        mock_supabase.table.return_value = profile_chain

        with pytest.raises(HTTPException) as exc:
            upsert_user_profile(USER_ID, working_style="Fully remote")
        assert exc.value.status_code == 500
        mock_identify.assert_not_called()


class TestGetUserProfile:
    @patch("app.users.service.supabase")
    def test_returns_profile_when_row_exists(self, mock_supabase):
        from app.users.service import get_user_profile

        profile_chain = _chain(data=[{
            "user_id": str(USER_ID),
            "working_style": "Fully remote",
            "home_area": "North London",
            "work_area": None,
        }])
        mock_supabase.table.return_value = profile_chain

        result = get_user_profile(USER_ID)

        assert result["exists"] is True
        assert result["working_style"] == "Fully remote"
        assert result["home_area"] == "North London"
        assert result["work_area"] is None

    @patch("app.users.service.supabase")
    def test_returns_not_exists_when_no_row(self, mock_supabase):
        from app.users.service import get_user_profile

        mock_supabase.table.return_value = _chain(data=[])

        result = get_user_profile(USER_ID)

        assert result == {"exists": False}
