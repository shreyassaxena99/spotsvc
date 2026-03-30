# User Onboarding Profile Endpoints — Design Spec

**Date:** 2026-03-30
**Status:** Approved

---

## Overview

Add two endpoints to handle onboarding profile data collected from new users:

- `POST /users/profile` — upsert onboarding profile into `public.user_profiles`
- `GET /users/profile/{user_id}` — check whether a profile row exists (iOS uses this to decide whether to show onboarding)

---

## Endpoints

### POST /users/profile

**Auth:** JWT required (`get_current_user` dependency). `user_id` is extracted from the JWT `sub` claim — it is NOT accepted in the request body.

**Request body:**
```json
{
  "working_style": "Fully remote",
  "home_area": "North London",
  "work_area": "Central London"
}
```
All fields are optional strings. No server-side enum validation — the iOS app controls valid values.

**Behaviour:**
1. Upsert into `public.user_profiles` on `user_id` conflict, setting `updated_at = now()`.
2. On success, call PostHog `identify` with `distinct_id=user_id` and only the non-`None` properties.
3. Raise `HTTPException(500)` if the Supabase upsert fails.

**Response (200):**
```json
{"status": "ok"}
```

---

### GET /users/profile/{user_id}

**Auth:** JWT required (`get_current_user` dependency). Returns `403` if path `user_id` does not match the JWT's `user_id`.

**Behaviour:** Select from `user_profiles` where `user_id` matches.

**Response — profile exists (200):**
```json
{
  "exists": true,
  "user_id": "...",
  "working_style": "Fully remote",
  "home_area": "North London",
  "work_area": "Central London"
}
```

**Response — no row yet (200):**
```json
{"exists": false}
```

---

## Files Changed

| File | Change |
|---|---|
| `requirements.txt` | Add `posthog` |
| `.env.example` | Add `POSTHOG_API_KEY` |
| `app/config.py` | Add optional `posthog_api_key: Optional[str] = None` |
| `app/core/posthog.py` | New — module-level PostHog singleton |
| `app/users/schemas.py` | Add `OnboardingProfileRequest`, `OnboardingProfileResponse`, `UserProfileData` |
| `app/users/service.py` | Add `upsert_user_profile()` and `get_user_profile()` |
| `app/users/router.py` | Add two new route handlers |
| `app/main.py` | Update `/health` to report `posthog_api_key_set` |

---

## Health Check

`GET /health` will include a `posthog_api_key_set: bool` field — consistent with the existing `admin_pwd_set` field. This lets Railway deployment checks confirm the key is configured in the environment.

---

## PostHog

- New dependency: `posthog` Python SDK
- Singleton in `app/core/posthog.py`, initialised with `POSTHOG_API_KEY` and `host="https://eu.i.posthog.com"`
- If `posthog_api_key` is not set, the identify call is skipped silently (safe for local dev)
- Only non-`None` profile fields are included in the `identify` properties

---

## Data Layer

- DB table: `public.user_profiles` (already created in Supabase)
- Upsert conflict target: `user_id`
- `updated_at` set explicitly on every upsert
- Access via `supabase` service-role client (bypasses RLS — intentional)
- Service functions are sync (consistent with all other service functions in this project)

---

## Out of Scope

- Enum validation on `working_style`, `home_area`, `work_area` — iOS controls the option set
- A DELETE or PATCH endpoint for the profile — not needed yet
