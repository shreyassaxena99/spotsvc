# CLAUDE.md — London Work Spots Backend

## Project Overview
Backend API for an iOS app that shows curated work-friendly spots (cafes, gyms, hotel lobbies, coworking spaces) in London. Users see spots on a map, view details, and save favorites.

## Tech Stack
- **Framework:** Python 3.12 + FastAPI (async throughout)
- **Database:** Supabase Postgres + PostGIS — accessed via **Supabase Python client** (REST/HTTPS), not direct TCP
- **DB Client:** `supabase-py` v2 — uses `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`. No SQLAlchemy, no asyncpg.
- **Auth:** Supabase Auth (Apple + Google sign-in) — no auth endpoints in this server. iOS app authenticates directly with Supabase. This server only validates Supabase JWTs.
- **External API:** Google Places API (New) via `requests`
- **Validation:** Pydantic v2
- **No migrations tooling.** Tables are created directly in Supabase SQL Editor. No Alembic.

## Project Structure
```
app/
├── main.py                     # FastAPI app, CORS, lifespan, /health endpoint
├── config.py                   # pydantic-settings: SUPABASE_URL, SUPABASE_JWT_SECRET,
│                               #   SUPABASE_SERVICE_ROLE_KEY, GOOGLE_PLACES_API_KEY
├── dependencies.py             # get_current_user, get_admin_user, no_auth (temp bypass)
│
├── admin/
│   ├── router.py               # Spot CRUD, Google autocomplete proxy, Google place preview
│   ├── service.py              # Supabase client DB calls + Google data fetch logic (sync)
│   └── schemas.py
│
├── google_places/
│   ├── client.py               # GooglePlacesClient class using requests (sync)
│   └── schemas.py              # Pydantic models for Google responses
│
├── db/
│   ├── database.py             # Supabase client singleton (create_client)
│   └── models.py               # SpotCategory + AccessType enums (plain Python enums)
│
└── core/
    └── security.py             # decode_supabase_jwt(), require_admin_role()
```

**Not yet implemented:** `spots/`, `saved/`, `users/` modules (future iOS endpoints).

## Authentication Rules
- **No auth endpoints in this server.** Auth is iOS ↔ Supabase directly.
- All protected endpoints receive a Supabase JWT via `Authorization: Bearer <token>`.
- Validate with `python-jose`: decode with `SUPABASE_JWT_SECRET`, algorithm `HS256`, audience `authenticated`.
- Extract `user_id` from `payload["sub"]`.
- Admin check: `payload["app_metadata"]["role"] == "admin"`.
- **Currently:** Admin auth is bypassed via `no_auth` dependency (returns `{}`). Re-enable by swapping `no_auth` back to `get_admin_user` in `admin/router.py`.

## Database

Tables are created manually via Supabase SQL Editor. All DB access goes through the Supabase Python client (HTTP/PostgREST), not direct Postgres connections.

The `supabase` singleton in `db/database.py` uses the **service role key** — this bypasses Row Level Security, which is correct for server-side operations.

### spots table — additional columns added post-initial schema

The `location` column (PostGIS geography) is set automatically by a trigger from `latitude`/`longitude` floats. Always insert `latitude` and `longitude`; never set `location` directly.

```sql
-- Run once in Supabase SQL Editor if not already done
ALTER TABLE spots ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION;
ALTER TABLE spots ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION;

CREATE OR REPLACE FUNCTION set_spot_location()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.latitude IS NOT NULL AND NEW.longitude IS NOT NULL THEN
    NEW.location = ST_SetSRID(ST_MakePoint(NEW.longitude, NEW.latitude), 4326)::geography;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER spots_location_trigger
  BEFORE INSERT OR UPDATE ON spots
  FOR EACH ROW EXECUTE FUNCTION set_spot_location();
```

### Full initial schema

```sql
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TYPE spot_category AS ENUM (
    'cafe', 'gym', 'hotel_lobby', 'coworking', 'library', 'restaurant', 'other'
);
CREATE TYPE access_type AS ENUM ('free', 'purchase_required', 'members_only');

-- Profiles (extends auth.users)
CREATE TABLE profiles (
    id              UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    display_name    VARCHAR(100),
    email_opt_in    BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Auto-create profile on signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, display_name)
    VALUES (
        NEW.id,
        COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'name', 'User')
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_new_user();

-- Spots
CREATE TABLE spots (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    google_place_id       VARCHAR(300) NOT NULL UNIQUE,
    name                  VARCHAR(255) NOT NULL,
    formatted_address     VARCHAR(500),
    short_address         VARCHAR(300),
    location              GEOGRAPHY(POINT, 4326) NOT NULL,
    latitude              DOUBLE PRECISION,
    longitude             DOUBLE PRECISION,
    phone_national        VARCHAR(50),
    phone_international   VARCHAR(50),
    google_maps_uri       VARCHAR(500),
    website_uri           VARCHAR(500),
    price_level           VARCHAR(50),
    rating                NUMERIC(2,1),
    user_rating_count     INTEGER DEFAULT 0,
    editorial_summary     TEXT,
    business_status       VARCHAR(50),
    timezone              VARCHAR(100) DEFAULT 'Europe/London',
    regular_hours         JSONB,
    current_hours         JSONB,
    photos                JSONB DEFAULT '[]',
    outdoor_seating       BOOLEAN,
    restroom              BOOLEAN,
    serves_breakfast      BOOLEAN,
    serves_lunch          BOOLEAN,
    serves_dinner         BOOLEAN,
    serves_brunch         BOOLEAN,
    serves_coffee         BOOLEAN,
    allows_dogs           BOOLEAN,
    good_for_groups       BOOLEAN,
    dine_in               BOOLEAN,
    takeout               BOOLEAN,
    delivery              BOOLEAN,
    reservable            BOOLEAN,
    parking_options       JSONB,
    payment_options       JSONB,
    accessibility_options JSONB,
    category              spot_category NOT NULL,
    access_type           access_type NOT NULL,
    wifi_available        BOOLEAN DEFAULT TRUE,
    power_outlets         BOOLEAN DEFAULT TRUE,
    noise_level           VARCHAR(20),
    description           TEXT,
    admin_notes           TEXT,
    is_active             BOOLEAN DEFAULT TRUE,
    created_by            UUID,
    google_data_updated_at TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_spots_location ON spots USING GIST (location);
CREATE INDEX idx_spots_active ON spots (is_active) WHERE is_active = TRUE;
CREATE INDEX idx_spots_name ON spots USING GIN (to_tsvector('english', name));

-- Saved spots
CREATE TABLE saved_spots (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL,
    spot_id    UUID NOT NULL REFERENCES spots(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, spot_id)
);
CREATE INDEX idx_saved_spots_user ON saved_spots (user_id);

-- Row Level Security
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users read own profile"   ON profiles FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Users update own profile" ON profiles FOR UPDATE USING (auth.uid() = id);

ALTER TABLE spots ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Anyone can read active spots"
    ON spots FOR SELECT USING (is_active = TRUE);
CREATE POLICY "Admins manage spots"
    ON spots FOR ALL
    USING ((auth.jwt()->>'app_metadata')::jsonb->>'role' = 'admin');

ALTER TABLE saved_spots ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users read own saves"   ON saved_spots FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users insert own saves" ON saved_spots FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users delete own saves" ON saved_spots FOR DELETE USING (auth.uid() = user_id);
```

## Implemented API Endpoints

### GET /health
Returns `{"status": "ok", "db": "ok"}`. Pings Supabase via `spots` table select.

### GET /admin/google-autocomplete?q=
Proxies to Google Places Autocomplete biased to London (20km radius). Returns `suggestions[]` with `place_id`, `text`, `secondary_text`.

### GET /admin/google-place/{place_id}
Fetches full Google Place details for preview before saving. Returns `PlaceDetails`.

### GET /admin/spots
Paginated list of all spots (active + inactive). Supports `search` param (name ilike). Returns `SpotListResponse`.

### POST /admin/spots
Accepts `google_place_id` + curated fields (`category`, `access_type`, `wifi_available`, `power_outlets`, `noise_level`, `description`, `admin_notes`). Fetches all data from Google, stores in DB. Returns `SpotResponse`.

## Planned API Endpoints (not yet implemented)

- `GET /spots` — PostGIS proximity search (ST_DWithin) with `is_open_now` computation
- `GET /spots/{id}` — full spot detail with `is_saved`
- `GET/POST/DELETE /me/saved-spots`
- `GET/PATCH/DELETE /me`
- `PUT /admin/spots/{id}` — update curated fields
- `DELETE /admin/spots/{id}` — soft delete
- `POST /admin/spots/{id}/refresh` — re-fetch Google data

## Google Places Client

Sync `requests.Session`. Called directly from async endpoints (acceptable for low-traffic admin use).

### Place Details
```
GET https://places.googleapis.com/v1/places/{place_id}
X-Goog-Api-Key: {key}
X-Goog-FieldMask: <full mask — all fields>
```

### Autocomplete
```
POST https://places.googleapis.com/v1/places:autocomplete
X-Goog-Api-Key: {key}
Body: { "input": "...", "locationBias": { circle centred on London, 20km } }
```

## is_open_now Logic (for future spots endpoint)
Compute from `regular_hours` JSON + `timezone` field. Google's `regularOpeningHours.periods` uses Sunday=0 day format. Convert Python's Monday=0 weekday to Google's format. Compare current time in spot's timezone against periods.

## Code Style & Conventions
- Async for all FastAPI endpoint handlers.
- DB service functions (`admin/service.py`) are **sync** — Supabase client is synchronous. Acceptable for admin-only endpoints.
- `requests` (synchronous) for Google Places API calls — same pattern.
- Type hints on all function signatures.
- Pydantic v2 models for all request/response schemas.
- Use `from __future__ import annotations` in all files.
- Use `UUID` type for all IDs.
- Environment variables via pydantic-settings `BaseSettings`.
- Error responses use FastAPI's `HTTPException`.
- Use `logging` module, not print().

## Dependencies (requirements.txt)
```
fastapi==0.115.6
uvicorn[standard]==0.34.0
requests==2.32.3
python-jose[cryptography]==3.3.0
pydantic-settings==2.7.1
supabase==2.11.0
python-multipart==0.0.20
pytz==2024.2
```

## Environment Variables
```
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_JWT_SECRET=your-jwt-secret
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
GOOGLE_PLACES_API_KEY=your-api-key
APP_ENV=production
```
