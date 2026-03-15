# Saved Spots & Collections Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 10 API endpoints that let authenticated users save spots, organise them into named collections, and share collections publicly via a link.

**Architecture:** A new `app/saved/` module (schemas, service, router) follows the same sync-service pattern as `app/admin/` and `app/spots/`. All DB access goes through the supabase-py client (HTTP, service role key). Two new tables (`collections`, `collection_spots`) are added manually in Supabase SQL Editor. The existing `saved_spots` table is unchanged.

**Tech Stack:** FastAPI, supabase-py v2, Pydantic v2, Python 3.12. Tests use `pytest` + `unittest.mock`.

**Spec:** `docs/superpowers/specs/2026-03-15-saved-spots-collections-design.md`

---

## Chunk 1: DB Migration + Module Scaffold + Schemas

---

### Task 1: DB Migration (Manual — No Code)

**Run in Supabase SQL Editor in this exact order.**

- [ ] **Step 1: Create tables and indexes**

```sql
CREATE TABLE collections (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL,
    name         VARCHAR(100) NOT NULL,
    is_shareable BOOLEAN NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_collections_user ON collections (user_id);

CREATE TABLE collection_spots (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    collection_id UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    spot_id       UUID NOT NULL REFERENCES spots(id) ON DELETE CASCADE,
    added_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(collection_id, spot_id)
);

CREATE INDEX idx_collection_spots_collection ON collection_spots (collection_id);
```

- [ ] **Step 2: Enable RLS and create policies**

```sql
-- collections
ALTER TABLE collections ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users manage own collections"
    ON collections FOR ALL
    USING (auth.uid() = user_id);

CREATE POLICY "Anyone can read shareable collections"
    ON collections FOR SELECT
    USING (is_shareable = TRUE);

GRANT SELECT ON collections TO anon;

-- collection_spots
ALTER TABLE collection_spots ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users manage spots in own collections"
    ON collection_spots FOR ALL
    USING (
        collection_id IN (
            SELECT id FROM collections WHERE user_id = auth.uid()
        )
    );

CREATE POLICY "Anyone can read spots in shareable collections"
    ON collection_spots FOR SELECT
    USING (
        collection_id IN (
            SELECT id FROM collections WHERE is_shareable = TRUE
        )
    );

GRANT SELECT ON collection_spots TO anon;

-- saved_spots: idempotent — safe to run even if policies already exist
ALTER TABLE saved_spots ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    CREATE POLICY "Users read own saves" ON saved_spots FOR SELECT USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE POLICY "Users insert own saves" ON saved_spots FOR INSERT WITH CHECK (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE POLICY "Users delete own saves" ON saved_spots FOR DELETE USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
```

- [ ] **Step 3: Verify tables exist**

In SQL Editor: `SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name IN ('collections', 'collection_spots');`

Expected: 2 rows.

---

### Task 2: Module Scaffold and Pydantic Schemas

**Files:**
- Create: `app/saved/__init__.py`
- Create: `app/saved/schemas.py`
- Create: `tests/test_saved_schemas.py`

- [ ] **Step 1: Write the failing schema test**

```python
# tests/test_saved_schemas.py
from __future__ import annotations

import uuid
from datetime import datetime, timezone

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
        import pytest
        with pytest.raises(Exception):
            CreateCollectionRequest(name="")

    def test_name_max_length(self):
        import pytest
        with pytest.raises(Exception):
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/shreyassaxena/development/spotsvc
.venv/bin/python -m pytest tests/test_saved_schemas.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'app.saved'`

- [ ] **Step 3: Create the module package**

```python
# app/saved/__init__.py
# (empty)
```

- [ ] **Step 4: Create schemas**

```python
# app/saved/schemas.py
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.spots.schemas import SpotPin


class SaveSpotRequest(BaseModel):
    spot_id: uuid.UUID
    collection_ids: list[uuid.UUID] = []


class CreateCollectionRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    source_collection_id: Optional[uuid.UUID] = None


class UpdateCollectionRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    is_shareable: Optional[bool] = None


class AddSpotToCollectionRequest(BaseModel):
    spot_id: uuid.UUID


class CollectionResponse(BaseModel):
    id: uuid.UUID
    name: str
    is_shareable: bool
    spot_count: int
    created_at: datetime
    updated_at: datetime


class CollectionListResponse(BaseModel):
    collections: list[CollectionResponse]


class SavedSpotResponse(BaseModel):
    spot: SpotPin
    saved_at: datetime
    collection_ids: list[uuid.UUID]


class SavedSpotsResponse(BaseModel):
    spots: list[SavedSpotResponse]


class PublicCollectionResponse(BaseModel):
    id: uuid.UUID
    name: str
    spot_count: int
    spots: list[SpotPin]
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_saved_schemas.py -v
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/saved/__init__.py app/saved/schemas.py tests/test_saved_schemas.py
git commit -m "feat: add saved module scaffold and Pydantic schemas"
```

---

## Chunk 2: Service Layer — save/unsave/list_saved_spots

---

### Task 3: save_spot and unsave_spot Service Functions

**Files:**
- Create: `app/saved/service.py`
- Create: `tests/test_saved_service.py`

**Supabase mock pattern** used throughout all service tests:

```python
from unittest.mock import MagicMock

def _chain(data=None):
    """Build a fluent supabase query mock."""
    m = MagicMock()
    m.execute.return_value = MagicMock(data=data if data is not None else [])
    for method in ("select", "eq", "in_", "order", "limit",
                   "upsert", "insert", "update", "delete"):
        getattr(m, method).return_value = m
    return m

def _tables(**by_name):
    """Return a side_effect function that routes table() calls by name."""
    default = _chain()
    def dispatch(name):
        return by_name.get(name, default)
    return dispatch
```

- [ ] **Step 1: Write failing tests for save_spot and unsave_spot**

```python
# tests/test_saved_service.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_saved_service.py::TestSaveSpot tests/test_saved_service.py::TestUnsaveSpot -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError` or `ImportError` — `app.saved.service` does not exist yet.

- [ ] **Step 3: Create service.py with save_spot and unsave_spot**

```python
# app/saved/service.py
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from app.db.database import supabase
from app.saved.schemas import (
    CollectionListResponse,
    CollectionResponse,
    PublicCollectionResponse,
    SavedSpotResponse,
    SavedSpotsResponse,
    UpdateCollectionRequest,
)
from app.spots.service import _build_spot_pin

logger = logging.getLogger(__name__)


def save_spot(
    user_id: uuid.UUID,
    spot_id: uuid.UUID,
    collection_ids: list[uuid.UUID],
) -> SavedSpotResponse:
    # Step 1: Verify spot exists and is active
    spot_result = (
        supabase.table("spots")
        .select("*")
        .eq("id", str(spot_id))
        .eq("is_active", True)
        .execute()
    )
    if not spot_result.data:
        raise HTTPException(status_code=404, detail="Spot not found")
    spot_row = spot_result.data[0]

    # Step 2: Validate all collection_ids in one query (skip if empty)
    if collection_ids:
        cid_strs = [str(cid) for cid in collection_ids]
        coll_check = (
            supabase.table("collections")
            .select("id")
            .in_("id", cid_strs)
            .eq("user_id", str(user_id))
            .execute()
        )
        if len(coll_check.data) != len(collection_ids):
            raise HTTPException(
                status_code=403,
                detail="One or more collection IDs are invalid or not owned by you",
            )

    # Step 3: Upsert into saved_spots (no created_at — preserves existing on conflict)
    ss_result = (
        supabase.table("saved_spots")
        .upsert({"user_id": str(user_id), "spot_id": str(spot_id)}, on_conflict="user_id,spot_id")
        .execute()
    )
    saved_at = ss_result.data[0]["created_at"]

    # Step 4: Bulk upsert into collection_spots (single call, not a loop)
    if collection_ids:
        cs_rows = [{"collection_id": str(cid), "spot_id": str(spot_id)} for cid in collection_ids]
        supabase.table("collection_spots").upsert(
            cs_rows, on_conflict="collection_id,spot_id", ignore_duplicates=True
        ).execute()

    # Step 5: Fetch all user collection IDs
    user_colls_result = (
        supabase.table("collections").select("id").eq("user_id", str(user_id)).execute()
    )
    user_collection_ids = [row["id"] for row in user_colls_result.data]

    # Step 6: Fetch which of those collections this spot belongs to
    response_collection_ids: list[uuid.UUID] = []
    if user_collection_ids:
        cs_result = (
            supabase.table("collection_spots")
            .select("collection_id")
            .in_("collection_id", user_collection_ids)
            .eq("spot_id", str(spot_id))
            .execute()
        )
        response_collection_ids = [uuid.UUID(row["collection_id"]) for row in cs_result.data]

    return SavedSpotResponse(
        spot=_build_spot_pin(spot_row),
        saved_at=saved_at,
        collection_ids=response_collection_ids,
    )


def unsave_spot(user_id: uuid.UUID, spot_id: uuid.UUID) -> None:
    # Step 1: Verify the spot is saved (404 before any destructive write)
    check = (
        supabase.table("saved_spots")
        .select("id")
        .eq("user_id", str(user_id))
        .eq("spot_id", str(spot_id))
        .execute()
    )
    if not check.data:
        raise HTTPException(status_code=404, detail="Spot is not saved")

    # Step 2: Fetch all user collection IDs
    colls = supabase.table("collections").select("id").eq("user_id", str(user_id)).execute()
    collection_ids = [row["id"] for row in colls.data]

    # Step 3: Delete from collection_spots (skip if user has no collections)
    if len(collection_ids) > 0:
        supabase.table("collection_spots").delete().in_(
            "collection_id", collection_ids
        ).eq("spot_id", str(spot_id)).execute()

    # Step 4: Delete from saved_spots
    supabase.table("saved_spots").delete().eq("user_id", str(user_id)).eq(
        "spot_id", str(spot_id)
    ).execute()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_saved_service.py::TestSaveSpot tests/test_saved_service.py::TestUnsaveSpot -v
```

Expected: All 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/saved/service.py tests/test_saved_service.py
git commit -m "feat: add save_spot and unsave_spot service functions"
```

---

### Task 4: list_saved_spots Service Function

**Files:**
- Modify: `app/saved/service.py`
- Modify: `tests/test_saved_service.py`

- [ ] **Step 1: Write failing tests**

Add this class to `tests/test_saved_service.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_saved_service.py::TestListSavedSpots -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'list_saved_spots'`

- [ ] **Step 3: Implement list_saved_spots**

Add to `app/saved/service.py`:

```python
def list_saved_spots(
    user_id: uuid.UUID,
    collection_id: Optional[uuid.UUID] = None,
) -> SavedSpotsResponse:
    if collection_id is not None:
        return _list_saved_spots_filtered(user_id, collection_id)
    return _list_saved_spots_all(user_id)


def _list_saved_spots_filtered(
    user_id: uuid.UUID,
    collection_id: uuid.UUID,
) -> SavedSpotsResponse:
    # Step 1: Verify collection ownership
    coll_result = (
        supabase.table("collections")
        .select("id,user_id")
        .eq("id", str(collection_id))
        .execute()
    )
    if not coll_result.data:
        raise HTTPException(status_code=404, detail="Collection not found")
    if coll_result.data[0]["user_id"] != str(user_id):
        raise HTTPException(status_code=403, detail="Not your collection")

    # Step 2: Fetch all user's collection IDs (for full collection_ids in response)
    user_colls = (
        supabase.table("collections").select("id").eq("user_id", str(user_id)).execute()
    )
    user_collection_ids = [row["id"] for row in user_colls.data]

    # Step 3: Fetch spots in this collection, ordered by added_at ASC
    cs_result = (
        supabase.table("collection_spots")
        .select("spot_id")
        .eq("collection_id", str(collection_id))
        .order("added_at")
        .execute()
    )
    if not cs_result.data:
        return SavedSpotsResponse(spots=[])
    spot_ids = [row["spot_id"] for row in cs_result.data]

    # Step 4: Batch fetch spot rows, re-sort to added_at ASC order
    spots_result = supabase.table("spots").select("*").in_("id", spot_ids).execute()
    spot_map = {row["id"]: row for row in spots_result.data}

    # Step 5: Fetch saved_at timestamps
    ss_result = (
        supabase.table("saved_spots")
        .select("spot_id,created_at")
        .eq("user_id", str(user_id))
        .in_("spot_id", spot_ids)
        .execute()
    )
    saved_at_map = {row["spot_id"]: row["created_at"] for row in ss_result.data}

    # Step 6: Fetch full collection membership across all user's collections
    cs_all: dict[str, list[uuid.UUID]] = {}
    if user_collection_ids:
        cs_all_result = (
            supabase.table("collection_spots")
            .select("collection_id,spot_id")
            .in_("collection_id", user_collection_ids)
            .execute()
        )
        for row in cs_all_result.data:
            cs_all.setdefault(row["spot_id"], []).append(uuid.UUID(row["collection_id"]))

    # Step 7: Build response preserving added_at ASC order from step 3
    spots = []
    for sid in spot_ids:
        row = spot_map.get(sid)
        if row is None:
            continue
        spots.append(
            SavedSpotResponse(
                spot=_build_spot_pin(row),
                saved_at=saved_at_map.get(sid),
                collection_ids=cs_all.get(sid, []),
            )
        )
    return SavedSpotsResponse(spots=spots)


def _list_saved_spots_all(user_id: uuid.UUID) -> SavedSpotsResponse:
    # Step 1: Fetch saved spots ordered by created_at DESC
    ss_result = (
        supabase.table("saved_spots")
        .select("spot_id,created_at")
        .eq("user_id", str(user_id))
        .order("created_at", desc=True)
        .execute()
    )
    if not ss_result.data:
        return SavedSpotsResponse(spots=[])
    spot_ids = [row["spot_id"] for row in ss_result.data]
    saved_at_map = {row["spot_id"]: row["created_at"] for row in ss_result.data}

    # Step 2: Fetch all user's collection IDs
    user_colls = (
        supabase.table("collections").select("id").eq("user_id", str(user_id)).execute()
    )
    user_collection_ids = [row["id"] for row in user_colls.data]

    # Step 3: Batch fetch spot rows, re-sort to created_at DESC order
    spots_result = supabase.table("spots").select("*").in_("id", spot_ids).execute()
    spot_map = {row["id"]: row for row in spots_result.data}

    # Step 4: Fetch collection membership for all user's collections
    cs_all: dict[str, list[uuid.UUID]] = {}
    if user_collection_ids:
        cs_all_result = (
            supabase.table("collection_spots")
            .select("collection_id,spot_id")
            .in_("collection_id", user_collection_ids)
            .execute()
        )
        for row in cs_all_result.data:
            cs_all.setdefault(row["spot_id"], []).append(uuid.UUID(row["collection_id"]))

    # Step 5: Build response preserving created_at DESC order from step 1
    spots = []
    for sid in spot_ids:
        row = spot_map.get(sid)
        if row is None:
            continue
        spots.append(
            SavedSpotResponse(
                spot=_build_spot_pin(row),
                saved_at=saved_at_map[sid],
                collection_ids=cs_all.get(sid, []),
            )
        )
    return SavedSpotsResponse(spots=spots)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_saved_service.py::TestListSavedSpots -v
```

Expected: All 5 tests pass.

- [ ] **Step 5: Run all service tests**

```bash
.venv/bin/python -m pytest tests/test_saved_service.py -v
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/saved/service.py tests/test_saved_service.py
git commit -m "feat: add list_saved_spots service function"
```

---

## Chunk 3: Collections CRUD + Spot-in-Collection + Router

---

### Task 5: Collections CRUD Service Functions

**Files:**
- Modify: `app/saved/service.py`
- Modify: `tests/test_saved_service.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_saved_service.py`:

```python
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
        responses = {
            "collections": _chain(data=[COLL_ROW]),  # count check (0 existing) then insert
        }
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
                    return _chain(data=[])   # count check — 0 existing
                if calls["n"] == 2:
                    return _chain(data=[COLL_ROW])  # insert
                return _chain(data=[non_shareable])  # source collection fetch
            return _chain()
        mock_sb.table.side_effect = dispatch
        from app.saved.service import create_collection
        with pytest.raises(HTTPException) as exc:
            create_collection(USER_ID, "Copy", uuid.uuid4())
        assert exc.value.status_code == 404

    @patch("app.saved.service.supabase")
    def test_copy_own_collection_raises_400(self, mock_sb):
        shareable_own = {**COLL_ROW, "is_shareable": True, "user_id": str(USER_ID)}
        calls = {"n": 0}
        def dispatch(name):
            if name == "collections":
                calls["n"] += 1
                if calls["n"] == 1:
                    return _chain(data=[])         # count check
                if calls["n"] == 2:
                    return _chain(data=[COLL_ROW]) # insert
                return _chain(data=[shareable_own]) # source collection
            return _chain()
        mock_sb.table.side_effect = dispatch
        from app.saved.service import create_collection
        with pytest.raises(HTTPException) as exc:
            create_collection(USER_ID, "Copy", uuid.uuid4())
        assert exc.value.status_code == 400


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
```

Add the import at the top of the test file:
```python
from app.saved.schemas import CollectionListResponse, CollectionResponse
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_saved_service.py::TestListCollections tests/test_saved_service.py::TestCreateCollection tests/test_saved_service.py::TestUpdateCollection tests/test_saved_service.py::TestDeleteCollection -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'list_collections'`

- [ ] **Step 3: Implement collections CRUD**

Add to `app/saved/service.py`:

```python
def list_collections(user_id: uuid.UUID) -> CollectionListResponse:
    result = (
        supabase.table("collections")
        .select("*")
        .eq("user_id", str(user_id))
        .order("created_at")
        .execute()
    )
    if not result.data:
        return CollectionListResponse(collections=[])
    collection_ids = [row["id"] for row in result.data]

    cs_result = (
        supabase.table("collection_spots")
        .select("collection_id")
        .in_("collection_id", collection_ids)
        .execute()
    )
    counts: dict[str, int] = {}
    for row in cs_result.data:
        counts[row["collection_id"]] = counts.get(row["collection_id"], 0) + 1

    colls = [
        CollectionResponse(
            id=row["id"],
            name=row["name"],
            is_shareable=row["is_shareable"],
            spot_count=counts.get(row["id"], 0),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in result.data
    ]
    return CollectionListResponse(collections=colls)


def create_collection(
    user_id: uuid.UUID,
    name: str,
    source_collection_id: Optional[uuid.UUID] = None,
) -> CollectionResponse:
    # Step 1: Enforce collection cap
    count_result = (
        supabase.table("collections").select("id").eq("user_id", str(user_id)).execute()
    )
    if len(count_result.data) >= 50:
        raise HTTPException(status_code=422, detail="Collection limit reached (50)")

    # Step 2: Insert new collection
    now = datetime.now(timezone.utc).isoformat()
    insert_result = supabase.table("collections").insert({
        "user_id": str(user_id),
        "name": name,
        "is_shareable": False,
        "created_at": now,
        "updated_at": now,
    }).execute()
    new_coll = insert_result.data[0]
    new_coll_id = new_coll["id"]

    spot_count = 0

    # Step 3: Copy from source collection if provided
    if source_collection_id is not None:
        src_result = (
            supabase.table("collections")
            .select("*")
            .eq("id", str(source_collection_id))
            .execute()
        )
        if not src_result.data or not src_result.data[0]["is_shareable"]:
            raise HTTPException(status_code=404, detail="Collection not found")
        if src_result.data[0]["user_id"] == str(user_id):
            raise HTTPException(status_code=400, detail="Cannot copy your own collection")

        src_spots = (
            supabase.table("collection_spots")
            .select("spot_id")
            .eq("collection_id", str(source_collection_id))
            .execute()
        )
        spot_ids = [row["spot_id"] for row in src_spots.data]
        spot_count = len(spot_ids)

        if spot_ids:
            try:
                cs_rows = [{"collection_id": new_coll_id, "spot_id": sid} for sid in spot_ids]
                supabase.table("collection_spots").upsert(
                    cs_rows, on_conflict="collection_id,spot_id", ignore_duplicates=True
                ).execute()
                ss_rows = [{"user_id": str(user_id), "spot_id": sid} for sid in spot_ids]
                supabase.table("saved_spots").upsert(
                    ss_rows, on_conflict="user_id,spot_id", ignore_duplicates=True
                ).execute()
            except Exception as exc:
                logger.error(
                    "create_collection copy failed after inserting collection: %s",
                    exc,
                    exc_info=True,
                )
                raise HTTPException(
                    status_code=500, detail=f"Failed to copy collection spots: {exc}"
                )

    return CollectionResponse(
        id=new_coll["id"],
        name=new_coll["name"],
        is_shareable=new_coll["is_shareable"],
        spot_count=spot_count,
        created_at=new_coll["created_at"],
        updated_at=new_coll["updated_at"],
    )


def update_collection(
    user_id: uuid.UUID,
    collection_id: uuid.UUID,
    payload: UpdateCollectionRequest,
) -> CollectionResponse:
    result = (
        supabase.table("collections").select("*").eq("id", str(collection_id)).execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Collection not found")
    if result.data[0]["user_id"] != str(user_id):
        raise HTTPException(status_code=403, detail="Not your collection")

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=422, detail="No fields provided to update")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    update_result = (
        supabase.table("collections").update(updates).eq("id", str(collection_id)).execute()
    )
    updated = update_result.data[0]

    # Note: separate read-after-write; no transaction — count is accurate under normal usage
    cs_result = (
        supabase.table("collection_spots").select("id").eq("collection_id", str(collection_id)).execute()
    )
    spot_count = len(cs_result.data)

    return CollectionResponse(
        id=updated["id"],
        name=updated["name"],
        is_shareable=updated["is_shareable"],
        spot_count=spot_count,
        created_at=updated["created_at"],
        updated_at=updated["updated_at"],
    )


def delete_collection(user_id: uuid.UUID, collection_id: uuid.UUID) -> None:
    result = (
        supabase.table("collections").select("id,user_id").eq("id", str(collection_id)).execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Collection not found")
    if result.data[0]["user_id"] != str(user_id):
        raise HTTPException(status_code=403, detail="Not your collection")
    supabase.table("collections").delete().eq("id", str(collection_id)).execute()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_saved_service.py::TestListCollections tests/test_saved_service.py::TestCreateCollection tests/test_saved_service.py::TestUpdateCollection tests/test_saved_service.py::TestDeleteCollection -v
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/saved/service.py tests/test_saved_service.py
git commit -m "feat: add collections CRUD service functions"
```

---

### Task 6: add_spot_to_collection, remove_spot_from_collection, get_public_collection

**Files:**
- Modify: `app/saved/service.py`
- Modify: `tests/test_saved_service.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_saved_service.py`:

```python
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
        calls = {"n": 0}
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
        calls = {"n": 0}
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
```

Add to imports at top of test file:
```python
from app.saved.schemas import PublicCollectionResponse
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_saved_service.py::TestAddSpotToCollection tests/test_saved_service.py::TestRemoveSpotFromCollection tests/test_saved_service.py::TestGetPublicCollection -v 2>&1 | head -20
```

Expected: `ImportError` for the new functions.

- [ ] **Step 3: Implement the three functions**

Add to `app/saved/service.py`:

```python
def add_spot_to_collection(
    user_id: uuid.UUID,
    collection_id: uuid.UUID,
    spot_id: uuid.UUID,
) -> SavedSpotResponse:
    # Step 1: Verify collection belongs to user
    coll_result = (
        supabase.table("collections").select("id,user_id").eq("id", str(collection_id)).execute()
    )
    if not coll_result.data:
        raise HTTPException(status_code=404, detail="Collection not found")
    if coll_result.data[0]["user_id"] != str(user_id):
        raise HTTPException(status_code=403, detail="Not your collection")

    # Step 2: Verify spot exists and is active
    spot_result = (
        supabase.table("spots")
        .select("*")
        .eq("id", str(spot_id))
        .eq("is_active", True)
        .execute()
    )
    if not spot_result.data:
        raise HTTPException(status_code=404, detail="Spot not found")
    spot_row = spot_result.data[0]

    # Step 3: Upsert into collection_spots
    supabase.table("collection_spots").upsert(
        {"collection_id": str(collection_id), "spot_id": str(spot_id)},
        on_conflict="collection_id,spot_id",
        ignore_duplicates=True,
    ).execute()

    # Step 4: Upsert into saved_spots (implicit save — ignore_duplicates preserves created_at)
    supabase.table("saved_spots").upsert(
        {"user_id": str(user_id), "spot_id": str(spot_id)},
        on_conflict="user_id,spot_id",
        ignore_duplicates=True,
    ).execute()

    # Step 5: Fetch saved_at (separate query since ignore_duplicates may return empty data)
    ss_result = (
        supabase.table("saved_spots")
        .select("created_at")
        .eq("user_id", str(user_id))
        .eq("spot_id", str(spot_id))
        .execute()
    )
    saved_at = ss_result.data[0]["created_at"]

    # Step 6: Fetch all user collection IDs and spot's full collection membership
    user_colls = (
        supabase.table("collections").select("id").eq("user_id", str(user_id)).execute()
    )
    user_collection_ids = [row["id"] for row in user_colls.data]

    response_collection_ids: list[uuid.UUID] = []
    if user_collection_ids:
        cs_result = (
            supabase.table("collection_spots")
            .select("collection_id")
            .in_("collection_id", user_collection_ids)
            .eq("spot_id", str(spot_id))
            .execute()
        )
        response_collection_ids = [uuid.UUID(row["collection_id"]) for row in cs_result.data]

    return SavedSpotResponse(
        spot=_build_spot_pin(spot_row),
        saved_at=saved_at,
        collection_ids=response_collection_ids,
    )


def remove_spot_from_collection(
    user_id: uuid.UUID,
    collection_id: uuid.UUID,
    spot_id: uuid.UUID,
) -> None:
    # Step 1: Verify collection belongs to user
    coll_result = (
        supabase.table("collections").select("id,user_id").eq("id", str(collection_id)).execute()
    )
    if not coll_result.data:
        raise HTTPException(status_code=404, detail="Collection not found")
    if coll_result.data[0]["user_id"] != str(user_id):
        raise HTTPException(status_code=403, detail="Not your collection")

    # Step 2: Delete from collection_spots (idempotent — no-op if not in collection)
    supabase.table("collection_spots").delete().eq(
        "collection_id", str(collection_id)
    ).eq("spot_id", str(spot_id)).execute()


def get_public_collection(collection_id: uuid.UUID) -> PublicCollectionResponse:
    # Step 1: Fetch collection — 404 if not found or not shareable
    result = (
        supabase.table("collections")
        .select("id,name,is_shareable")
        .eq("id", str(collection_id))
        .execute()
    )
    if not result.data or not result.data[0]["is_shareable"]:
        raise HTTPException(status_code=404, detail="Collection not found")
    coll = result.data[0]

    # Step 2: Fetch spots capped at 200, ordered by added_at ASC
    cs_result = (
        supabase.table("collection_spots")
        .select("spot_id")
        .eq("collection_id", str(collection_id))
        .order("added_at")
        .limit(200)
        .execute()
    )
    if not cs_result.data:
        return PublicCollectionResponse(
            id=coll["id"], name=coll["name"], spot_count=0, spots=[]
        )
    spot_ids = [row["spot_id"] for row in cs_result.data]

    # Step 3: Batch fetch spot rows, re-sort to preserve added_at ASC order
    spots_result = supabase.table("spots").select("*").in_("id", spot_ids).execute()
    spot_map = {row["id"]: row for row in spots_result.data}
    spots = [_build_spot_pin(spot_map[sid]) for sid in spot_ids if sid in spot_map]

    return PublicCollectionResponse(
        id=coll["id"],
        name=coll["name"],
        spot_count=len(spots),
        spots=spots,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_saved_service.py::TestAddSpotToCollection tests/test_saved_service.py::TestRemoveSpotFromCollection tests/test_saved_service.py::TestGetPublicCollection -v
```

Expected: All tests pass.

- [ ] **Step 5: Run all service tests**

```bash
.venv/bin/python -m pytest tests/test_saved_service.py -v
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/saved/service.py tests/test_saved_service.py
git commit -m "feat: add add/remove spot to collection and get_public_collection"
```

---

### Task 7: Router and main.py Registration

**Files:**
- Create: `app/saved/router.py`
- Modify: `app/main.py`
- Create: `tests/test_saved_router.py`

- [ ] **Step 1: Write failing router tests**

```python
# tests/test_saved_router.py
from __future__ import annotations

import uuid
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app

# Bypass auth for router tests — patch get_current_user to return a fake user
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


@pytest.fixture
def client():
    return TestClient(app)


class TestSavedSpotsEndpoints:
    def test_get_saved_spots_requires_auth(self, client):
        resp = client.get("/me/saved-spots")
        assert resp.status_code == 403

    @patch("app.saved.router.get_current_user", return_value=FAKE_USER)
    @patch("app.saved.service.list_saved_spots")
    def test_get_saved_spots_returns_200(self, mock_list, mock_auth, client):
        from app.saved.schemas import SavedSpotsResponse
        mock_list.return_value = SavedSpotsResponse(spots=[])
        resp = client.get(
            "/me/saved-spots",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"spots": []}

    @patch("app.saved.router.get_current_user", return_value=FAKE_USER)
    @patch("app.saved.service.save_spot")
    def test_post_saved_spots_returns_200(self, mock_save, mock_auth, client):
        from app.saved.schemas import SavedSpotResponse, SavedSpotsResponse
        from app.spots.schemas import SpotPin
        from app.db.models import SpotCategory, AccessType
        pin = SpotPin(
            id=uuid.UUID(SPOT_ID), name="Test Cafe", short_address=None,
            latitude=51.5, longitude=-0.1, category=SpotCategory.cafe,
            access_type=AccessType.free, wifi_available=True, power_outlets=True,
            noise_matrix=None, rating=None, is_open_now=None, cover_photo=None,
        )
        from datetime import timezone
        mock_save.return_value = SavedSpotResponse(
            spot=pin,
            saved_at=datetime.fromisoformat(NOW),
            collection_ids=[],
        )
        resp = client.post(
            "/me/saved-spots",
            json={"spot_id": SPOT_ID},
            headers={"Authorization": "Bearer fake-token"},
        )
        assert resp.status_code == 200

    @patch("app.saved.router.get_current_user", return_value=FAKE_USER)
    @patch("app.saved.service.unsave_spot")
    def test_delete_saved_spot_returns_204(self, mock_unsave, mock_auth, client):
        mock_unsave.return_value = None
        resp = client.delete(
            f"/me/saved-spots/{SPOT_ID}",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert resp.status_code == 204


class TestCollectionsEndpoints:
    @patch("app.saved.router.get_current_user", return_value=FAKE_USER)
    @patch("app.saved.service.list_collections")
    def test_get_collections_returns_200(self, mock_list, mock_auth, client):
        from app.saved.schemas import CollectionListResponse
        mock_list.return_value = CollectionListResponse(collections=[])
        resp = client.get(
            "/me/collections",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert resp.status_code == 200

    @patch("app.saved.router.get_current_user", return_value=FAKE_USER)
    @patch("app.saved.service.create_collection")
    def test_post_collections_returns_201(self, mock_create, mock_auth, client):
        from app.saved.schemas import CollectionResponse
        mock_create.return_value = CollectionResponse(
            id=uuid.UUID(COLL_ID), name="My List", is_shareable=False,
            spot_count=0, created_at=datetime.fromisoformat(NOW),
            updated_at=datetime.fromisoformat(NOW),
        )
        resp = client.post(
            "/me/collections",
            json={"name": "My List"},
            headers={"Authorization": "Bearer fake-token"},
        )
        assert resp.status_code == 201

    @patch("app.saved.router.get_current_user", return_value=FAKE_USER)
    @patch("app.saved.service.delete_collection")
    def test_delete_collection_returns_204(self, mock_del, mock_auth, client):
        mock_del.return_value = None
        resp = client.delete(
            f"/me/collections/{COLL_ID}",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert resp.status_code == 204


class TestPublicCollectionEndpoint:
    @patch("app.saved.service.get_public_collection")
    def test_public_endpoint_no_auth_required(self, mock_get, client):
        from app.saved.schemas import PublicCollectionResponse
        mock_get.return_value = PublicCollectionResponse(
            id=uuid.UUID(COLL_ID), name="Shared", spot_count=0, spots=[]
        )
        resp = client.get(f"/collections/{COLL_ID}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Shared"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_saved_router.py -v 2>&1 | head -20
```

Expected: `ImportError` — `app.saved.router` does not exist.

- [ ] **Step 3: Create the router**

```python
# app/saved/router.py
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response

from app.dependencies import get_current_user
from app.saved.schemas import (
    AddSpotToCollectionRequest,
    CollectionListResponse,
    CollectionResponse,
    CreateCollectionRequest,
    PublicCollectionResponse,
    SavedSpotResponse,
    SavedSpotsResponse,
    SaveSpotRequest,
    UpdateCollectionRequest,
)
from app.saved.service import (
    add_spot_to_collection,
    create_collection,
    delete_collection,
    get_public_collection,
    list_collections,
    list_saved_spots,
    remove_spot_from_collection,
    save_spot,
    unsave_spot,
    update_collection,
)

router = APIRouter(tags=["saved"])


@router.get("/me/saved-spots", response_model=SavedSpotsResponse)
async def get_saved_spots(
    collection_id: Optional[uuid.UUID] = Query(None),
    user: dict = Depends(get_current_user),
) -> SavedSpotsResponse:
    """List saved spots. Filter by collection_id to see only spots in that collection."""
    return list_saved_spots(uuid.UUID(user["sub"]), collection_id)


@router.post("/me/saved-spots", response_model=SavedSpotResponse)
async def post_saved_spot(
    payload: SaveSpotRequest,
    user: dict = Depends(get_current_user),
) -> SavedSpotResponse:
    """Save a spot. Optionally add to one or more collections in the same call."""
    return save_spot(uuid.UUID(user["sub"]), payload.spot_id, payload.collection_ids)


@router.delete("/me/saved-spots/{spot_id}")
async def delete_saved_spot(
    spot_id: uuid.UUID,
    user: dict = Depends(get_current_user),
) -> Response:
    """Unsave a spot. Also removes it from all of the user's collections."""
    unsave_spot(uuid.UUID(user["sub"]), spot_id)
    return Response(status_code=204)


@router.get("/me/collections", response_model=CollectionListResponse)
async def get_collections(
    user: dict = Depends(get_current_user),
) -> CollectionListResponse:
    """List all of the user's collections with spot counts."""
    return list_collections(uuid.UUID(user["sub"]))


@router.post("/me/collections", response_model=CollectionResponse, status_code=201)
async def post_collection(
    payload: CreateCollectionRequest,
    user: dict = Depends(get_current_user),
) -> CollectionResponse:
    """Create a collection. Use source_collection_id to copy a shareable collection."""
    return create_collection(uuid.UUID(user["sub"]), payload.name, payload.source_collection_id)


@router.patch("/me/collections/{collection_id}", response_model=CollectionResponse)
async def patch_collection(
    collection_id: uuid.UUID,
    payload: UpdateCollectionRequest,
    user: dict = Depends(get_current_user),
) -> CollectionResponse:
    """Rename or toggle is_shareable on a collection."""
    return update_collection(uuid.UUID(user["sub"]), collection_id, payload)


@router.delete("/me/collections/{collection_id}")
async def delete_collection_route(
    collection_id: uuid.UUID,
    user: dict = Depends(get_current_user),
) -> Response:
    """Delete a collection. Spots remain saved."""
    delete_collection(uuid.UUID(user["sub"]), collection_id)
    return Response(status_code=204)


@router.post("/me/collections/{collection_id}/spots", response_model=SavedSpotResponse)
async def post_spot_to_collection(
    collection_id: uuid.UUID,
    payload: AddSpotToCollectionRequest,
    user: dict = Depends(get_current_user),
) -> SavedSpotResponse:
    """Add a spot to a collection. Also saves the spot if not already saved."""
    return add_spot_to_collection(uuid.UUID(user["sub"]), collection_id, payload.spot_id)


@router.delete("/me/collections/{collection_id}/spots/{spot_id}")
async def delete_spot_from_collection(
    collection_id: uuid.UUID,
    spot_id: uuid.UUID,
    user: dict = Depends(get_current_user),
) -> Response:
    """Remove a spot from a collection. Does not unsave the spot."""
    remove_spot_from_collection(uuid.UUID(user["sub"]), collection_id, spot_id)
    return Response(status_code=204)


@router.get("/collections/{collection_id}", response_model=PublicCollectionResponse)
async def get_public_collection_route(
    collection_id: uuid.UUID,
) -> PublicCollectionResponse:
    """View a shareable collection and its spots. No auth required. Returns 404 if not shareable."""
    return get_public_collection(collection_id)
```

- [ ] **Step 4: Register the router in main.py**

In `app/main.py`, add after the existing imports:
```python
from app.saved.router import router as saved_router
```

And after `app.include_router(suggestions_router)`:
```python
app.include_router(saved_router)
```

The updated `main.py`:

```python
# app/main.py
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.admin.router import router as admin_router
from app.saved.router import router as saved_router
from app.spots.router import router as spots_router
from app.suggestions.router import router as suggestions_router
from app.config import settings
from app.db.database import supabase
from app.google_places.client import google_places_client

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    google_places_client.close()


app = FastAPI(
    title="Spotsvc API",
    description="Backend for the London Work Spots app",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url="/redoc" if settings.app_env != "production" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_router, prefix="/admin", tags=["admin"])
app.include_router(spots_router, prefix="/spots", tags=["spots"])
app.include_router(suggestions_router)
app.include_router(saved_router)


@app.get("/health", tags=["meta"])
async def health_check():
    try:
        supabase.table("spots").select("id").limit(1).execute()
        db_status = "ok"
    except Exception as exc:
        logger.error("Health check DB ping failed: %s", exc, exc_info=True)
        db_status = str(exc)
    admin_pwd_set = bool(settings.admin_pwd)
    return {"status": "ok", "db": db_status, "admin_pwd_set": admin_pwd_set}
```

- [ ] **Step 5: Run router tests**

```bash
.venv/bin/python -m pytest tests/test_saved_router.py -v
```

Expected: All tests pass.

- [ ] **Step 6: Run the full test suite**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: All tests across all test files pass.

- [ ] **Step 7: Commit**

```bash
git add app/saved/router.py app/main.py tests/test_saved_router.py
git commit -m "feat: add saved spots router and register with FastAPI app"
```

---

## Summary

After completing all tasks, the following is implemented:

| Task | Deliverable |
|------|-------------|
| 1 | DB tables + RLS policies (manual SQL) |
| 2 | `app/saved/schemas.py` — all Pydantic models |
| 3 | `save_spot`, `unsave_spot` service functions |
| 4 | `list_saved_spots` service function (filtered + unfiltered) |
| 5 | `list_collections`, `create_collection`, `update_collection`, `delete_collection` |
| 6 | `add_spot_to_collection`, `remove_spot_from_collection`, `get_public_collection` |
| 7 | `app/saved/router.py` — 10 endpoints; `app/main.py` updated |
