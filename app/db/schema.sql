-- =============================================================================
-- Spotsvc — Initial Schema
-- Run this in the Supabase SQL editor before starting the service.
-- =============================================================================

-- PostGIS (already enabled on Supabase, but safe to run again)
CREATE EXTENSION IF NOT EXISTS postgis;

-- Enum types
CREATE TYPE spot_category AS ENUM (
    'cafe', 'gym', 'hotel_lobby', 'coworking', 'library', 'restaurant', 'other'
);

CREATE TYPE access_type AS ENUM (
    'free', 'purchase_required', 'members_only'
);

-- Spots table
-- We store only what Google can't provide: coordinates, category, access, amenities.
CREATE TABLE spots (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    google_place_id   VARCHAR(300) NOT NULL UNIQUE,
    name              VARCHAR(255) NOT NULL,           -- cached from Google for search/display
    location          GEOGRAPHY(POINT, 4326) NOT NULL, -- PostGIS point (lon, lat)
    category          spot_category NOT NULL,
    access_type       access_type NOT NULL,
    wifi_available    BOOLEAN NOT NULL DEFAULT TRUE,
    power_outlets     BOOLEAN NOT NULL DEFAULT TRUE,
    noise_level       VARCHAR(20) CHECK (noise_level IN ('quiet', 'moderate', 'lively')),
    description       TEXT,                            -- editorial description
    admin_notes       TEXT,                            -- internal team notes
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,
    created_by        UUID REFERENCES auth.users(id),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Spatial index for nearby-spots queries (ST_DWithin)
CREATE INDEX idx_spots_location ON spots USING GIST (location);
-- Partial index for active-only queries
CREATE INDEX idx_spots_active ON spots (is_active) WHERE is_active = TRUE;

-- Auto-update updated_at on row changes
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER spots_updated_at
    BEFORE UPDATE ON spots
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- Row Level Security
-- FastAPI uses the service role key (bypasses RLS). These policies protect
-- against direct Supabase client access and add defence in depth.
-- =============================================================================

ALTER TABLE spots ENABLE ROW LEVEL SECURITY;

-- Any authenticated user can read active spots
CREATE POLICY "Authenticated users can read active spots"
    ON spots FOR SELECT
    USING (is_active = TRUE AND auth.role() = 'authenticated');

-- Only admins can create, update, or delete
CREATE POLICY "Admins can manage spots"
    ON spots FOR ALL
    USING ((auth.jwt() -> 'app_metadata' ->> 'role') = 'admin');

-- =============================================================================
-- Admin user setup (run once per admin)
-- Replace 'admin-user-uuid' with the actual UUID from auth.users.
-- =============================================================================

-- UPDATE auth.users
-- SET raw_app_meta_data = raw_app_meta_data || '{"role": "admin"}'::jsonb
-- WHERE id = 'admin-user-uuid';
