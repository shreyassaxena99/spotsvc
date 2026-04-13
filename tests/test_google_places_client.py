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

    def test_skips_photo_with_malformed_name(self):
        from app.google_places.client import google_places_client

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "ChIJabc",
            "displayName": {"text": "Test Cafe"},
            "location": {"latitude": 51.5, "longitude": -0.1},
            "photos": [
                {"name": "places/ChIJabc/photos/GOODREF"},
                {"name": "malformed-no-photos-segment"},
                {},  # missing name key
            ],
        }

        with patch.object(google_places_client._session, "get", return_value=mock_response):
            result = google_places_client.get_details("ChIJabc")

        assert result.photo_references == ["GOODREF"]
