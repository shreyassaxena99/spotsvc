# Saved Spots & Collections Design Spec

**Date:** 2026-03-15
**Status:** Approved
**Feature:** User saved spots with optional named collections and shareable collection links

---

## Overview

Users can save spots to a personal saved list and optionally organise them into named collections. A spot can be saved standalone (without belonging to any collection) or added to one or more named collections simultaneously. Collections can be made shareable via a link — recipients can view the collection and save it to their own account.

---

## Key Design Decisions

- **Two distinct states:** saved (standalone) vs collection membership — not mutually exclusive
- **Multi-collection:** a spot can belong to multiple collections at the same time
- **Implicit save on collection add:** adding a spot to a collection also saves it if not already saved
- **Explicit unsave cascades:** unsaving a spot removes it from all of the user's collections
- **Collection delete does not unsave:** deleting a collection leaves the spots saved
- **Sharing is opt-in per collection:** `is_shareable` flag, off by default
- **Collection cap:** max 50 collections per user; enforced in the service layer (raise 422 if exceeded)
- **Public collection spot cap:** `GET /collections/{id}` returns at most 200 spots, ordered by `added_at ASC`

---

## Data Model

### Existing Table (unchanged)

```sql
-- saved_spots already exists — no changes
CREATE TABLE saved_spots (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL,
    spot_id    UUID NOT NULL REFERENCES spots(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, spot_id)
);
```

### New Tables

```sql
CREATE TABLE collections (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL,
    name         VARCHAR(100) NOT NULL,
    is_shareable BOOLEAN NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_collections_user ON collections (user_id);

CREATE TABLE collection_spots (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    collection_id UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    spot_id       UUID NOT NULL REFERENCES spots(id) ON DELETE CASCADE,
    added_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(collection_id, spot_id)
);

CREATE INDEX idx_collection_spots_collection ON collection_spots (collection_id);
```

### RLS Policies

The FastAPI service connects with the **service role key**, which bypasses RLS entirely. RLS policies apply only when PostgREST (or Supabase client SDKs using anon/user JWTs) accesses these tables directly — for example, from future iOS direct-to-Supabase calls or the Supabase dashboard. They do not restrict the FastAPI service itself.

The public `GET /collections/{id}` endpoint is served by FastAPI (service role) and does not depend on the anon RLS policies below. However, to keep the tables safe for any future anon access, the anon GRANTs and RLS policies are included.

```sql
-- collections
ALTER TABLE collections ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users manage own collections"
    ON collections FOR ALL
    USING (auth.uid() = user_id);

CREATE POLICY "Anyone can read shareable collections"
    ON collections FOR SELECT
    USING (is_shareable = TRUE);

-- Grant anon SELECT so unauthenticated Supabase client requests can read shareable collections
GRANT SELECT ON collections TO anon;

-- collection_spots
ALTER TABLE collection_spots ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users manage spots in own collections"
    ON collection_spots FOR ALL
    USING (
        collection_id IN (
            SELECT id FROM collections WHERE user_id = auth.uid()
        )
    );

CREATE POLICY "Anyone can read spots in shareable collections"
    ON collection_spots FOR SELECT
    USING (
        collection_id IN (
            SELECT id FROM collections WHERE is_shareable = TRUE
        )
    );

-- Grant anon SELECT so unauthenticated Supabase client requests can read spots in shareable collections
GRANT SELECT ON collection_spots TO anon;

-- saved_spots: no GRANT to anon is intentional — saved_spots has no public-access use case.
-- saved_spots (add missing policies if not yet present)
ALTER TABLE saved_spots ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users read own saves"
    ON saved_spots FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users insert own saves"
    ON saved_spots FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users delete own saves"
    ON saved_spots FOR DELETE USING (auth.uid() = user_id);

-- No UPDATE policy on saved_spots — the table has no mutable fields (only id, user_id, spot_id,
-- created_at). This is intentional. If a mutable field is added later, an UPDATE policy will be needed.
```

---

## API Endpoints

### Saved Spots

| Method | Path | Auth | Status | Response |
|--------|------|------|--------|----------|
| `GET` | `/me/saved-spots` | Required | 200 | `SavedSpotsResponse` |
| `POST` | `/me/saved-spots` | Required | 200 | `SavedSpotResponse` |
| `DELETE` | `/me/saved-spots/{spot_id}` | Required | 204 | _(no body)_ |

`GET /me/saved-spots` accepts an optional `collection_id` query param to filter by collection.

`POST /me/saved-spots` saves a spot and optionally adds it to collections in the same call. Returns **200** (not 201) because the upsert is idempotent — a second call for the same `spot_id` does not create a new row.

`DELETE /me/saved-spots/{spot_id}` unsaves a spot and removes it from all of the user's collections.

### Collections

| Method | Path | Auth | Status | Response |
|--------|------|------|--------|----------|
| `GET` | `/me/collections` | Required | 200 | `CollectionListResponse` |
| `POST` | `/me/collections` | Required | 201 | `CollectionResponse` |
| `PATCH` | `/me/collections/{id}` | Required | 200 | `CollectionResponse` |
| `DELETE` | `/me/collections/{id}` | Required | 204 | _(no body)_ |
| `POST` | `/me/collections/{id}/spots` | Required | 200 | `SavedSpotResponse` |
| `DELETE` | `/me/collections/{id}/spots/{spot_id}` | Required | 204 | _(no body)_ |

`POST /me/collections` creates a collection. Optional `source_collection_id` copies spots from a shareable collection.

`PATCH /me/collections/{id}` renames or toggles `is_shareable`. Raises 422 if the request body is empty (no fields set). See edge cases.

### Public Sharing

| Method | Path | Auth | Status | Response |
|--------|------|------|--------|----------|
| `GET` | `/collections/{id}` | None | 200 | `PublicCollectionResponse` |

Returns 404 if the collection does not exist or `is_shareable = false`. Returns at most 200 spots ordered by `added_at ASC`. `spot_count` in the response is the number of spots returned (≤ 200), not the true total.

---

## Pydantic Schemas (`app/saved/schemas.py`)

```python
# Requests
class SaveSpotRequest(BaseModel):
    spot_id: uuid.UUID
    collection_ids: list[uuid.UUID] = []  # empty = save standalone only

class CreateCollectionRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    source_collection_id: Optional[uuid.UUID] = None  # copy from shareable collection

class UpdateCollectionRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    is_shareable: Optional[bool] = None

class AddSpotToCollectionRequest(BaseModel):
    spot_id: uuid.UUID

# Responses
class CollectionResponse(BaseModel):
    id: uuid.UUID
    name: str
    is_shareable: bool
    spot_count: int
    created_at: datetime
    updated_at: datetime

class CollectionListResponse(BaseModel):
    collections: list[CollectionResponse]

class SavedSpotResponse(BaseModel):
    spot: SpotPin              # reuses existing public SpotPin schema from app/spots/schemas.py
    saved_at: datetime         # maps to saved_spots.created_at
    collection_ids: list[uuid.UUID]  # ALL of this user's collections the spot belongs to
                                     # (always the full set, regardless of any collection_id filter)

class SavedSpotsResponse(BaseModel):
    spots: list[SavedSpotResponse]

class PublicCollectionResponse(BaseModel):
    id: uuid.UUID
    name: str
    spot_count: int            # = len(spots). Capped at 200. Does not reflect the true total
                               # if the collection has more than 200 spots. Intentional.
    spots: list[SpotPin]       # capped at 200 entries, ordered by added_at ASC
```

---

## Service Layer (`app/saved/service.py`)

All functions are **sync** (supabase-py is sync) — same pattern as existing service files.

**Import note:** `_build_spot_pin` lives in `app/spots/service.py`. Import it at the top of `app/saved/service.py`. It expects a full `spots` row dict (all columns). All spot fetch queries in this file use `.select("*")` to satisfy this requirement. The `spots` table has a `noise_matrix` JSONB column (added by the noise matrix feature — see noise matrix design spec). `_build_spot_pin` reads `row.get("noise_matrix")` and handles `None` gracefully.

### `save_spot(user_id, spot_id, collection_ids[])` → `SavedSpotResponse`
1. Verify spot exists and is active: fetch `spots` where `id = spot_id`. Raise 404 if not found or `is_active = false`.
2. Validate all `collection_ids` in one batched query before any write: fetch `collections` rows with `.select("id").in_("id", collection_ids).eq("user_id", user_id)`. If the number of returned rows does not match `len(collection_ids)`, raise 403 (at least one ID is missing or belongs to another user). Skip this step if `collection_ids` is empty.
3. Upsert into `saved_spots` using `on_conflict="user_id,spot_id"` **without** `ignore_duplicates=True`. The upsert payload includes only `user_id` and `spot_id` — do NOT include `created_at` in the insert dict, so the existing `created_at` is preserved on conflict. supabase-py v2 returns the upserted row in `result.data[0]` regardless of whether it was an insert or update (no `ignore_duplicates`). `saved_at` = `result.data[0]["created_at"]`, which is the original save timestamp in both the new and idempotent cases.
4. If `collection_ids` is non-empty: bulk-upsert into `collection_spots` in a single call — build a list of `{"collection_id": str(cid), "spot_id": str(spot_id)}` dicts and call `.upsert(rows, on_conflict="collection_id,spot_id", ignore_duplicates=True)` once. Do NOT loop over collection IDs.
5. Fetch all user collection IDs for the `collection_ids` field in the response (always fetch ALL user collections, regardless of whether `collection_ids` was empty or not): `.select("id").eq("user_id", user_id)` from `collections` → `user_collection_ids`. If the user has no collections, set `user_collection_ids = []` and skip the next sub-step.
6. If `user_collection_ids` is non-empty: fetch `collection_spots` for this `spot_id` across all user's collections: `.select("collection_id").in_("collection_id", user_collection_ids).eq("spot_id", spot_id)` — extract list of `collection_id` values for the response.
7. Call `_build_spot_pin(spot_row)` using the spot row fetched in step 1. Return `SavedSpotResponse`.

### `unsave_spot(user_id, spot_id)` → `None` (204)
1. **First:** verify the spot is saved — fetch `saved_spots` where `user_id` and `spot_id` match. Raise 404 if not found.
2. Fetch all of user's collection IDs: `.select("id").eq("user_id", user_id)` from `collections` → `collection_ids`
3. If `len(collection_ids) > 0`: delete from `collection_spots` where `collection_id IN (collection_ids)` and `spot_id` matches, using `.in_("collection_id", collection_ids).eq("spot_id", spot_id)`. Skip if `collection_ids` is empty.
4. Delete from `saved_spots` where `user_id` and `spot_id` match

### `list_saved_spots(user_id, collection_id?)` → `SavedSpotsResponse`

**Filtered path** (`collection_id` provided):
1. Verify collection ownership — fetch `collections` row with `.eq("id", collection_id)`. Raise 404 if not found at all. Raise 403 if found but `user_id` does not match.
2. Fetch all user's collection IDs: `.select("id").eq("user_id", user_id)` from `collections` → `user_collection_ids`
3. Fetch `collection_spots` rows for this `collection_id` ordered by `added_at ASC`: `.select("spot_id").eq("collection_id", collection_id).order("added_at")` → preserve the ordered list of `spot_id`s. If result is empty (collection has no spots), return `SavedSpotsResponse(spots=[])` immediately. **This early return also guards steps 4 and 5, which both call `.in_("...", spot_ids)` — those calls are safe because `spot_id`s is guaranteed non-empty past this point.**
4. Fetch full spot data in a single batched query: `.select("*").in_("id", spot_ids)` from `spots`. Re-sort to match `added_at ASC` ordering from step 3: build a dict `{row["id"]: row for row in result.data}` then reconstruct using the ordered `spot_id`s.
5. Fetch `saved_spots` rows for these `spot_id`s (for `saved_at`): `.select("spot_id,created_at").eq("user_id", user_id).in_("spot_id", spot_ids)` — build a dict `{spot_id: created_at}`
6. If `user_collection_ids` is non-empty: fetch all `collection_spots` rows for all user's collections: `.select("collection_id,spot_id").in_("collection_id", user_collection_ids)`. This intentionally fetches collection membership for ALL of the user's spots across ALL their collections — not just the spots in this filtered view. The result set is bounded: max 50 collections × spots in those collections. Group by `spot_id` into a dict `{spot_id: [collection_id, ...]}`. `collection_ids` in `SavedSpotResponse` is always the full set, regardless of the filter. When building the response, look up each spot's entry in this dict (defaulting to `[]` if absent). If `user_collection_ids` is empty, use `{}` for all spots.
7. Build and return `SavedSpotsResponse` preserving `added_at ASC` ordering from step 3

**Unfiltered path** (no `collection_id`):
1. Fetch all `saved_spots` rows for user ordered by `created_at DESC`: `.select("spot_id,created_at").eq("user_id", user_id).order("created_at", desc=True)` → get ordered `spot_id`s and build `{spot_id: created_at}` dict. If result is empty, return `SavedSpotsResponse(spots=[])` immediately.
2. Fetch all user's collection IDs: `.select("id").eq("user_id", user_id)` from `collections` → `user_collection_ids`
3. Fetch full spot data in a single batched query: `.select("*").in_("id", spot_ids)` from `spots`. Build a dict `{row["id"]: row for row in result.data}` then reconstruct list using the ordered `spot_id`s from step 1 (preserves `saved_at DESC` ordering).
4. If `user_collection_ids` is non-empty: fetch all `collection_spots` rows for this user: `.select("collection_id,spot_id").in_("collection_id", user_collection_ids)` — group by `spot_id` into a dict `{spot_id: [collection_id, ...]}`. If empty, use `{}` for all spots.
5. Build and return `SavedSpotsResponse` preserving ordering from step 1

**N+1 rule:** Never fetch spot data or collection membership row by row. Always collect all required IDs first, then issue a single `.in_()` query per table.

### `list_collections(user_id)` → `CollectionListResponse`
1. Fetch all `collections` rows where `user_id` matches, ordered by `created_at ASC`. Extract `collection_ids = [row["id"] for row in result.data]`. If result is empty, return `CollectionListResponse(collections=[])` immediately. (This early return also ensures `collection_ids` is non-empty before step 2's `.in_()` call.)
2. Fetch all `collection_spots` rows for these collections in one query: `.select("collection_id").in_("collection_id", collection_ids)` — supabase-py has no GROUP BY, so group in Python using `collections.Counter` or a dict comprehension to get per-collection counts. This is acceptable because a user has at most 50 collections. The result set is bounded and no cap is needed.
3. Merge counts into `CollectionResponse` objects (count = 0 for collections with no spots) and return `CollectionListResponse`

### `create_collection(user_id, name, source_collection_id?)` → `CollectionResponse`
1. Check user's current collection count — fetch count from `collections` where `user_id` matches. Raise 422 with message "Collection limit reached (50)" if already at 50.
2. Insert into `collections` → get new collection row
3. If `source_collection_id` provided:
   - Fetch that collection; raise 404 if not found or `is_shareable = false`
   - Raise 400 with message "Cannot copy your own collection" if the collection's `user_id` matches `user_id`
   - Fetch all `collection_spots` for the source collection → get `spot_id`s. If `spot_id`s is empty (source collection has no spots), skip the next two sub-steps.
   - Bulk-insert into `collection_spots` (new `collection_id`, each `spot_id`) using `on_conflict="collection_id,spot_id"` with `ignore_duplicates=True`
   - Bulk-upsert each into `saved_spots` using `on_conflict="user_id,spot_id"` with `ignore_duplicates=True`
   - **Partial-failure note:** these three writes (create collection, insert collection_spots, upsert saved_spots) are not wrapped in a DB transaction. If a later write fails, log the error and raise 500; the partially-created collection is left in place for the user to delete or retry.
4. `spot_count`: if `source_collection_id` was provided, `spot_count = len(spot_ids)` where `spot_ids` comes from the fetch in step 3c. If no `source_collection_id` was provided, `spot_count = 0` (set directly; `spot_ids` is never defined in this path).

### `update_collection(user_id, collection_id, payload: UpdateCollectionRequest)` → `CollectionResponse`
1. Fetch collection — raise 404 if not found, 403 if `user_id` does not match
2. Build updates dict from `payload.model_dump(exclude_unset=True)` — raise 422 with message "No fields provided to update" if empty
3. Add `updated_at = datetime.now(timezone.utc).isoformat()` to updates
4. Update `collections` row, return updated row
5. Fetch current `spot_count` for this collection: `.select("id").eq("collection_id", collection_id)` from `collection_spots`, then use `len(result.data)` — any column works since only the count is needed. **Note:** this is a separate read after write with no transaction, so `spot_count` reflects DB state at the time of the read. Under normal usage this is accurate. This is intentional — the service uses no transactions.
6. Return `CollectionResponse`

### `delete_collection(user_id, collection_id)` → `None` (204)
1. Fetch collection — raise 404 if not found, 403 if `user_id` does not match
2. Delete from `collections` — `ON DELETE CASCADE` handles `collection_spots` cleanup automatically
3. `saved_spots` rows are NOT touched

### `add_spot_to_collection(user_id, collection_id, spot_id)` → `SavedSpotResponse`
1. Verify collection belongs to user — fetch `collections` row. Raise 404 if not found, 403 if `user_id` does not match.
2. Verify spot exists and is active — fetch `spots` row. Raise 404 if not found or `is_active = false`.
3. Upsert into `collection_spots` using `on_conflict="collection_id,spot_id"` with `ignore_duplicates=True`
4. Upsert into `saved_spots` using `on_conflict="user_id,spot_id"` with `ignore_duplicates=True` (implicit save; does not change `created_at` if spot was already saved). Note: `ignore_duplicates=True` means `result.data` will be empty if the spot was already saved — do not read `saved_at` from this result.
5. Fetch `saved_spots` row for this user/spot to get `saved_at` (= `saved_spots.created_at`): `.select("created_at").eq("user_id", user_id).eq("spot_id", spot_id)`
6. Fetch all user's collection IDs from `collections` (separate query, not just the one collection from step 1 — the user may belong to multiple collections): `.select("id").eq("user_id", user_id)` → `user_collection_ids`. Since the user owns at least the collection verified in step 1, `user_collection_ids` is guaranteed non-empty. Fetch all `collection_spots` for this `spot_id` across those collections: `.select("collection_id").in_("collection_id", user_collection_ids).eq("spot_id", spot_id)` — extract list of `collection_id` values for the response.
7. Call `_build_spot_pin(spot_row)` using the spot row fetched in step 2. Return `SavedSpotResponse`.

### `remove_spot_from_collection(user_id, collection_id, spot_id)` → `None` (204)
1. Verify collection belongs to user — fetch `collections` row. Raise 404 if not found, 403 if `user_id` does not match.
2. Delete from `collection_spots` where `collection_id` and `spot_id` match. If the spot is not in the collection, the delete is a no-op — return 204 (idempotent).
3. Does NOT touch `saved_spots`

### `get_public_collection(collection_id)` → `PublicCollectionResponse`
1. Fetch collection — 404 if not found or `is_shareable = false`
2. Fetch `collection_spots` limited to 200 rows ordered by `added_at ASC`: `.select("spot_id").eq("collection_id", collection_id).order("added_at").limit(200)` — preserve the ordered list of `spot_id`s. If result is empty (collection has no spots), return `PublicCollectionResponse(id=..., name=..., spot_count=0, spots=[])` immediately.
3. Fetch full spot data in a single batched query: `.select("*").in_("id", spot_ids)` from `spots`. Re-sort to match the `added_at ASC` order from step 2: build a dict `{row["id"]: row for row in result.data}` then reconstruct the list using the ordered `spot_id`s from step 2.
4. Build `SpotPin` objects via `_build_spot_pin` (imported from `app/spots/service.py`) and return `PublicCollectionResponse` with `spot_count = len(spots)`

---

## Module Structure

```
app/saved/
├── __init__.py
├── router.py      # all 10 endpoints
├── service.py     # sync DB calls
└── schemas.py     # Pydantic v2 request/response models
```

Register in `app/main.py` with no prefix (endpoints already carry their full paths `/me/...` and `/collections/...`):
```python
from app.saved.router import router as saved_router
app.include_router(saved_router)
```

The router is created with `APIRouter(tags=["saved"])` — no prefix — so all path strings in `router.py` are written in full (e.g. `@router.get("/me/saved-spots")`). The `tags=["saved"]` groups all 10 endpoints under "saved" in the OpenAPI docs, consistent with the existing `admin` router.

**Important:** Do NOT set `dependencies=[Depends(get_current_user)]` at the `APIRouter` level. Auth dependencies must be applied per-route, because `GET /collections/{id}` (the public sharing endpoint) must NOT require auth. Apply `Depends(get_current_user)` individually to each `/me/...` route handler. The public route has no auth dependency.

---

## Edge Cases

| Scenario | Behaviour |
|----------|-----------|
| Save a spot already saved | Idempotent — 200, existing `saved_at` preserved |
| `POST /me/saved-spots` with any `collection_id` not owned by user | 403 — validated in bulk before any write |
| Add spot to collection not owned by user | 403 |
| Add spot to a collection, spot already in it | Idempotent — 200, no duplicate |
| Delete collection | Spots remain in `saved_spots`; `collection_spots` cascade-deleted |
| Unsave a spot in multiple collections | 404 check first; then removes from all collections, then unsaves |
| Copy a non-shareable collection | 404 |
| Copy own collection | 400 |
| User already has 50 collections | 422 on create |
| `create_collection` copy fails mid-way | 500; partially-created collection left in place |
| `PATCH` with empty body (no fields set) | 422 — "No fields provided to update" |
| `GET /collections/{id}` on non-shareable | 404 |
| Spot deactivated/deleted while in collection | `ON DELETE CASCADE` on `collection_spots` and `saved_spots` handles it |
| `GET /collections/{id}` with >200 spots | Returns first 200 ordered by `added_at ASC` |
| `DELETE /me/collections/{id}/spots/{spot_id}` when spot not in collection | Idempotent — 204 |
| `DELETE /me/saved-spots/{spot_id}` when spot is not saved | 404 |
| `GET /me/saved-spots?collection_id=X` where X doesn't exist | 404 |
| `GET /me/saved-spots?collection_id=X` where X exists but belongs to another user | 403 |

---

## UX Recommendations for Designer

### Saving a spot

The save action lives in two places: the map pin callout and the spot detail screen. Use a single bookmark icon for both. Two states:

- **No collections yet:** tapping saves immediately (haptic feedback + icon fills). No sheet needed — keep it frictionless.
- **Collections exist:** tapping opens a bottom sheet with a checklist of the user's collections and a "+ New Collection" row at the bottom. The spot saves to `saved_spots` the moment the sheet opens (optimistic). Collection checkboxes toggle membership instantly — no confirm button. User dismisses the sheet by swiping down or tapping outside.

The bookmark icon on the map pin should reflect saved state at a glance. Consider a subtle fill/colour change distinct from the category colour.

### The Saved Spots tab

Dedicated tab (bookmark icon in the tab bar). Default view: flat list of all saved spots, most recently saved first, card layout matching the main spots list.

**Empty state:** When the user has no saved spots yet, show a centred illustration with the text "No saved spots yet" and a subline "Tap the bookmark icon on any spot to save it here." No CTA button — discovery should happen naturally on the map.

A horizontal scrollable filter row sits just below the navigation bar:
- "All" pill (selected by default)
- One pill per collection, showing name + spot count
- "+ New" pill at the far right to create a collection

Selecting a pill filters the list in place — no navigation push. This keeps the interaction lightweight and avoids deep nesting.

### Creating a collection

Accessible from two entry points:
1. The "+ New" pill in the filter row
2. The "+ New Collection" row at the bottom of the save bottom sheet

Both trigger a simple modal with a single text field ("Collection name") and a "Create" button. After creation, the new collection is immediately selected/checked. Keep it to one field — no description, no cover image at this stage.

### Collection detail view

Tapping a collection pill in the filter row shows the filtered list inline. For a dedicated collection view (needed for the share flow), push a new screen showing:
- Collection name (tappable to rename inline)
- Share icon in the nav bar top right
- Same card list as the main saved view
- Swipe-to-remove on individual spots (removes from collection, does not unsave)

### Sharing a collection

Share icon in the collection detail nav bar. Tapping shows a single confirmation step: "Share this collection? Anyone with the link can view and save it." with a toggle. Once enabled, the standard iOS share sheet appears with the link. The share icon changes to indicate the collection is public.

### Receiving a shared collection (Universal Link)

When a non-user or logged-out user opens the link: show a preview screen (no auth required) with the collection name, spot count, and a scrollable list of spot cards. CTA: "Open in app" or "Download Spotsvc".

When an authenticated user opens the link: show a modal over the current screen with:
- Collection name + spot count
- Scrollable spot card preview (compact)
- Two actions: **"Save all spots"** (primary, adds all spots to their saved list) and **"Save as collection"** (secondary, creates a copy with the name pre-filled but editable)
- Dismiss button top right

Keep the modal lightweight — this is a transient action, not a new screen.
