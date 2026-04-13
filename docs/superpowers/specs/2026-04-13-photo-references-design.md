# Photo References Design

**Date:** 2026-04-13
**Status:** Approved

## Problem

The `photos` column on the `spots` table stores full Google Places API media URLs:

```
https://places.googleapis.com/v1/places/{place_id}/photos/{photo_reference}/media?maxHeightPx=800&key=...
```

Photo references expire. When they do, the iOS app receives a `400 INVALID_ARGUMENT` from Google and photos fail to load.

## Solution

Store only bare photo reference tokens in the DB. Construct fresh media URLs at serve time by injecting the current API key and the stored reference tokens.

## DB Schema

The following columns have already been added to the `spots` table:

```sql
ALTER TABLE spots
  ADD COLUMN photo_place_id   text,
  ADD COLUMN photo_references text[];
```

The old `photos` column (text[]) is kept for now but will no longer be populated.

- `photo_place_id` — the Google Place ID (same as `google_place_id`; stored here for self-contained photo URL construction)
- `photo_references` — bare reference tokens extracted from Google's `photos[].name` field (format: `places/{id}/photos/{ref}`, we store only the `{ref}` segment)

## Data Flow

```
Google API response
  → extract bare tokens from photos[].name
  → store in photo_place_id + photo_references[]
                   ↓
     GET /spots/:id (serve time)
  → build_photo_url(photo_place_id, ref) per token
  → return fresh URLs in response.photos[]
```

## Changes

### `google_places/schemas.py`

Rename `photos: list[str]` → `photo_references: list[str]` on `PlaceDetails`.

**Note:** `GET /admin/google-place/{place_id}` returns `PlaceDetails` directly; the admin panel's place preview will need a frontend update to read `photo_references` instead of `photos`.

### `google_places/client.py`

- `get_details()`: extract bare tokens from `p['name']` using `p['name'].split('/photos/')[1]`, store in `photo_references`.
- Add `build_photo_url(place_id: str, photo_ref: str, max_height: int = 800) -> str` — constructs the full Google media URL at call time, pulling `GOOGLE_PLACES_API_KEY` from settings.

### `admin/service.py`

- `create_spot()`: write `photo_place_id` and `photo_references` to DB; remove `photos` from the insert payload.
- `_build_spot_response()`: build fresh URLs via `build_photo_url` from `data["photo_place_id"]` + `data["photo_references"]`; assign to the `photos` field on `SpotResponse` (field name unchanged — admin panel still sees a list of URLs).

### `spots/service.py`

- Import `build_photo_url`.
- `_build_spot_pin()` / `_build_spot_detail()`: build fresh URL list from `photo_place_id` + `photo_references`; use `[0]` for `cover_photo`.
- Fallback: if either field is `None` or empty, `photos = []` and `cover_photo = None` (handles existing rows with no references yet).
- Remove `_extract_cover_photo()` — no longer needed as a separate helper.

## Caching

No caching. No Redis in the project; URL construction is pure string interpolation with no I/O.

## iOS Compatibility

The `photos: list[str]` field on `SpotDetail` and `cover_photo: Optional[str]` on `SpotPin` are unchanged. The iOS app receives fresh URLs without any client-side changes.

## Out of Scope

- Migration of existing rows (re-fetching Google data to backfill `photo_references`) — separate operational task
- Admin panel frontend update for `photo_references` rename on `PlaceDetails`
- Caching layer (no Redis available)
