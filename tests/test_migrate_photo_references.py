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
