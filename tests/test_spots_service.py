from __future__ import annotations

import uuid


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

    def test_returns_empty_when_references_is_empty_list(self):
        from app.spots.service import _build_photo_urls

        assert _build_photo_urls({"photo_place_id": "ChIJabc", "photo_references": []}) == []


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
