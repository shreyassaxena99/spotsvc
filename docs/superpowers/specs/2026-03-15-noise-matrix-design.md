# Noise Matrix Design Spec

**Date:** 2026-03-15
**Status:** Approved
**Feature:** Replace static `noise_level` with a time-aware 2×3 noise matrix

---

## Overview

Each spot currently stores a single static noise level (`quiet`, `moderate`, `lively`). This is replaced with a 2×3 matrix — two day types (Weekday, Weekend) × three time periods (Morning, Afternoon, Evening) — where each cell stores a noise level and the timestamp it was last set. The full matrix is sent to all clients; iOS and web apps select the contextually relevant cell based on the current local time and day.

---

## Time Period Definitions

| Period    | Local time range |
|-----------|-----------------|
| Morning   | 06:00 – 10:59   |
| Afternoon | 11:00 – 15:59   |
| Evening   | 16:00 – close   |

---

## Data Model

### DB Schema Changes (Supabase SQL Editor — run in order)

**Step 1 — Add column:**
```sql
ALTER TABLE spots ADD COLUMN noise_matrix JSONB;
```

**Step 2 — Backfill existing rows:**
```sql
UPDATE spots
SET noise_matrix = jsonb_build_object(
  'weekday', jsonb_build_object(
    'morning',   jsonb_build_object('level', noise_level, 'updated_at', NOW()),
    'afternoon', jsonb_build_object('level', noise_level, 'updated_at', NOW()),
    'evening',   jsonb_build_object('level', noise_level, 'updated_at', NOW())
  ),
  'weekend', jsonb_build_object(
    'morning',   jsonb_build_object('level', noise_level, 'updated_at', NOW()),
    'afternoon', jsonb_build_object('level', noise_level, 'updated_at', NOW()),
    'evening',   jsonb_build_object('level', noise_level, 'updated_at', NOW())
  )
);
```
Spots where `noise_level IS NULL` produce an all-null matrix (N/A baseline). This is correct.

**Step 3 — Drop old column:**
```sql
ALTER TABLE spots DROP COLUMN noise_level;
```

### JSONB Shape

```json
{
  "weekday": {
    "morning":   { "level": "quiet",    "updated_at": "2026-03-15T10:00:00Z" },
    "afternoon": { "level": "moderate", "updated_at": "2026-03-15T10:00:00Z" },
    "evening":   { "level": "lively",   "updated_at": "2026-03-15T10:00:00Z" }
  },
  "weekend": {
    "morning":   { "level": null, "updated_at": null },
    "afternoon": { "level": "moderate", "updated_at": "2026-03-15T10:00:00Z" },
    "evening":   { "level": "lively",   "updated_at": "2026-03-15T10:00:00Z" }
  }
}
```

`level: null` means N/A (either unknown or venue closed during that period).

---

## Pydantic Models (`app/db/noise.py` — new shared file)

```python
# Input — admin writes, level is the only settable field per cell
class NoiseCellInput(BaseModel):
    level: Optional[Literal["quiet", "moderate", "lively"]] = None  # None = N/A

class NoisePeriodInput(BaseModel):
    morning: NoiseCellInput = NoiseCellInput()
    afternoon: NoiseCellInput = NoiseCellInput()
    evening: NoiseCellInput = NoiseCellInput()

class NoiseMatrixInput(BaseModel):
    weekday: NoisePeriodInput = NoisePeriodInput()
    weekend: NoisePeriodInput = NoisePeriodInput()

# Output — API responses, includes server-stamped updated_at per cell
class NoiseCellOutput(BaseModel):
    level: Optional[str]
    updated_at: Optional[datetime]

class NoisePeriodOutput(BaseModel):
    morning: NoiseCellOutput
    afternoon: NoiseCellOutput
    evening: NoiseCellOutput

class NoiseMatrixOutput(BaseModel):
    weekday: NoisePeriodOutput
    weekend: NoisePeriodOutput
```

Two helpers also live in `app/db/noise.py`:

- `noise_matrix_to_db(matrix: NoiseMatrixInput) -> dict` — converts input to JSONB dict, stamping `updated_at: datetime.now(UTC)` on cells with a non-null level, `null` on N/A cells
- `noise_matrix_from_db(data: dict | None) -> NoiseMatrixOutput | None` — parses raw JSONB from DB into `NoiseMatrixOutput`

---

## API Changes

### Admin (`app/admin/schemas.py`)

| Schema | Old field | New field |
|--------|-----------|-----------|
| `CreateSpotRequest` | `noise_level: Optional[Literal["quiet","moderate","lively"]]` | `noise_matrix: Optional[NoiseMatrixInput] = None` |
| `UpdateSpotRequest` | `noise_level: Optional[Literal["quiet","moderate","lively"]]` | `noise_matrix: Optional[NoiseMatrixInput] = None` |
| `SpotResponse` | `noise_level: Optional[str]` | `noise_matrix: Optional[NoiseMatrixOutput]` |

### Suggestions (`app/suggestions/schemas.py`)

| Schema | Old field | New field |
|--------|-----------|-----------|
| `UpdateSuggestionStatusRequest` | `noise_level: Optional[Literal["quiet","moderate","lively"]]` | `noise_matrix: Optional[NoiseMatrixInput] = None` |

### Public Spots (`app/spots/schemas.py`)

| Schema | Old field | New field |
|--------|-----------|-----------|
| `SpotPin` | `noise_level: Optional[str]` | `noise_matrix: Optional[NoiseMatrixOutput]` |
| `SpotDetail` | `noise_level: Optional[str]` | `noise_matrix: Optional[NoiseMatrixOutput]` |

---

## Service Layer Changes

### `app/admin/service.py`
- `create_spot`: replace `"noise_level": payload.noise_level` with `"noise_matrix": noise_matrix_to_db(payload.noise_matrix)` (omit key if `None`)
- `update_spot`: same substitution in the updates dict
- `_build_spot_response`: replace `noise_level=data.get("noise_level")` with `noise_matrix=noise_matrix_from_db(data.get("noise_matrix"))`

### `app/spots/service.py`
- `_build_spot_pin` / `_build_spot_detail`: replace `noise_level=row.get("noise_level")` with `noise_matrix=noise_matrix_from_db(row.get("noise_matrix"))`

### `app/suggestions/service.py`
- `update_suggestion_status`: replace `noise_level=noise_level` with `noise_matrix=noise_matrix` when constructing `CreateSpotRequest`
- `suggestions/router.py`: replace `payload.noise_level` with `payload.noise_matrix` in the `update_suggestion_status` call

---

## Migration Strategy Summary

1. Run SQL steps 1–3 in Supabase SQL Editor (add column → backfill → drop old column)
2. Deploy updated FastAPI service (schema + service changes)
3. No rollback needed between steps — old column is still present until Step 3 is explicitly run

---

## Frontend Changes (Lovable Prompts)

### Admin Web App

> We're replacing the single "Noise Level" dropdown on the add/edit spot form with a 2×3 noise matrix grid. The grid has two rows (Weekday, Weekend) and three columns (Morning 6–11am, Afternoon 11am–4pm, Evening 4pm+). Each cell contains a dropdown with four options: N/A, Quiet, Moderate, Lively. The default value for all cells is N/A.
>
> The API field is changing from `noise_level: string` to `noise_matrix` with this shape:
> ```json
> {
>   "weekday": { "morning": { "level": "quiet" }, "afternoon": { "level": null }, "evening": { "level": "moderate" } },
>   "weekend": { "morning": { "level": null }, "afternoon": { "level": "lively" }, "evening": { "level": null } }
> }
> ```
> `null` means N/A. `updated_at` per cell comes back in responses but is read-only — do not send it.
>
> Replace the noise level dropdown with this grid in both the Add Spot form and the Edit Spot form. The grid should be visually compact — a simple table layout with the day types as row headers and time periods as column headers. Also update any spot list/detail views in the admin panel that currently display a single noise level string to instead show the full 2×3 grid.

### Public-Facing Web App

> We're replacing the static "Noise Level" field on spot cards and detail pages with a contextual label that reflects the current time and day.
>
> The API now returns a `noise_matrix` object instead of `noise_level`:
> ```json
> {
>   "weekday": { "morning": { "level": "quiet", "updated_at": "..." }, "afternoon": { "level": "moderate", "updated_at": "..." }, "evening": { "level": null, "updated_at": null } },
>   "weekend": { "morning": { "level": null, "updated_at": null }, "afternoon": { "level": "lively", "updated_at": "..." }, "evening": { "level": "lively", "updated_at": "..." } }
> }
> ```
>
> Client-side logic to determine which cell to show:
> - Day type: if today is Saturday or Sunday → `weekend`, otherwise → `weekday`
> - Time of day: current local time before 11am → `morning`, 11am–4pm → `afternoon`, after 4pm → `evening`
> - If the selected cell's `level` is `null`, hide the noise label entirely
>
> Apply this everywhere a noise level is currently shown — spot cards on the map/list and the spot detail page.
