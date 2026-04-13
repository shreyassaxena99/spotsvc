from __future__ import annotations

import logging

import requests

from app.config import settings
from app.google_places.schemas import PlaceDetails, PlaceSuggestion

logger = logging.getLogger(__name__)

PLACES_BASE_URL = "https://places.googleapis.com/v1"

# Bias autocomplete results toward central London (20km radius)
_LONDON_LOCATION_BIAS = {
    "circle": {
        "center": {"latitude": 51.5074, "longitude": -0.1278},
        "radius": 20000.0,
    }
}

_DETAIL_FIELD_MASK = ",".join([
    "id",
    "displayName",
    "formattedAddress",
    "shortFormattedAddress",
    "location",
    "nationalPhoneNumber",
    "internationalPhoneNumber",
    "googleMapsUri",
    "websiteUri",
    "priceLevel",
    "rating",
    "userRatingCount",
    "editorialSummary",
    "businessStatus",
    "regularOpeningHours",
    "currentOpeningHours",
    "photos",
    "outdoorSeating",
    "restroom",
    "servesBreakfast",
    "servesLunch",
    "servesDinner",
    "servesBrunch",
    "servesCoffee",
    "allowsDogs",
    "goodForGroups",
    "dineIn",
    "takeout",
    "delivery",
    "reservable",
    "parkingOptions",
    "paymentOptions",
    "accessibilityOptions",
    "timeZone",
])


def build_photo_url(place_id: str, photo_ref: str, max_height: int = 800) -> str:
    return (
        f"https://places.googleapis.com/v1/places/{place_id}"
        f"/photos/{photo_ref}/media"
        f"?maxHeightPx={max_height}&key={settings.google_places_api_key}"
    )


class GooglePlacesClient:
    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update({"X-Goog-Api-Key": settings.google_places_api_key})

    def autocomplete(self, query: str) -> list[PlaceSuggestion]:
        response = self._session.post(
            f"{PLACES_BASE_URL}/places:autocomplete",
            json={
                "input": query,
                "locationBias": _LONDON_LOCATION_BIAS,
            },
        )
        response.raise_for_status()
        data = response.json()

        suggestions: list[PlaceSuggestion] = []
        for item in data.get("suggestions", []):
            pred = item.get("placePrediction", {})
            if not pred:
                continue
            suggestions.append(
                PlaceSuggestion(
                    place_id=pred.get("placeId", ""),
                    text=pred.get("text", {}).get("text", ""),
                    secondary_text=(
                        pred.get("structuredFormat", {})
                        .get("secondaryText", {})
                        .get("text")
                    ),
                )
            )
        return suggestions

    def get_details(self, place_id: str) -> PlaceDetails:
        response = self._session.get(
            f"{PLACES_BASE_URL}/places/{place_id}",
            headers={"X-Goog-FieldMask": _DETAIL_FIELD_MASK},
        )
        response.raise_for_status()
        data = response.json()

        location = data.get("location", {})

        # Extract bare photo reference tokens — capped at 5 to avoid excessive payload
        photo_references = [
            parts[1]
            for p in data.get("photos", [])[:5]
            if len(parts := p.get("name", "").split("/photos/")) == 2
        ]

        editorial = data.get("editorialSummary")
        tz = data.get("timeZone")

        return PlaceDetails(
            place_id=data.get("id", place_id),
            name=data.get("displayName", {}).get("text", ""),
            formatted_address=data.get("formattedAddress"),
            short_address=data.get("shortFormattedAddress"),
            latitude=location.get("latitude", 0.0),
            longitude=location.get("longitude", 0.0),
            phone_national=data.get("nationalPhoneNumber"),
            phone_international=data.get("internationalPhoneNumber"),
            google_maps_uri=data.get("googleMapsUri"),
            website_uri=data.get("websiteUri"),
            price_level=data.get("priceLevel"),
            rating=data.get("rating"),
            user_rating_count=data.get("userRatingCount"),
            editorial_summary=editorial.get("text") if editorial else None,
            business_status=data.get("businessStatus"),
            timezone=tz.get("id") if tz else None,
            regular_hours=data.get("regularOpeningHours"),
            current_hours=data.get("currentOpeningHours"),
            photo_references=photo_references,
            outdoor_seating=data.get("outdoorSeating"),
            restroom=data.get("restroom"),
            serves_breakfast=data.get("servesBreakfast"),
            serves_lunch=data.get("servesLunch"),
            serves_dinner=data.get("servesDinner"),
            serves_brunch=data.get("servesBrunch"),
            serves_coffee=data.get("servesCoffee"),
            allows_dogs=data.get("allowsDogs"),
            good_for_groups=data.get("goodForGroups"),
            dine_in=data.get("dineIn"),
            takeout=data.get("takeout"),
            delivery=data.get("delivery"),
            reservable=data.get("reservable"),
            parking_options=data.get("parkingOptions"),
            payment_options=data.get("paymentOptions"),
            accessibility_options=data.get("accessibilityOptions"),
        )

    def close(self) -> None:
        self._session.close()


google_places_client = GooglePlacesClient()
