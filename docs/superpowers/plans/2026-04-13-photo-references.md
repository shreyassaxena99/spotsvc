# Photo References Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store bare Google photo reference tokens in the DB and construct fresh media URLs at serve time so expired references never break the iOS app.

**Architecture:** `google_places/client.py` extracts bare tokens (not full URLs) from the Google API response and exposes a `build_photo_url()` helper. `admin/service.py` stores tokens on ingest. `spots/service.py` and `admin/service.py` call `build_photo_url()` at serve time. A standalone migration script backfills existing rows.

**Tech Stack:** Python 3.12, FastAPI, supabase-py v2, requests, pytest, unittest.mock

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `app/google_places/schemas.py` | Modify | Rename `photos` → `photo_references` on `PlaceDetails` |
| `app/google_places/client.py` | Modify | Extract bare tokens; add `build_photo_url()` |
| `app/spots/service.py` | Modify | Build fresh URLs at serve time; remove `_extract_cover_photo` |
| `app/admin/service.py` | Modify | Write `photo_place_id`/`photo_references` on ingest; build fresh URLs in response builder |
| `scripts/migrate_photo_references.py` | Create | Backfill `photo_place_id` + `photo_references` on existing spots |
| `tests/test_google_places_client.py` | Create | Tests for `build_photo_url` and token extraction |
| `tests/test_spots_service.py` | Create | Tests for fresh URL building in spots service |
| `tests/test_admin_service.py` | Create | Tests for ingest payload and response builder |
| `tests/test_migrate_photo_references.py` | Create | Tests for migration script |

---

### Task 1: `build_photo_url` and token extraction in google_places

**Files:**
- Modify: `app/google_places/schemas.py`
- Modify: `app/google_places/client.py`
- Create: `tests/test_google_places_client.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_google_places_client.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestBuildPhotoUrl:
    def test_returns_correct_url(self):
        from app.google_places.client import build_photo_url

        url = build_photo_url("ChIJabc", "ATCDNfWBGAg0OPr")
        assert url == (
            "https://places.googleapis.com/v1/places/ChIJabc"
            "/photos/ATCDNfWBGAg0OPr/media"
            "?maxHeightPx=800&key=test-google-key"
        )

    def test_respects_custom_max_height(self):
        from app.google_places.client import build_photo_url

        url = build_photo_url("ChIJabc", "ATCDNfWBGAg0OPr", max_height=400)
        assert "maxHeightPx=400" in url
        assert "maxHeightPx=800" not in url


class TestGetDetailsPhotoExtraction:
    def test_extracts_bare_photo_references(self):
        from app.google_places.client import google_places_client

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "ChIJabc",
            "displayName": {"text": "Test Cafe"},
            "location": {"latitude": 51.5, "longitude": -0.1},
            "photos": [
                {"name": "places/ChIJabc/photos/ATCDNfWBGAg0OPr"},
                {"name": "places/ChIJabc/photos/BXYZabc123"},
            ],
        }

        with patch.object(google_places_client._session, "get", return_value=mock_response):
            result = google_places_client.get_details("ChIJabc")

        assert result.photo_references == ["ATCDNfWBGAg0OPr", "BXYZabc123"]

    def test_caps_references_at_five(self):
        from app.google_places.client import google_places_client

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "ChIJabc",
            "displayName": {"text": "Test Cafe"},
            "location": {"latitude": 51.5, "longitude": -0.1},
            "photos": [
                {"name": f"places/ChIJabc/photos/REF{i}"} for i in range(8)
            ],
        }

        with patch.object(google_places_client._session, "get", return_value=mock_response):
            result = google_places_client.get_details("ChIJabc")

        assert len(result.photo_references) == 5

    def test_returns_empty_list_when_no_photos(self):
        from app.google_places.client import google_places_client

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "ChIJabc",
            "displayName": {"text": "Test Cafe"},
            "location": {"latitude": 51.5, "longitude": -0.1},
        }

        with patch.object(google_places_client._session, "get", return_value=mock_response):
            result = google_places_client.get_details("ChIJabc")

        assert result.photo_references == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_google_places_client.py -v
```

Expected: `ImportError` or `AttributeError` — `build_photo_url` doesn't exist yet and `PlaceDetails` still has `photos`.

- [ ] **Step 3: Rename `photos` → `photo_references` in `PlaceDetails`**

In `app/google_places/schemas.py`, change line 33:

```python
# Before
photos: list[str] = []

# After
photo_references: list[str] = []
```

- [ ] **Step 4: Add `build_photo_url` and update token extraction in `client.py`**

In `app/google_places/client.py`, add `build_photo_url` as a module-level function after the imports (before the `GooglePlacesClient` class), and update the photo extraction block in `get_details`:

```python
# Add after imports, before GooglePlacesClient class definition:

def build_photo_url(place_id: str, photo_ref: str, max_height: int = 800) -> str:
    return (
        f"https://places.googleapis.com/v1/places/{place_id}"
        f"/photos/{photo_ref}/media"
        f"?maxHeightPx={max_height}&key={settings.google_places_api_key}"
    )
```

In `get_details`, replace the `photos` block (lines 104–111):

```python
# Before
photos = [
    (
        f"https://places.googleapis.com/v1/{p['name']}/media"
        f"?maxHeightPx=800&key={settings.google_places_api_key}"
    )
    for p in data.get("photos", [])[:5]
]

# After
photo_references = [
    p["name"].split("/photos/")[1]
    for p in data.get("photos", [])[:5]
]
```

In the `PlaceDetails(...)` constructor call at the bottom of `get_details`, change:

```python
# Before
photos=photos,

# After
photo_references=photo_references,
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_google_places_client.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/google_places/schemas.py app/google_places/client.py tests/test_google_places_client.py
git commit -m "feat: extract bare photo reference tokens; add build_photo_url"
```

---

### Task 2: Build fresh URLs at serve time in `spots/service.py`

**Files:**
- Modify: `app/spots/service.py`
- Create: `tests/test_spots_service.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_spots_service.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime


def _minimal_pin_row(**overrides) -> dict:
    row = {
        "id": str(uuid.uuid4()),
        "name": "Test Cafe",
        "short_address": "Soho, London",
        "latitude": 51.5,
        "longitude": -0.1,
        "category": "cafe",
        "access_type": "free",
        "wifi_available": True,
        "power_outlets": True,
        "noise_matrix": None,
        "rating": 4.5,
        "regular_hours": None,
        "timezone": None,
        "photo_place_id": "ChIJabc",
        "photo_references": ["ATCDNfWBGAg0OPr", "BXYZabc123"],
    }
    row.update(overrides)
    return row


def _minimal_detail_row(**overrides) -> dict:
    row = _minimal_pin_row()
    row.update({
        "formatted_address": "1 Test St, London",
        "phone_national": None,
        "google_maps_uri": None,
        "website_uri": None,
        "price_level": None,
        "user_rating_count": 100,
        "editorial_summary": None,
        "business_status": "OPERATIONAL",
        "regular_hours": None,
        "outdoor_seating": None,
        "restroom": None,
        "serves_coffee": True,
        "allows_dogs": None,
        "good_for_groups": None,
        "parking_options": None,
        "payment_options": None,
        "accessibility_options": None,
        "description": None,
        "created_at": "2026-04-13T00:00:00+00:00",
        "updated_at": "2026-04-13T00:00:00+00:00",
    })
    row.update(overrides)
    return row


class TestBuildPhotoUrls:
    def test_returns_fresh_urls(self):
        from app.spots.service import _build_photo_urls

        row = {"photo_place_id": "ChIJabc", "photo_references": ["ATCDNfWBGAg0OPr", "BXYZabc123"]}
        result = _build_photo_urls(row)
        assert result == [
            "https://places.googleapis.com/v1/places/ChIJabc/photos/ATCDNfWBGAg0OPr/media?maxHeightPx=800&key=test-google-key",
            "https://places.googleapis.com/v1/places/ChIJabc/photos/BXYZabc123/media?maxHeightPx=800&key=test-google-key",
        ]

    def test_returns_empty_when_no_place_id(self):
        from app.spots.service import _build_photo_urls

        assert _build_photo_urls({"photo_place_id": None, "photo_references": ["ATCDNfWBGAg0OPr"]}) == []

    def test_returns_empty_when_no_references(self):
        from app.spots.service import _build_photo_urls

        assert _build_photo_urls({"photo_place_id": "ChIJabc", "photo_references": None}) == []

    def test_returns_empty_when_both_missing(self):
        from app.spots.service import _build_photo_urls

        assert _build_photo_urls({}) == []


class TestBuildSpotPin:
    def test_cover_photo_is_first_fresh_url(self):
        from app.spots.service import _build_spot_pin

        pin = _build_spot_pin(_minimal_pin_row())
        assert pin.cover_photo == (
            "https://places.googleapis.com/v1/places/ChIJabc"
            "/photos/ATCDNfWBGAg0OPr/media?maxHeightPx=800&key=test-google-key"
        )

    def test_cover_photo_is_none_when_no_references(self):
        from app.spots.service import _build_spot_pin

        pin = _build_spot_pin(_minimal_pin_row(photo_place_id=None, photo_references=None))
        assert pin.cover_photo is None


class TestBuildSpotDetail:
    def test_photos_contains_all_fresh_urls(self):
        from app.spots.service import _build_spot_detail

        detail = _build_spot_detail(_minimal_detail_row())
        assert len(detail.photos) == 2
        assert detail.photos[0] == (
            "https://places.googleapis.com/v1/places/ChIJabc"
            "/photos/ATCDNfWBGAg0OPr/media?maxHeightPx=800&key=test-google-key"
        )

    def test_photos_is_empty_when_no_references(self):
        from app.spots.service import _build_spot_detail

        detail = _build_spot_detail(_minimal_detail_row(photo_place_id=None, photo_references=None))
        assert detail.photos == []

    def test_cover_photo_matches_first_photo(self):
        from app.spots.service import _build_spot_detail

        detail = _build_spot_detail(_minimal_detail_row())
        assert detail.cover_photo == detail.photos[0]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_spots_service.py -v
```

Expected: `ImportError` — `_build_photo_urls` doesn't exist yet.

- [ ] **Step 3: Update `spots/service.py`**

Add import at the top (alongside existing imports):

```python
from app.google_places.client import build_photo_url
```

Replace `_extract_cover_photo` with `_build_photo_urls`, and update `_build_spot_pin` and `_build_spot_detail`:

```python
# Remove _extract_cover_photo entirely.

def _build_photo_urls(row: dict) -> list[str]:
    place_id = row.get("photo_place_id")
    refs = row.get("photo_references") or []
    if not place_id or not refs:
        return []
    return [build_photo_url(place_id, ref) for ref in refs]


def _build_spot_pin(row: dict) -> SpotPin:
    photos = _build_photo_urls(row)
    return SpotPin(
        id=row["id"],
        name=row["name"],
        short_address=row.get("short_address"),
        latitude=row["latitude"],
        longitude=row["longitude"],
        category=row["category"],
        access_type=row["access_type"],
        wifi_available=row.get("wifi_available", True),
        power_outlets=row.get("power_outlets", True),
        noise_matrix=noise_matrix_from_db(row.get("noise_matrix")),
        rating=row.get("rating"),
        is_open_now=compute_is_open_now(row.get("regular_hours"), row.get("timezone")),
        cover_photo=photos[0] if photos else None,
    )


def _build_spot_detail(row: dict) -> SpotDetail:
    photos = _build_photo_urls(row)
    return SpotDetail(
        id=row["id"],
        name=row["name"],
        short_address=row.get("short_address"),
        latitude=row["latitude"],
        longitude=row["longitude"],
        category=row["category"],
        access_type=row["access_type"],
        wifi_available=row.get("wifi_available", True),
        power_outlets=row.get("power_outlets", True),
        noise_matrix=noise_matrix_from_db(row.get("noise_matrix")),
        rating=row.get("rating"),
        is_open_now=compute_is_open_now(row.get("regular_hours"), row.get("timezone")),
        cover_photo=photos[0] if photos else None,
        formatted_address=row.get("formatted_address"),
        phone_national=row.get("phone_national"),
        google_maps_uri=row.get("google_maps_uri"),
        website_uri=row.get("website_uri"),
        price_level=row.get("price_level"),
        user_rating_count=row.get("user_rating_count"),
        editorial_summary=row.get("editorial_summary"),
        business_status=row.get("business_status"),
        regular_hours=row.get("regular_hours"),
        photos=photos,
        outdoor_seating=row.get("outdoor_seating"),
        restroom=row.get("restroom"),
        serves_coffee=row.get("serves_coffee"),
        allows_dogs=row.get("allows_dogs"),
        good_for_groups=row.get("good_for_groups"),
        parking_options=row.get("parking_options"),
        payment_options=row.get("payment_options"),
        accessibility_options=row.get("accessibility_options"),
        description=row.get("description"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_spots_service.py -v
```

Expected: all 9 tests PASS.

- [ ] **Step 5: Run full test suite to confirm no regressions**

```bash
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/spots/service.py tests/test_spots_service.py
git commit -m "feat: build fresh photo URLs at serve time in spots service"
```

---

### Task 3: Store tokens on ingest and serve fresh URLs in `admin/service.py`

**Files:**
- Modify: `app/admin/service.py`
- Create: `tests/test_admin_service.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_admin_service.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch


def _chain(data=None):
    m = MagicMock()
    m.execute.return_value = MagicMock(data=data if data is not None else [], count=None)
    for method in ("select", "eq", "insert", "update", "ilike", "order", "range", "is_"):
        getattr(m, method).return_value = m
    return m


def _fake_place_details(place_id: str = "ChIJabc") -> MagicMock:
    d = MagicMock()
    d.name = "Test Cafe"
    d.formatted_address = "1 Test St, London"
    d.short_address = "Test St"
    d.latitude = 51.5
    d.longitude = -0.1
    d.phone_national = None
    d.phone_international = None
    d.google_maps_uri = None
    d.website_uri = None
    d.price_level = None
    d.rating = 4.5
    d.user_rating_count = 100
    d.editorial_summary = None
    d.business_status = "OPERATIONAL"
    d.timezone = "Europe/London"
    d.regular_hours = None
    d.current_hours = None
    d.photo_references = ["ATCDNfWBGAg0OPr"]
    d.outdoor_seating = None
    d.restroom = None
    d.serves_breakfast = None
    d.serves_lunch = None
    d.serves_dinner = None
    d.serves_brunch = None
    d.serves_coffee = True
    d.allows_dogs = None
    d.good_for_groups = None
    d.dine_in = None
    d.takeout = None
    d.delivery = None
    d.reservable = None
    d.parking_options = None
    d.payment_options = None
    d.accessibility_options = None
    return d


def _fake_spot_row(place_id: str = "ChIJabc") -> dict:
    return {
        "id": str(uuid.uuid4()),
        "google_place_id": place_id,
        "name": "Test Cafe",
        "formatted_address": "1 Test St, London",
        "short_address": "Test St",
        "latitude": 51.5,
        "longitude": -0.1,
        "phone_national": None,
        "phone_international": None,
        "google_maps_uri": None,
        "website_uri": None,
        "price_level": None,
        "rating": 4.5,
        "user_rating_count": 100,
        "editorial_summary": None,
        "business_status": "OPERATIONAL",
        "timezone": "Europe/London",
        "regular_hours": None,
        "current_hours": None,
        "photo_place_id": place_id,
        "photo_references": ["ATCDNfWBGAg0OPr"],
        "outdoor_seating": None,
        "restroom": None,
        "serves_breakfast": None,
        "serves_lunch": None,
        "serves_dinner": None,
        "serves_brunch": None,
        "serves_coffee": True,
        "allows_dogs": None,
        "good_for_groups": None,
        "dine_in": None,
        "takeout": None,
        "delivery": None,
        "reservable": None,
        "parking_options": None,
        "payment_options": None,
        "accessibility_options": None,
        "category": "cafe",
        "access_type": "free",
        "wifi_available": True,
        "power_outlets": True,
        "noise_matrix": None,
        "description": None,
        "admin_notes": None,
        "is_active": True,
        "google_data_updated_at": "2026-04-13T00:00:00+00:00",
        "created_at": "2026-04-13T00:00:00+00:00",
        "updated_at": "2026-04-13T00:00:00+00:00",
    }


class TestBuildSpotResponse:
    def test_photos_built_from_photo_references(self):
        from app.admin.service import _build_spot_response

        row = _fake_spot_row()
        result = _build_spot_response(row)
        assert result.photos == [
            "https://places.googleapis.com/v1/places/ChIJabc"
            "/photos/ATCDNfWBGAg0OPr/media?maxHeightPx=800&key=test-google-key"
        ]

    def test_photos_empty_when_no_references(self):
        from app.admin.service import _build_spot_response

        row = _fake_spot_row()
        row["photo_references"] = None
        row["photo_place_id"] = None
        result = _build_spot_response(row)
        assert result.photos == []


class TestCreateSpot:
    @patch("app.admin.service.google_places_client")
    @patch("app.admin.service.supabase")
    def test_insert_payload_has_photo_references_not_photos(self, mock_supabase, mock_gpc):
        from app.admin.service import create_spot
        from app.admin.schemas import CreateSpotRequest
        from app.db.models import AccessType, SpotCategory

        mock_gpc.get_details.return_value = _fake_place_details("ChIJabc")

        no_existing = _chain(data=[])
        insert_chain = _chain(data=[_fake_spot_row("ChIJabc")])
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[_fake_spot_row("ChIJabc")])

        payload = CreateSpotRequest(
            google_place_id="ChIJabc",
            category=SpotCategory.cafe,
            access_type=AccessType.free,
        )
        create_spot(payload, admin_user_id=None)

        insert_call_args = mock_supabase.table.return_value.insert.call_args
        inserted_data = insert_call_args[0][0]

        assert inserted_data.get("photo_place_id") == "ChIJabc"
        assert inserted_data.get("photo_references") == ["ATCDNfWBGAg0OPr"]
        assert "photos" not in inserted_data
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_admin_service.py -v
```

Expected: `AssertionError` — `_build_spot_response` still uses old `photos` field.

- [ ] **Step 3: Update `admin/service.py`**

Add `build_photo_url` to the existing import from `google_places.client`:

```python
# Before
from app.google_places.client import google_places_client

# After
from app.google_places.client import build_photo_url, google_places_client
```

Update `_build_spot_response` — replace `photos=data.get("photos") or []` with fresh URL construction:

```python
def _build_spot_response(data: dict) -> SpotResponse:
    place_id = data.get("photo_place_id") or data.get("google_place_id")
    refs = data.get("photo_references") or []
    photos = [build_photo_url(place_id, ref) for ref in refs] if place_id and refs else []
    return SpotResponse(
        id=data["id"],
        google_place_id=data["google_place_id"],
        name=data["name"],
        formatted_address=data.get("formatted_address"),
        short_address=data.get("short_address"),
        latitude=data["latitude"],
        longitude=data["longitude"],
        phone_national=data.get("phone_national"),
        phone_international=data.get("phone_international"),
        google_maps_uri=data.get("google_maps_uri"),
        website_uri=data.get("website_uri"),
        price_level=data.get("price_level"),
        rating=data.get("rating"),
        user_rating_count=data.get("user_rating_count"),
        editorial_summary=data.get("editorial_summary"),
        business_status=data.get("business_status"),
        timezone=data.get("timezone"),
        regular_hours=data.get("regular_hours"),
        current_hours=data.get("current_hours"),
        photos=photos,
        outdoor_seating=data.get("outdoor_seating"),
        restroom=data.get("restroom"),
        serves_breakfast=data.get("serves_breakfast"),
        serves_lunch=data.get("serves_lunch"),
        serves_dinner=data.get("serves_dinner"),
        serves_brunch=data.get("serves_brunch"),
        serves_coffee=data.get("serves_coffee"),
        allows_dogs=data.get("allows_dogs"),
        good_for_groups=data.get("good_for_groups"),
        dine_in=data.get("dine_in"),
        takeout=data.get("takeout"),
        delivery=data.get("delivery"),
        reservable=data.get("reservable"),
        parking_options=data.get("parking_options"),
        payment_options=data.get("payment_options"),
        accessibility_options=data.get("accessibility_options"),
        category=data["category"],
        access_type=data["access_type"],
        wifi_available=data.get("wifi_available", True),
        power_outlets=data.get("power_outlets", True),
        noise_matrix=noise_matrix_from_db(data.get("noise_matrix")),
        description=data.get("description"),
        admin_notes=data.get("admin_notes"),
        is_active=data.get("is_active", True),
        google_data_updated_at=data.get("google_data_updated_at"),
        created_at=data["created_at"],
        updated_at=data["updated_at"],
    )
```

In `create_spot`, in the `spot_data` dict (around line 115), replace the `photos` entry with the two new fields:

```python
# Remove this line:
"photos": place.photos,

# Add these two lines in its place:
"photo_place_id": payload.google_place_id,
"photo_references": place.photo_references,
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_admin_service.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Run full test suite**

```bash
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/admin/service.py tests/test_admin_service.py
git commit -m "feat: store photo reference tokens on ingest; build fresh URLs in admin responses"
```

---

### Task 4: Migration script

**Files:**
- Create: `scripts/migrate_photo_references.py`
- Create: `tests/test_migrate_photo_references.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_migrate_photo_references.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock, call, patch


class TestMigratePhotoReferences:
    @patch("scripts.migrate_photo_references.google_places_client")
    @patch("scripts.migrate_photo_references.supabase")
    def test_updates_spot_with_photo_references(self, mock_supabase, mock_gpc):
        from scripts.migrate_photo_references import run

        mock_supabase.table.return_value.select.return_value.is_.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "spot-1", "google_place_id": "ChIJabc"}]
        )

        mock_details = MagicMock()
        mock_details.photo_references = ["ATCDNfWBGAg0OPr", "BXYZabc123"]
        mock_gpc.get_details.return_value = mock_details

        update_chain = MagicMock()
        update_chain.eq.return_value.execute.return_value = MagicMock(data=[{}])
        mock_supabase.table.return_value.update.return_value = update_chain

        run()

        mock_gpc.get_details.assert_called_once_with("ChIJabc")
        mock_supabase.table.return_value.update.assert_called_once_with({
            "photo_place_id": "ChIJabc",
            "photo_references": ["ATCDNfWBGAg0OPr", "BXYZabc123"],
        })
        update_chain.eq.assert_called_once_with("id", "spot-1")

    @patch("scripts.migrate_photo_references.google_places_client")
    @patch("scripts.migrate_photo_references.supabase")
    def test_skips_spot_on_google_api_error(self, mock_supabase, mock_gpc):
        from scripts.migrate_photo_references import run

        mock_supabase.table.return_value.select.return_value.is_.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {"id": "spot-1", "google_place_id": "ChIJfail"},
                {"id": "spot-2", "google_place_id": "ChIJok"},
            ]
        )

        ok_details = MagicMock()
        ok_details.photo_references = ["REFok"]
        mock_gpc.get_details.side_effect = [Exception("API error"), ok_details]

        update_chain = MagicMock()
        update_chain.eq.return_value.execute.return_value = MagicMock(data=[{}])
        mock_supabase.table.return_value.update.return_value = update_chain

        run()  # should not raise

        # Only the second spot should have been updated
        mock_supabase.table.return_value.update.assert_called_once_with({
            "photo_place_id": "ChIJok",
            "photo_references": ["REFok"],
        })

    @patch("scripts.migrate_photo_references.google_places_client")
    @patch("scripts.migrate_photo_references.supabase")
    def test_does_nothing_when_all_spots_already_migrated(self, mock_supabase, mock_gpc):
        from scripts.migrate_photo_references import run

        mock_supabase.table.return_value.select.return_value.is_.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )

        run()

        mock_gpc.get_details.assert_not_called()
        mock_supabase.table.return_value.update.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_migrate_photo_references.py -v
```

Expected: `ModuleNotFoundError` — script doesn't exist yet.

- [ ] **Step 3: Create `scripts/migrate_photo_references.py`**

First ensure the `scripts/` directory exists:

```bash
mkdir -p scripts
touch scripts/__init__.py
```

Create `scripts/migrate_photo_references.py`:

```python
from __future__ import annotations

import logging
import time

from app.db.database import supabase
from app.google_places.client import google_places_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def run() -> None:
    result = (
        supabase.table("spots")
        .select("id, google_place_id")
        .is_("photo_references", "null")
        .eq("is_active", True)
        .execute()
    )
    spots = result.data
    logger.info("Found %d spots to migrate", len(spots))

    succeeded = 0
    skipped = 0

    for spot in spots:
        spot_id = spot["id"]
        place_id = spot["google_place_id"]
        try:
            details = google_places_client.get_details(place_id)
            supabase.table("spots").update(
                {
                    "photo_place_id": place_id,
                    "photo_references": details.photo_references,
                }
            ).eq("id", spot_id).execute()
            logger.info(
                "Migrated %s (%s): %d references", spot_id, place_id, len(details.photo_references)
            )
            succeeded += 1
        except Exception as exc:
            logger.error("Failed to migrate spot %s (%s): %s", spot_id, place_id, exc)
            skipped += 1
        time.sleep(0.2)

    logger.info("Done. Succeeded: %d, Skipped: %d", succeeded, skipped)


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_migrate_photo_references.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Run full test suite**

```bash
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/__init__.py scripts/migrate_photo_references.py tests/test_migrate_photo_references.py
git commit -m "feat: add migration script to backfill photo reference tokens"
```

---

## Running the Migration

After deploying the code changes, run the migration against production:

```bash
# Ensure .env is present with production credentials, then:
python scripts/migrate_photo_references.py
```

The script is idempotent — it only touches rows where `photo_references IS NULL`, so it is safe to re-run.
