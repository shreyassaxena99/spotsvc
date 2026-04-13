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

## Migration Script

`scripts/migrate_photo_references.py` — a standalone script to backfill `photo_place_id` and `photo_references` on all existing spots that don't have them yet.

### Behaviour

1. Query all spots where `photo_references IS NULL` and `is_active = TRUE`.
2. For each spot, call `google_places_client.get_details(google_place_id)` to get a fresh API response.
3. Extract the bare reference tokens (`photo_references`) from the response, set `photo_place_id = google_place_id`.
4. `UPDATE` the spot row with the two new columns.
5. Sleep 200 ms between calls to stay well within Google's QPS limits.
6. On error (Google API failure, DB failure), log and skip — continue to the next spot.
7. Print a summary: total processed, succeeded, skipped.

### Running the script

```bash
# from the repo root with .env loaded
python scripts/migrate_photo_references.py
```

The script uses the same `settings` / `supabase` / `google_places_client` singletons as the app, so `.env` (or env vars) must be present.

### Implementation notes

- Import `app.db.database.supabase`, `app.google_places.client.google_places_client`, and `app.config.settings` directly — no need to start the FastAPI app.
- Fetch all candidate spots in a single query (no pagination needed for the small dataset).
- The `photos` column is left untouched — the script only writes to the two new columns.

## Out of Scope

- Admin panel frontend update for `photo_references` rename on `PlaceDetails`
- Caching layer (no Redis available)
