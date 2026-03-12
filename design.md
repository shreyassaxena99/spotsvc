# Backend System Design: London Work Spots App

## Overview

A mobile app (iOS) that shows users curated work-friendly spots in London — cafes, gyms, hotel lobbies, coworking spaces, etc. Users see spots on a map, view details (hours, busyness, pricing, access type), save favorites, and navigate to spots. An admin panel allows the team to curate spots with Google Maps autocomplete + manual fields.

**Core architectural principles:**
1. **Fetch once, store locally.** When an admin adds a spot, we call the Google Places API once and store all relevant fields in our database. A weekly background script refreshes this data.
2. **Supabase as the backend platform** — Postgres (with PostGIS), Auth (Apple + Google sign-in), Row Level Security.
3. **No Redis needed for MVP.** All place data lives in Postgres. The only field that benefits from live fetching is busyness — deferred to Phase 2.

---

## Tech Stack

| Layer | Choice | Notes |
|-------|--------|-------|
| **Framework** | Python 3.12 + FastAPI | Async for endpoints + DB, sync `requests` for Google API |
| **Database** | Supabase (Postgres + PostGIS) | Tables created via Supabase SQL Editor, no migrations tooling |
| **Auth** | Supabase Auth | Built-in Apple + Google social login |
| **Google Places** | `requests` library | Synchronous HTTP calls, wrapped in a client class |
| **Background Jobs** | Cron (GitHub Actions, Railway, or pg_cron) | Weekly Google Places data refresh |
| **Admin Panel** | React (Next.js) or Retool | Google Places Autocomplete for adding spots |

---

## Authentication with Supabase Auth

Supabase Auth handles Apple and Google sign-in natively. No auth endpoints needed in FastAPI.

### How it works

1. **iOS app** uses the Supabase Swift SDK to trigger social login:
   ```swift
   try await supabase.auth.signInWithOAuth(.google)
   try await supabase.auth.signInWithApple()
   ```

2. **Supabase Auth** handles the OAuth flow, verifies tokens, creates the user in `auth.users`, and returns a JWT.

3. **FastAPI** validates the Supabase JWT on protected requests using `python-jose` with the `SUPABASE_JWT_SECRET`, algorithm `HS256`, audience `authenticated`. User ID comes from `payload["sub"]`.

### Admin role

Set via Supabase `app_metadata`, embedded in the JWT:

```sql
UPDATE auth.users
SET raw_app_meta_data = raw_app_meta_data || '{"role": "admin"}'::jsonb
WHERE id = 'admin-user-uuid';
```

FastAPI checks `payload["app_metadata"]["role"] == "admin"` for admin endpoints.

### Email capture

Supabase stores the email in `auth.users.email`. Apple relay addresses work (Apple forwards emails). Apple only sends the email on first sign-in — Supabase captures it automatically.

---

## Data Model

Tables are created manually via **Supabase SQL Editor**. No Alembic or migration tooling. SQLAlchemy models mirror the tables for ORM usage but do not manage schema.

### `profiles`

Extends Supabase's `auth.users` with app-specific fields. Auto-created via trigger on signup.

```sql
CREATE TABLE profiles (
    id              UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    display_name    VARCHAR(100),
    email_opt_in    BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

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
```

### `spots`

Stores both Google Places data (fetched at creation, refreshed weekly) and manually curated fields.

```sql
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TYPE spot_category AS ENUM (
    'cafe', 'gym', 'hotel_lobby', 'coworking', 'library', 'restaurant', 'other'
);
CREATE TYPE access_type AS ENUM ('free', 'purchase_required', 'members_only');

CREATE TABLE spots (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Google Place reference
    google_place_id       VARCHAR(300) NOT NULL UNIQUE,

    -- Google data (fetched at creation, refreshed weekly)
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

    -- Google amenities
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

    -- Manually curated fields (admin sets these)
    category              spot_category NOT NULL,
    access_type           access_type NOT NULL,
    wifi_available        BOOLEAN DEFAULT TRUE,
    power_outlets         BOOLEAN DEFAULT TRUE,
    noise_level           VARCHAR(20),           -- 'quiet', 'moderate', 'lively'
    description           TEXT,
    admin_notes           TEXT,

    -- Metadata
    is_active             BOOLEAN DEFAULT TRUE,
    created_by            UUID,
    google_data_updated_at TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_spots_location ON spots USING GIST (location);
CREATE INDEX idx_spots_active ON spots (is_active) WHERE is_active = TRUE;
CREATE INDEX idx_spots_name ON spots USING GIN (to_tsvector('english', name));
```

**What we store vs. what's curated:**

| Field | Source | When set |
|-------|--------|----------|
| Name, address, phone, website | Google Places | Creation + weekly refresh |
| Lat/lng | Google Places | Creation + weekly refresh |
| Hours (regular + current) | Google Places | Creation + weekly refresh |
| Photos | Google Places | Creation + weekly refresh |
| Price level, rating, review count | Google Places | Creation + weekly refresh |
| Google amenities (outdoor seating, restroom, etc.) | Google Places | Creation + weekly refresh |
| Parking, payment, accessibility | Google Places | Creation + weekly refresh |
| **Category** | **Manual** | Admin sets at creation |
| **Access type** | **Manual** | Admin sets at creation |
| **Wi-Fi, power outlets, noise level** | **Manual** | Admin sets at creation |
| **Description** | **Manual** | Admin writes at creation |

### `saved_spots`

```sql
CREATE TABLE saved_spots (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL,
    spot_id    UUID NOT NULL REFERENCES spots(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, spot_id)
);
CREATE INDEX idx_saved_spots_user ON saved_spots (user_id);
```

### Row Level Security

```sql
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

### ER Diagram

```
auth.users (Supabase managed)
    │
    ├── 1:1 ── profiles (display_name, email_opt_in)
    │
    └── 1:N ── saved_spots
                    │
                    └── N:1 ── spots (Google data + curated data, all in one table)
```

---

## "Is Open Now" Logic

Computed server-side from `regular_hours` JSON + `timezone` field. No external API calls needed. Available on both the list and detail endpoints.

---

## API Endpoints

Auth is handled by Supabase directly (iOS ↔ Supabase). FastAPI handles data only.

### Spots

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/spots` | Protected | List spots near user (PostGIS, no external calls) |
| `GET` | `/spots/:id` | Protected | Full spot detail (database only) |

#### `GET /spots` — Map view

```
GET /spots?lat=51.5074&lng=-0.1278&radius=2000&category=cafe,coworking
```

| Param | Type | Required | Default | Notes |
|-------|------|----------|---------|-------|
| `lat` | float | Yes | | User's latitude |
| `lng` | float | Yes | | User's longitude |
| `radius` | int | No | 2000 | Meters, max 5000 |
| `category` | string | No | all | Comma-separated filter |
| `access_type` | string | No | all | Filter |

```json
{
  "spots": [
    {
      "id": "uuid",
      "name": "Workshop Coffee",
      "category": "cafe",
      "latitude": 51.5225,
      "longitude": -0.0849,
      "distance_meters": 450,
      "is_open_now": true,
      "price_level": "PRICE_LEVEL_MODERATE",
      "rating": 4.3
    }
  ]
}
```

Pure PostGIS query. `is_open_now` computed in Python from stored hours.

#### `GET /spots/:id` — Detail view

Full spot data from database. No external calls. Includes `is_open_now`, `distance_meters`, `is_saved`, all Google amenities, and curated fields.

---

### Saved Spots

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/me/saved-spots` | Protected | List saved spots (same format as `/spots`) |
| `POST` | `/me/saved-spots/:spotId` | Protected | Save a spot |
| `DELETE` | `/me/saved-spots/:spotId` | Protected | Unsave a spot |

---

### User Profile

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/me` | Protected | Get profile + email |
| `PATCH` | `/me` | Protected | Update display name, email opt-in |
| `DELETE` | `/me` | Protected | Delete account + data (GDPR) |

---

### Admin Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/admin/spots` | Admin | List all spots (paginated, searchable) |
| `POST` | `/admin/spots` | Admin | Create spot (fetches Google data via `requests`, stores all) |
| `PUT` | `/admin/spots/:id` | Admin | Update curated fields |
| `DELETE` | `/admin/spots/:id` | Admin | Soft-delete |
| `POST` | `/admin/spots/:id/refresh` | Admin | Re-fetch Google data for one spot |
| `GET` | `/admin/google-autocomplete?q=` | Admin | Proxy Google Autocomplete via `requests` |
| `GET` | `/admin/google-place/:placeId` | Admin | Preview Google data via `requests` |

**Admin spot creation flow:**

```
1. Admin types place name
2. → GET /admin/google-autocomplete?q=Workshop+Coffee+London
3. Admin selects suggestion
4. → GET /admin/google-place/{place_id} (preview)
5. Admin fills in: category, access_type, wifi, power, noise, description
6. → POST /admin/spots (backend calls Google API via requests, stores everything)
```

---

## Navigation Deeplink

No backend endpoint needed. iOS app constructs from coordinates:

```
Apple Maps:  https://maps.apple.com/?daddr=51.5225,-0.0849
Google Maps: https://www.google.com/maps/dir/?api=1&destination=51.5225,-0.0849
Citymapper:  https://citymapper.com/directions?endcoord=51.5225,-0.0849
```

Or use the `google_maps_uri` stored in the database.

---

## Architecture Diagram

```
┌─────────────────┐        ┌─────────────────┐
│   iOS App        │        │  Admin Panel     │
│   (Swift)        │        │  (React/Next.js) │
└──┬───────────┬───┘        └────────┬─────────┘
   │           │                     │
   │  Auth     │  Data               │  Data
   │  (direct) │  (via API)          │  (via API)
   ▼           ▼                     ▼
┌────────┐  ┌──────────────────────────────────┐
│Supabase│  │         FastAPI Server            │
│  Auth  │  │                                   │
│        │  │  Spots / Saved / Users / Admin    │
│ Apple  │  │  routers                          │
│ Google │  │                                   │
│ sign-in│  │  Google Places client (requests)  │
│        │  │  JWT validation via Supabase      │
└────────┘  └─────────────┬─────────────────────┘
                          │
                          ▼
                   ┌──────────┐         ┌───────────────┐
                   │ Supabase │         │ Google Places  │
                   │ Postgres │         │     API        │
                   │ + PostGIS│         │                │
                   │          │ ◄───────│ Called only:    │
                   │ - profiles│        │ • spot creation │
                   │ - spots  │         │ • weekly refresh│
                   │ - saved  │         │ • admin preview │
                   └──────────┘         └───────────────┘

                   ┌─────────────────────┐
                   │  Weekly Cron Job     │
                   │  (refresh script)    │
                   │  uses requests lib   │
                   │  ~500 API calls      │
                   │  Cost: ~$8.50/week   │
                   └─────────────────────┘
```

---

## Google Places API Cost

| Action | Frequency | Monthly cost |
|--------|-----------|-------------|
| Admin adds/previews spots | ~10-20/week | ~$2 |
| Autocomplete (admin) | ~50/week | ~$0.57 |
| Weekly refresh (500 spots) | 4x/month | ~$34 |
| **Total** | | **~$37/month** |

---

## Supabase Plan

Pro plan ($25/mo) is sufficient for MVP. PostGIS available on all plans.

---

## MVP Prioritization

**Phase 1 — Core:**
- Supabase Auth (Apple + Google sign-in)
- `GET /spots` with PostGIS + `is_open_now`
- `GET /spots/:id` with full detail from Postgres
- Save/unsave spots
- Admin panel with Google autocomplete + curated fields
- Weekly Google data refresh cron

**Phase 2 — Enhancements:**
- Live busyness (on-demand Google call, cached in Redis)
- Filters (Wi-Fi, noise, outdoor seating, dog-friendly)
- Push notifications
- User-submitted spot suggestions

**Phase 3 — Growth:**
- User reviews/tips
- Live occupancy reporting
- Expand beyond London
- Analytics dashboard
