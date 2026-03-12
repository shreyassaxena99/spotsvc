# spotsvc

Backend API for a curated London work-spots app. iOS users see cafes, gyms, hotel lobbies, and coworking spaces on a map, view details, and save favourites. An admin panel lets the team add and manage spots.

Built with **FastAPI** (async), **Supabase** (Postgres + PostGIS + Auth), **Redis** (Google Places cache), and deployed on **Railway**.

---

## Architecture

```
iOS App (Swift)          Admin Panel (React)
     │                          │
     │ Supabase JWT             │ Supabase JWT
     ▼                          ▼
┌─────────────────────────────────────┐
│            spotsvc (FastAPI)         │
│                                     │
│  /admin/*   →  admin router         │
│  /spots/*   →  spots router (TODO)  │
│  /me/*      →  users router (TODO)  │
└────────────┬──────────────┬─────────┘
             │              │
    ┌─────────┴──┐   ┌──────┴────────┐   ┌────────────────┐
    │  Supabase   │   │  Redis        │   │ Google Places  │
    │  Postgres   │   │  (Upstash)    │   │ API (New)      │
    │  + PostGIS  │   │  1-hr TTL     │   │                │
    └─────────────┘   └───────────────┘   └────────────────┘
```

**Key principles:**
- Google Places is the source of truth for place metadata (name, address, hours, photos, busyness). We cache it in Redis; we do not duplicate it in our DB.
- Our DB stores only what Google can't provide: coordinates (for PostGIS geo queries), category, access type, amenities, and editorial copy.
- Auth is fully handled between the client and Supabase — this server only validates the JWT Supabase issues.

---

## Current capabilities

### Admin — add and list spots (`/admin/*`)

The only implemented surface right now. Requires a valid Supabase JWT with `app_metadata.role = "admin"`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/admin/google-autocomplete?q=` | Proxy to Google Places Autocomplete, London-biased |
| `GET` | `/admin/google-place/{place_id}` | Fetch full place details for preview before saving |
| `GET` | `/admin/spots` | List all spots — paginated, searchable by name |
| `POST` | `/admin/spots` | Create a spot (fetches name + coords from Google, stores in DB) |

**Add-spot flow:**
1. Admin types a name → `GET /admin/google-autocomplete?q=Workshop+Coffee` returns suggestions with `place_id`s.
2. Admin selects one → `GET /admin/google-place/{place_id}` returns a preview (name, address, lat/lng, hours, photos).
3. Admin fills in the manual fields and submits → `POST /admin/spots`.
4. Service verifies the `place_id` isn't already in the DB, fetches coordinates from Google, and persists the spot.

**`POST /admin/spots` request body:**
```json
{
  "google_place_id": "ChIJ...",
  "category": "cafe",
  "access_type": "purchase_required",
  "wifi_available": true,
  "power_outlets": true,
  "noise_level": "moderate",
  "description": "Bright, spacious cafe on Clerkenwell Road with reliable Wi-Fi.",
  "admin_notes": "Check upstairs for more seating."
}
```

`category` options: `cafe` `gym` `hotel_lobby` `coworking` `library` `restaurant` `other`

`access_type` options: `free` `purchase_required` `members_only`

### Health check

`GET /health` — returns `{"status": "ok"}`. Used by Railway for deployment health checks.

---

## What's not built yet

- `GET /spots` — map view, nearby spots via PostGIS `ST_DWithin`, no Google calls
- `GET /spots/:id` — detail view merging DB fields with Redis-cached Google data
- `PUT /admin/spots/:id` — update curated fields
- `DELETE /admin/spots/:id` — soft-delete (`is_active = false`)
- `GET /me` / `PATCH /me` / `DELETE /me` — user profile endpoints
- `GET /me/saved-spots` / `POST /me/saved-spots/:id` / `DELETE /me/saved-spots/:id` — save/unsave
- Redis caching layer (client exists, not wired into any route yet)
- Rate limiting

---

## Tech stack

| | |
|---|---|
| Framework | FastAPI + uvicorn |
| Database | Supabase Postgres + PostGIS (async via asyncpg + SQLAlchemy) |
| Auth | Supabase Auth — Apple + Google sign-in. JWT validated here with HS256. |
| Cache | Redis (Upstash) — Google Places responses, 1-hr TTL |
| HTTP client | httpx (async) — Google Places API calls |
| Deployment | Railway (Dockerfile) |

---

## Project structure

```
spotsvc/
├── app/
│   ├── main.py              # App factory, CORS, lifespan
│   ├── config.py            # Pydantic Settings (reads from env)
│   ├── dependencies.py      # get_db, get_current_user, get_admin_user
│   │
│   ├── admin/
│   │   ├── router.py        # /admin/* endpoints
│   │   ├── service.py       # Business logic (Google fetch + DB write)
│   │   └── schemas.py       # Pydantic request/response models
│   │
│   ├── google_places/
│   │   ├── client.py        # Async httpx wrapper for Places New API
│   │   └── schemas.py       # PlaceSuggestion, PlaceDetails models
│   │
│   ├── db/
│   │   ├── database.py      # Async engine (PgBouncer-compatible)
│   │   ├── models.py        # SQLAlchemy ORM — Spot model
│   │   └── schema.sql       # Run once in Supabase SQL editor
│   │
│   └── core/
│       ├── security.py      # JWT decode + admin role check
│       └── redis.py         # Async Redis client
│
├── Dockerfile
├── railway.toml
├── requirements.txt
└── .env.example
```

---

## Local setup

**Prerequisites:** Python 3.12, a Supabase project with PostGIS enabled, a Google Places API key (New), and a Redis instance (Upstash works).

```bash
git clone <repo>
cd spotsvc

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Fill in SUPABASE_*, DATABASE_URL, GOOGLE_PLACES_API_KEY, REDIS_URL

uvicorn app.main:app --reload
# Docs at http://localhost:8000/docs
```

**Database setup:** Run `app/db/schema.sql` in the Supabase SQL editor. It creates the `spots` table, PostGIS indexes, RLS policies, and the `updated_at` trigger.

**Setting an admin user:**
```sql
-- Run in Supabase SQL editor, replace with actual user UUID
UPDATE auth.users
SET raw_app_meta_data = raw_app_meta_data || '{"role": "admin"}'::jsonb
WHERE id = 'user-uuid-here';
```

---

## Deployment (Railway)

1. Create a new Railway project and connect the repo.
2. Set all env vars from `.env.example` in the Railway dashboard.
3. Railway detects `railway.toml` and builds the Dockerfile automatically.
4. The service starts on `$PORT` (set by Railway) with a health check on `/health`.

---

## Notable implementation details

- **PgBouncer compatibility** — `statement_cache_size=0` is set in asyncpg connect args. Supabase uses PgBouncer in transaction mode which doesn't support prepared statements.
- **Geography vs Geometry** — `location` is stored as `GEOGRAPHY(POINT, 4326)` so PostGIS distance calculations (`ST_DWithin`, `ST_Distance`) use metres by default, not degrees.
- **Google Places coordinate ownership** — lat/lng come from Google at insert time and are stored in our DB. This is the one exception to "don't duplicate Google data" — we need it for PostGIS queries that can't call Google on every request.
- **Docs in non-production only** — `/docs` and `/redoc` are disabled when `APP_ENV=production`.
