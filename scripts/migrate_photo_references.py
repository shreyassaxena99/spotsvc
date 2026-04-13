from __future__ import annotations

import logging
import os
import sys
import time

# Ensure the repo root is on sys.path so `app` is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import supabase
from app.google_places.client import google_places_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def run() -> None:
    # Only migrate active spots. Inactive spots can be migrated if/when reactivated
    # via the admin panel, which will call get_details() and store fresh references.
    result = (
        supabase.table("spots")
        .select("id, google_place_id")
        .is_("photo_references", "null")
        .eq("is_active", True)
        .execute()
    )
    spots = result.data
    logger.info("Found %d active spots to migrate", len(spots))

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
