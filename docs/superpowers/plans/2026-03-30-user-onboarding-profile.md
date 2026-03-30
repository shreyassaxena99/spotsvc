# User Onboarding Profile Endpoints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `POST /users/profile` and `GET /users/profile/{user_id}` endpoints that upsert onboarding data into `public.user_profiles`, call PostHog identify, and surface a `posthog_api_key_set` flag in the health check.

**Architecture:** Follows the existing users module pattern — sync service functions, async FastAPI handlers, JWT auth via `get_current_user`. PostHog is a lazily-initialised module-level singleton in `app/core/posthog.py`; if the key is unset it no-ops silently. All tests mock at the service boundary.

**Tech Stack:** FastAPI, supabase-py v2, posthog==7.9.12, pytest, unittest.mock

---

### Task 1: Add posthog dependency and config

**Files:**
- Modify: `requirements.txt`
- Modify: `.env.example`
- Modify: `app/config.py`

- [ ] **Step 1: Add posthog to requirements.txt**

Open `requirements.txt` and add this line at the end:

```
posthog==7.9.12
```

- [ ] **Step 2: Add POSTHOG_API_KEY to .env.example**

Open `.env.example` and append:

```
# PostHog
POSTHOG_API_KEY=your-posthog-project-api-key
```

- [ ] **Step 3: Add posthog_api_key to Settings**

The full updated `app/config.py`:

```python
from __future__ import annotations

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Supabase
    supabase_url: str
    supabase_jwt_secret: str
    supabase_service_role_key: str

    # Google Places API (New)
    google_places_api_key: str

    # PostHog
    posthog_api_key: Optional[str] = None

    # App
    app_env: str = "development"
    admin_pwd: str


settings = Settings()
```

- [ ] **Step 4: Commit**

```bash
git add requirements.txt .env.example app/config.py
git commit -m "feat: add posthog dependency and config"
```

---

### Task 2: Create PostHog singleton

**Files:**
- Create: `app/core/posthog.py`

- [ ] **Step 1: Create app/core/posthog.py**

```python
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_posthog_client = None


def _get_client():
    global _posthog_client
    if _posthog_client is None:
        from app.config import settings
        if settings.posthog_api_key:
            from posthog import Posthog
            _posthog_client = Posthog(
                project_api_key=settings.posthog_api_key,
                host="https://eu.i.posthog.com",
            )
    return _posthog_client


def identify(distinct_id: str, properties: dict) -> None:
    """Call PostHog identify. No-ops silently if PostHog is not configured."""
    client = _get_client()
    if client is None:
        logger.debug("PostHog not configured, skipping identify for %s", distinct_id)
        return
    try:
        client.identify(distinct_id=distinct_id, properties=properties)
    except Exception as exc:
        logger.warning("PostHog identify failed: %s", exc)
```

- [ ] **Step 2: Commit**

```bash
git add app/core/posthog.py
git commit -m "feat: add PostHog singleton"
```

---

### Task 3: Add schemas

**Files:**
- Modify: `app/users/schemas.py`

- [ ] **Step 1: Add the three new models**

The full updated `app/users/schemas.py`:

```python
from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel, Field


class UpdateProfileRequest(BaseModel):
    display_name: Optional[str] = Field(None, min_length=1, max_length=100)
    email_opt_in: Optional[bool] = None


class ProfileResponse(BaseModel):
    user_id: uuid.UUID
    display_name: Optional[str]
    email_opt_in: bool


class OnboardingProfileRequest(BaseModel):
    working_style: Optional[str] = None
    home_area: Optional[str] = None
    work_area: Optional[str] = None


class OnboardingProfileResponse(BaseModel):
    status: str


class UserProfileData(BaseModel):
    exists: bool
    user_id: Optional[uuid.UUID] = None
    working_style: Optional[str] = None
    home_area: Optional[str] = None
    work_area: Optional[str] = None
```

- [ ] **Step 2: Commit**

```bash
git add app/users/schemas.py
git commit -m "feat: add onboarding profile schemas"
```

---

### Task 4: Add service functions

**Files:**
- Modify: `app/users/service.py`
- Modify: `tests/test_users_service.py`

- [ ] **Step 1: Write the failing tests**

Add this class to `tests/test_users_service.py` (after the existing `TestUpdateProfile` class):

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_users_service.py::TestUpsertUserProfile tests/test_users_service.py::TestGetUserProfile -v
```

Expected: `ImportError` or `AttributeError` — `upsert_user_profile` and `get_user_profile` don't exist yet.

- [ ] **Step 3: Implement the service functions**

The full updated `app/users/service.py`:

```python
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from app.core.posthog import identify
from app.db.database import supabase
from app.users.schemas import ProfileResponse

logger = logging.getLogger(__name__)


def update_profile(
    user_id: uuid.UUID,
    display_name: Optional[str] = None,
    email_opt_in: Optional[bool] = None,
) -> ProfileResponse:
    if display_name is None and email_opt_in is None:
        raise HTTPException(status_code=422, detail="No fields provided to update")

    updated_display_name: Optional[str] = None
    updated_email_opt_in: bool = False

    if display_name is not None:
        auth_result = supabase.auth.admin.update_user_by_id(
            str(user_id), {"user_metadata": {"full_name": display_name}}
        )
        updated_display_name = auth_result.user.user_metadata.get("full_name")

    if email_opt_in is not None:
        now = datetime.now(timezone.utc).isoformat()
        pref_result = (
            supabase.table("user_preferences")
            .upsert(
                {"user_id": str(user_id), "email_opt_in": email_opt_in, "updated_at": now},
                on_conflict="user_id",
            )
            .execute()
        )
        updated_email_opt_in = pref_result.data[0]["email_opt_in"]

    return ProfileResponse(
        user_id=user_id,
        display_name=updated_display_name,
        email_opt_in=updated_email_opt_in,
    )


def upsert_user_profile(
    user_id: uuid.UUID,
    working_style: Optional[str] = None,
    home_area: Optional[str] = None,
    work_area: Optional[str] = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    try:
        supabase.table("user_profiles").upsert(
            {
                "user_id": str(user_id),
                "working_style": working_style,
                "home_area": home_area,
                "work_area": work_area,
                "updated_at": now,
            },
            on_conflict="user_id",
        ).execute()
    except Exception as exc:
        logger.error("Failed to upsert user profile for %s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail="Failed to save profile")

    props = {
        k: v for k, v in {
            "working_style": working_style,
            "home_area": home_area,
            "work_area": work_area,
        }.items() if v is not None
    }
    identify(str(user_id), props)


def get_user_profile(user_id: uuid.UUID) -> dict:
    result = (
        supabase.table("user_profiles")
        .select("user_id, working_style, home_area, work_area")
        .eq("user_id", str(user_id))
        .execute()
    )
    if not result.data:
        return {"exists": False}
    row = result.data[0]
    return {
        "exists": True,
        "user_id": row["user_id"],
        "working_style": row.get("working_style"),
        "home_area": row.get("home_area"),
        "work_area": row.get("work_area"),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_users_service.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/users/service.py tests/test_users_service.py
git commit -m "feat: add upsert_user_profile and get_user_profile service functions"
```

---

### Task 5: Add router endpoints

**Files:**
- Modify: `app/users/router.py`
- Modify: `tests/test_users_router.py`

- [ ] **Step 1: Write the failing tests**

Add this to `tests/test_users_router.py` after the existing `TestPatchMe` class:

```python
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
        assert resp.json()["exists"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_users_router.py::TestPostUserProfile tests/test_users_router.py::TestGetUserProfile -v
```

Expected: `AttributeError` — routes don't exist yet.

- [ ] **Step 3: Implement the router endpoints**

The full updated `app/users/router.py`:

```python
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_user
from app.users.schemas import (
    OnboardingProfileRequest,
    OnboardingProfileResponse,
    ProfileResponse,
    UpdateProfileRequest,
    UserProfileData,
)
from app.users.service import get_user_profile, update_profile, upsert_user_profile

router = APIRouter(tags=["users"])


@router.patch("/me", response_model=ProfileResponse)
async def patch_me(
    payload: UpdateProfileRequest,
    user: dict = Depends(get_current_user),
) -> ProfileResponse:
    """Update the current user's profile (e.g. email_opt_in)."""
    if payload.display_name is None and payload.email_opt_in is None:
        raise HTTPException(status_code=422, detail="No fields provided to update")
    return update_profile(
        uuid.UUID(user["user_id"]),
        display_name=payload.display_name,
        email_opt_in=payload.email_opt_in,
    )


@router.post("/users/profile", response_model=OnboardingProfileResponse)
async def post_user_profile(
    payload: OnboardingProfileRequest,
    user: dict = Depends(get_current_user),
) -> OnboardingProfileResponse:
    """Upsert onboarding profile data for the authenticated user."""
    upsert_user_profile(
        uuid.UUID(user["user_id"]),
        working_style=payload.working_style,
        home_area=payload.home_area,
        work_area=payload.work_area,
    )
    return OnboardingProfileResponse(status="ok")


@router.get("/users/profile/{user_id}", response_model=UserProfileData)
async def get_profile(
    user_id: uuid.UUID,
    user: dict = Depends(get_current_user),
) -> UserProfileData:
    """Return the onboarding profile for the authenticated user, or exists=false if not yet set."""
    if str(user_id) != user["user_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    data = get_user_profile(user_id)
    return UserProfileData(**data)
```

- [ ] **Step 4: Run all tests to verify they pass**

```bash
pytest tests/test_users_router.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/users/router.py tests/test_users_router.py
git commit -m "feat: add POST /users/profile and GET /users/profile/{user_id} endpoints"
```

---

### Task 6: Update health check

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: Add posthog_api_key_set to health check response**

The full updated health check handler in `app/main.py` (replace the existing `health_check` function only):

```python
@app.get("/health", tags=["meta"])
async def health_check():
    try:
        supabase.table("spots").select("id").limit(1).execute()
        db_status = "ok"
    except Exception as exc:
        logger.error("Health check DB ping failed: %s", exc, exc_info=True)
        db_status = str(exc)
    return {
        "status": "ok",
        "db": db_status,
        "admin_pwd_set": bool(settings.admin_pwd),
        "posthog_api_key_set": bool(settings.posthog_api_key),
    }
```

- [ ] **Step 2: Run full test suite**

```bash
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add app/main.py
git commit -m "feat: add posthog_api_key_set to health check"
```
