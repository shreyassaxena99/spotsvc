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

```sql
-- collections
ALTER TABLE collections ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users manage own collections"
    ON collections FOR ALL
    USING (auth.uid() = user_id);

CREATE POLICY "Anyone can read shareable collections"
    ON collections FOR SELECT
    USING (is_shareable = TRUE);

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

-- saved_spots (add missing policies if not yet present)
ALTER TABLE saved_spots ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users read own saves"
    ON saved_spots FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users insert own saves"
    ON saved_spots FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users delete own saves"
    ON saved_spots FOR DELETE USING (auth.uid() = user_id);
```

---

## API Endpoints

### Saved Spots

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/me/saved-spots` | Required | List all saved spots. Optional `collection_id` query param to filter by collection. |
| `POST` | `/me/saved-spots` | Required | Save a spot; optionally add to collections in the same call. |
| `DELETE` | `/me/saved-spots/{spot_id}` | Required | Unsave a spot (removes from all of user's collections too). |

### Collections

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/me/collections` | Required | List user's collections with spot count. |
| `POST` | `/me/collections` | Required | Create a collection. Optional `source_collection_id` copies a shareable collection. |
| `PATCH` | `/me/collections/{id}` | Required | Rename or toggle `is_shareable`. |
| `DELETE` | `/me/collections/{id}` | Required | Delete a collection (spots remain saved). |
| `POST` | `/me/collections/{id}/spots` | Required | Add a spot to a collection (also saves it). |
| `DELETE` | `/me/collections/{id}/spots/{spot_id}` | Required | Remove a spot from a collection (does not unsave). |

### Public Sharing

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/collections/{id}` | None | View a shareable collection + its spots. 404 if not shareable. |

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
    spot: SpotPin              # reuses existing public SpotPin schema
    saved_at: datetime
    collection_ids: list[uuid.UUID]  # which of this user's collections the spot belongs to

class SavedSpotsResponse(BaseModel):
    spots: list[SavedSpotResponse]

class PublicCollectionResponse(BaseModel):
    id: uuid.UUID
    name: str
    spots: list[SpotPin]
```

---

## Service Layer (`app/saved/service.py`)

All functions are **sync** (supabase-py is sync) — same pattern as existing service files.

### `save_spot(user_id, spot_id, collection_ids[])`
1. Upsert into `saved_spots` using `on_conflict="user_id,spot_id"` — idempotent if already saved
2. For each `collection_id`: verify it belongs to `user_id` (raise 403 if not), then upsert into `collection_spots`

### `unsave_spot(user_id, spot_id)`
1. Fetch all of user's `collections` IDs
2. Delete from `collection_spots` where `collection_id` in user's collections and `spot_id` matches
3. Delete from `saved_spots` where `user_id` and `spot_id` match
4. 404 if spot was not saved

### `list_saved_spots(user_id, collection_id?)`
1. If `collection_id` provided: verify it belongs to user, fetch `collection_spots` filtered by it, then fetch full spot data for each
2. Otherwise: fetch all `saved_spots` for user, then fetch full spot data + which collections each spot belongs to

### `create_collection(user_id, name, source_collection_id?)`
1. Insert into `collections`
2. If `source_collection_id`: fetch that collection, verify `is_shareable = true` (raise 404 if not), bulk-insert its `collection_spots` into the new collection, upsert each into `saved_spots`

### `add_spot_to_collection(user_id, collection_id, spot_id)`
1. Verify collection belongs to user (403 if not)
2. Verify spot exists and is active (404 if not)
3. Upsert into `collection_spots`
4. Upsert into `saved_spots` (implicit save)

### `remove_spot_from_collection(user_id, collection_id, spot_id)`
1. Verify collection belongs to user (403 if not)
2. Delete from `collection_spots`
3. Does NOT touch `saved_spots`

### `get_public_collection(collection_id)`
1. Fetch collection — 404 if not found or `is_shareable = false`
2. Fetch `collection_spots`, then fetch full spot data for each (reuses `_build_spot_pin`)

---

## Module Structure

```
app/saved/
├── __init__.py
├── router.py      # all 10 endpoints
├── service.py     # sync DB calls
└── schemas.py     # Pydantic v2 request/response models
```

Register in `app/main.py`:
```python
from app.saved.router import router as saved_router
app.include_router(saved_router)
```

---

## Edge Cases

| Scenario | Behaviour |
|----------|-----------|
| Save a spot already saved | Idempotent — 200, no duplicate |
| Add spot to collection not owned by user | 403 |
| Add spot to a collection, spot already in it | Idempotent — 200, no duplicate |
| Delete collection | Spots remain in `saved_spots`; `collection_spots` cascade-deleted |
| Unsave a spot in multiple collections | Removes from all collections, then unsaves |
| Copy a non-shareable collection | 404 |
| GET /collections/{id} on non-shareable | 404 |
| Spot deactivated/deleted while in collection | `ON DELETE CASCADE` on `collection_spots` and `saved_spots` handles it |

---

## UX Recommendations for Designer

### Saving a spot

The save action lives in two places: the map pin callout and the spot detail screen. Use a single bookmark icon for both. Two states:

- **No collections yet:** tapping saves immediately (haptic feedback + icon fills). No sheet needed — keep it frictionless.
- **Collections exist:** tapping opens a bottom sheet with a checklist of the user's collections and a "+ New Collection" row at the bottom. The spot saves to `saved_spots` the moment the sheet opens (optimistic). Collection checkboxes toggle membership instantly — no confirm button. User dismisses the sheet by swiping down or tapping outside.

The bookmark icon on the map pin should reflect saved state at a glance. Consider a subtle fill/colour change distinct from the category colour.

### The Saved Spots tab

Dedicated tab (bookmark icon in the tab bar). Default view: flat list of all saved spots, most recently saved first, card layout matching the main spots list.

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
