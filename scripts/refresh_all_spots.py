from __future__ import annotations

import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.admin.service import refresh_spot
from app.db.database import supabase

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DELAY_SECONDS = 0.5


def run(active_only: bool = True) -> None:
    query = supabase.table("spots").select("id, name, google_place_id")
    if active_only:
        query = query.eq("is_active", True)
    result = query.order("created_at").execute()
    spots = result.data

    logger.info(
        "Refreshing %d %s spot(s)…",
        len(spots),
        "active" if active_only else "all",
    )

    succeeded = 0
    failed = 0

    for spot in spots:
        spot_id = spot["id"]
        name = spot.get("name", spot_id)
        try:
            import uuid
            refresh_spot(uuid.UUID(spot_id))
            logger.info("OK  %s (%s)", name, spot_id)
            succeeded += 1
        except Exception as exc:
            logger.error("ERR %s (%s): %s", name, spot_id, exc)
            failed += 1
        time.sleep(DELAY_SECONDS)

    logger.info("Done. Succeeded: %d  Failed: %d", succeeded, failed)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Refresh Google Places data for all spots")
    parser.add_argument(
        "--all",
        dest="all_spots",
        action="store_true",
        help="Include inactive spots (default: active only)",
    )
    args = parser.parse_args()
    run(active_only=not args.all_spots)
