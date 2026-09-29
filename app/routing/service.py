from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"


def walking_route(
    origin_latitude: float,
    origin_longitude: float,
    destination_latitude: float,
    destination_longitude: float,
) -> Optional[tuple[int, int]]:
    """Return (walking distance metres, walking minutes), if Google can route it."""
    api_key = settings.google_routes_api_key or settings.google_places_api_key
    payload = {
        "origin": {"location": {"latLng": {"latitude": origin_latitude, "longitude": origin_longitude}}},
        "destination": {"location": {"latLng": {"latitude": destination_latitude, "longitude": destination_longitude}}},
        "travelMode": "WALK",
        "languageCode": "en-GB",
        "units": "METRIC",
    }
    try:
        response = httpx.post(
            ROUTES_URL,
            headers={
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": "routes.distanceMeters,routes.duration",
            },
            json=payload,
            timeout=4.0,
        )
        response.raise_for_status()
        routes = response.json().get("routes") or []
        if not routes:
            return None
        distance = routes[0].get("distanceMeters")
        duration = routes[0].get("duration", "")
        seconds = float(duration.removesuffix("s")) if duration.endswith("s") else 0
        if distance is None:
            return None
        return int(distance), max(1, round(seconds / 60))
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        logger.warning("Walking route lookup failed: %s", exc)
        return None
