from __future__ import annotations

import uuid
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
