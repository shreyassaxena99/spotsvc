# CLAUDE.md — London Work Spots Backend

## Project Overview
Backend API for an iOS app that shows curated work-friendly spots (cafes, gyms, hotel lobbies, coworking spaces) in London. Users see spots on a map, view details, and save favorites.

## Tech Stack
- **Framework:** Python 3.12 + FastAPI (async throughout)
- **Database:** Supabase Postgres + PostGIS (connection pooler, port 6543)
- **ORM:** SQLAlchemy 2.0 (async, using `asyncpg`)
- **Auth:** Supabase Auth (Apple + Google sign-in) — no auth endpoints in this server. iOS app authenticates directly with Supabase. This server only validates Supabase JWTs.
- **External API:** Google Places API (New) via `requests`
- **Validation:** Pydantic v2
- **No migrations tooling.** Tables are created directly in Supabase SQL Editor. No Alembic.

## Project Structure
```
app/
├── main.py                     # FastAPI app, CORS, lifespan (db startup/shutdown)
├── config.py                   # pydantic-settings: SUPABASE_URL, SUPABASE_JWT_SECRET,
│                               #   SUPABASE_SERVICE_ROLE_KEY, SUPABASE_DB_URL,
│                               #   GOOGLE_PLACES_API_KEY
├── dependencies.py             # get_db, get_current_user, require_admin
│
├── spots/
│   ├── router.py               # GET /spots, GET /spots/{id}
│   ├── service.py              # PostGIS queries, is_open_now computation
│   └── schemas.py
│
├── saved/
│   ├── router.py               # GET/POST/DELETE /me/saved-spots
│   └── schemas.py
│
├── users/
│   ├── router.py               # GET/PATCH/DELETE /me
│   └── schemas.py
│
├── admin/
│   ├── router.py               # Spot CRUD, Google autocomplete proxy, Google place preview
│   ├── service.py              # Fetch + store Google data logic
│   └── schemas.py
│
├── google_places/
│   ├── client.py               # GooglePlacesClient class using requests
│   └── schemas.py              # Pydantic models for Google responses
│
├── db/
│   ├── database.py             # async engine + sessionmaker via Supabase connection pooler
│   └── models.py               # SQLAlchemy ORM models
│
├── core/
│   ├── security.py             # decode_supabase_jwt(), get_current_user(), require_admin()
│   └── middleware.py           # Rate limiting, request logging
│
└── scripts/
    └── refresh_google_data.py  # Standalone weekly cron script
```

## Authentication Rules
- **No auth endpoints in this server.** Auth is iOS ↔ Supabase directly.
- All protected endpoints receive a Supabase JWT via `Authorization: Bearer <token>`.
- Validate with `python-jose`: decode with `SUPABASE_JWT_SECRET`, algorithm `HS256`, audience `authenticated`.
- Extract `user_id` from `payload["sub"]`.
- Admin check: `payload["app_metadata"]["role"] == "admin"`.
- Use FastAPI `Depends()` for `get_current_user` and `require_admin`.

## Database

Tables are created manually via Supabase SQL Editor. No Alembic or migration tooling. The SQLAlchemy models in `db/models.py` mirror the tables for ORM usage but do not manage schema creation.

### SQL to run in Supabase SQL Editor

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

## API Endpoints

### GET /spots
Query params: `lat` (required), `lng` (required), `radius` (default 2000, max 5000), `category` (comma-separated), `access_type` (comma-separated).

PostGIS query using `ST_DWithin` and `ST_Distance`. Compute `is_open_now` in Python from `regular_hours` + `timezone`. Return: id, name, category, latitude, longitude, distance_meters, is_open_now, price_level, rating.

### GET /spots/{id}
Query params: `lat`, `lng` (for distance calculation).

Return full spot data from database. Compute `is_open_now` and `distance_meters`. Include `is_saved` boolean (check saved_spots for current user).

### GET /me/saved-spots
Query params: optional `lat`, `lng` for distance.

Return saved spots in same lightweight format as GET /spots.

### POST /me/saved-spots/{spot_id}
Insert into saved_spots. 409 if already saved.

### DELETE /me/saved-spots/{spot_id}
Delete from saved_spots. 404 if not saved.

### GET /me
Return profile (display_name, email_opt_in) + email from Supabase auth (use service role key to call `supabase.auth.admin.get_user_by_id`).

### PATCH /me
Update display_name and/or email_opt_in.

### DELETE /me
Delete profile (CASCADE deletes saved_spots) + delete auth user via Supabase Admin API.

### GET /admin/spots
Admin only. Paginated list of all spots (including inactive). Search by name.

### POST /admin/spots
Admin only. Accepts `google_place_id` + curated fields. Backend calls Google Places API via `requests`, stores everything in spots table.

### PUT /admin/spots/{id}
Admin only. Update curated fields only (category, access_type, wifi, power, noise, description, admin_notes, is_active).

### DELETE /admin/spots/{id}
Admin only. Soft-delete: set `is_active = false`.

### POST /admin/spots/{id}/refresh
Admin only. Re-fetch Google Places data for a single spot and update the row.

### GET /admin/google-autocomplete
Admin only. Query param: `q`. Proxies to Google Places Autocomplete API via `requests`. Return suggestions with place_ids.

### GET /admin/google-place/{place_id}
Admin only. Fetches full Google Place Details via `requests` for preview before adding a spot.

## Google Places Client

Use `requests` library. Wrap in a `GooglePlacesClient` class. Since `requests` is synchronous, call it from FastAPI endpoints using `run_in_executor` or just call synchronously (acceptable for admin endpoints and the weekly script).

### Place Details
```
GET https://places.googleapis.com/v1/places/{place_id}
Headers:
  X-Goog-Api-Key: {GOOGLE_PLACES_API_KEY}
  X-Goog-FieldMask: displayName,formattedAddress,shortFormattedAddress,location,nationalPhoneNumber,internationalPhoneNumber,googleMapsUri,websiteUri,priceLevel,rating,userRatingCount,editorialSummary,businessStatus,regularOpeningHours,currentOpeningHours,photos,outdoorSeating,restroom,servesBreakfast,servesLunch,servesDinner,servesBrunch,servesCoffee,allowsDogs,goodForGroups,dineIn,takeout,delivery,reservable,parkingOptions,paymentOptions,accessibilityOptions,timeZone
```

### Autocomplete
```
POST https://places.googleapis.com/v1/places:autocomplete
Headers:
  X-Goog-Api-Key: {GOOGLE_PLACES_API_KEY}
Body:
  { "input": "query", "locationBias": { "circle": { "center": { "latitude": 51.5074, "longitude": -0.1278 }, "radius": 20000 } } }
```

## is_open_now Logic
Compute from `regular_hours` JSON + `timezone` field. Google's `regularOpeningHours.periods` uses Sunday=0 day format. Convert Python's Monday=0 weekday to Google's format. Compare current time in spot's timezone against periods.

## Weekly Refresh Script (scripts/refresh_google_data.py)
Standalone script using `requests`. Fetches all active spots, calls Google Place Details for each, updates the row. Add `time.sleep(0.1)` between calls for rate limiting. Log failures, don't stop on individual errors. Update `google_data_updated_at` on success.

## Code Style & Conventions
- Async for all FastAPI endpoints and database queries.
- `requests` (synchronous) for Google Places API calls — use `run_in_executor` in async endpoints if needed.
- Type hints on all function signatures.
- Pydantic v2 models for all request/response schemas.
- Use `from __future__ import annotations` in all files.
- Use `UUID` type for all IDs.
- Environment variables via pydantic-settings `BaseSettings`.
- Error responses use FastAPI's `HTTPException`.
- All database queries use parameterized queries (never f-strings).
- Use `logging` module, not print().

## Dependencies (requirements.txt)
```
fastapi
uvicorn[standard]
sqlalchemy[asyncio]
asyncpg
python-jose[cryptography]
pydantic-settings
requests
geoalchemy2
supabase
python-multipart
pytz
```

## Environment Variables
```
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_JWT_SECRET=your-jwt-secret
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_DB_URL=postgresql+asyncpg://postgres.xxx:password@aws-0-eu-west-2.pooler.supabase.com:6543/postgres
GOOGLE_PLACES_API_KEY=your-api-key
```
